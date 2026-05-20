"""Mock GitHub OAuth サーバ（E2E テスト専用）。

なぜ存在するか：
    R1-1 GitHub OAuth ログイン機能の E2E テスト (Playwright) で実 github.com を
    叩くのは不可能（API キー / 実ユーザー必須 / レート制限）。Backend の
    `GITHUB_AUTHORIZE_URL` / `GITHUB_TOKEN_URL` / `GITHUB_USER_API_URL` を
    本サーバの URL に上書きすることで、Backend は OAuth フローを mock 越しに
    完走する。

エンドポイント：
    GET  /login/oauth/authorize    : 認可画面の代替。即 302 で redirect_uri に code+state を載せて返す
    POST /login/oauth/access_token : code → access_token 交換
    GET  /user                     : access_token → GitHub user profile

挙動の切替（テスト側からの注入）：
    本サーバはステートレスだが、Cancel 等の異常系を扱うため /authorize の
    クエリパラメータで挙動を分岐させる：
    - /authorize?_mode=cancel → error=access_denied を返す（Cancel ボタン押下相当）
    - 上記以外（既定）         → 即 302 で redirect_uri に code+state を載せて返す

起動方法（Playwright globalSetup or webServer から）：
    uv run python apps/web/e2e/_mock-github/server.py --port 18001

CI では Playwright `webServer` configuration で本スクリプトを自動起動する。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from urllib.parse import urlencode, urlparse
from uuid import UUID

import asyncpg
import redis.asyncio as redis
import uvicorn
from fastapi import FastAPI, Form, Header, HTTPException, Path, Query, Response
from fastapi.responses import JSONResponse, RedirectResponse

# 許容する DB ホスト。/_test/reset の安全ガードで使う。
# 略称 (prd / stg 等) を blacklist で取りこぼす事故を避けるため、許容ホストだけを通す。
_LOCAL_DB_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def _is_local_db_url(db_url: str) -> bool:
    """DATABASE_URL のホスト部が localhost 系か判定する。

    sqlalchemy 形式 (postgresql+asyncpg://...) もそのまま受け取れるよう、
    "+driver" を取り除いてから urlparse する。
    """
    if not db_url:
        return False
    normalized = db_url
    if normalized.startswith("postgresql+"):
        idx = normalized.find("://")
        if idx > 0:
            normalized = "postgresql" + normalized[idx:]
    try:
        host = urlparse(normalized).hostname
    except ValueError:
        return False
    return host in _LOCAL_DB_HOSTS


async def _connect_local_db() -> asyncpg.Connection:
    """E2E 用テストエンドポイントから Postgres に繋ぐためのヘルパー。

    - DATABASE_URL が localhost / 127.0.0.1 以外なら 403 を投げて誤接続を防ぐ
    - SQLAlchemy 形式（postgresql+asyncpg://...）を asyncpg 用の素の形式に直す
    """
    db_url = os.environ.get("DATABASE_URL", "")
    if not _is_local_db_url(db_url):
        raise HTTPException(
            status_code=403,
            detail="DATABASE_URL のホストが localhost / 127.0.0.1 以外は拒否",
        )
    pg_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    return await asyncpg.connect(pg_url)


def _ensure_test_reset_enabled() -> None:
    """破壊的テストエンドポイント共通のガード。

    E2E_RESET_ENABLED=true がセットされた環境（playwright.config.ts の
    _MOCK_GITHUB_ENV）でのみ呼び出しを許可する。production / staging 等で
    間違って起動した時に DB を壊さないための保険。
    """
    if os.environ.get("E2E_RESET_ENABLED", "").lower() != "true":
        raise HTTPException(
            status_code=403,
            detail="E2E_RESET_ENABLED=true が未設定 (誤起動防止)",
        )


# 既定の test user。OAuth 完走後に Backend が DB に保存する想定の値。
_DEFAULT_USER = {
    "id": 999_000_001,
    "login": "e2e-testuser",
    "name": "E2E Test User",
    "email": "e2e-testuser@example.com",
}


def _build_app() -> FastAPI:
    """FastAPI アプリを組み立てて返す。

    モジュールトップで FastAPI を作ると uvicorn の `--reload` 等の動作が
    予測しにくくなるため、ファクトリ関数経由で生成する。
    """
    app = FastAPI(title="Mock GitHub OAuth", description="E2E 専用")

    @app.get("/login/oauth/authorize")
    async def authorize(
        # GitHub 仕様に合わせたクエリパラメータ。
        client_id: str = Query(...),
        redirect_uri: str = Query(...),
        state: str = Query(...),
        # 後段の動作分岐用。テスト側はクエリで上書きして「Cancel」を再現する。
        # 既定 (= "auto") なら正常系で即 302 リダイレクトする。
        # "cancel" を渡すと error=access_denied で redirect する。
        _mode: str = Query("auto"),
    ) -> Response:
        if _mode == "cancel":
            # GitHub 仕様: ユーザーが Cancel すると error+error_description+state を載せて
            # redirect する (code は付かない)。
            params = {
                "error": "access_denied",
                "error_description": "The user has denied your application access.",
                "state": state,
            }
            return RedirectResponse(
                url=f"{redirect_uri}?{urlencode(params)}", status_code=302
            )

        # 正常系: 固定 code "auto" を載せて redirect。実 GitHub では不透明 code だが
        # mock では後段 /access_token / /user で参照しないため固定値で十分。
        return RedirectResponse(
            url=f"{redirect_uri}?{urlencode({'code': 'auto', 'state': state})}",
            status_code=302,
        )

    @app.post("/login/oauth/access_token")
    async def access_token(
        client_id: str = Form(...),
        client_secret: str = Form(...),
        code: str = Form(...),
        redirect_uri: str = Form(...),
        accept: str = Header(default="application/json"),
    ) -> Response:
        # client_id / client_secret は形式チェックのみ (mock なので一致は問わない)。
        # accept ヘッダで JSON 返却 (Backend は明示的に JSON を要求する)。
        if not client_id or not client_secret:
            return JSONResponse({"error": "missing_credentials"}, status_code=400)

        # 異常系コード分岐: code=invalid_* なら error 応答 (GitHub 仕様で 200 + error)。
        if code.startswith("invalid_"):
            return JSONResponse(
                {
                    "error": "bad_verification_code",
                    "error_description": "The code passed is incorrect or expired.",
                },
                status_code=200,
            )

        # 正常系: token を返す。token 文字列に code を埋めて /user で復元できるようにする。
        return JSONResponse(
            {
                "access_token": f"mock_token::{code}",
                "token_type": "bearer",
                "scope": "",
            },
            status_code=200,
        )

    @app.get("/user")
    async def user(
        authorization: str = Header(default=""),
    ) -> Response:
        # Authorization ヘッダの形式チェックだけ行い、既定 user を返す。
        if not authorization.lower().startswith("token "):
            return JSONResponse({"message": "Unauthorized"}, status_code=401)
        token = authorization.split(" ", 1)[1]
        if not token.startswith("mock_token::"):
            return JSONResponse({"message": "Bad token"}, status_code=401)
        return JSONResponse(_DEFAULT_USER, status_code=200)

    @app.get("/_health")
    async def health() -> dict[str, str]:
        """Playwright globalSetup から起動確認に使う最小エンドポイント。"""
        return {"status": "ok"}

    @app.post("/_test/reset")
    async def reset_state() -> dict[str, str]:
        """E2E テスト間で DB / Redis を初期化する。

        破壊的操作のため二重ガード:
          1. 環境変数 E2E_RESET_ENABLED=true を必須にする (誤起動防止)
          2. DATABASE_URL に "production" / "staging" が含まれていたら拒否

        対象:
          - Postgres: users / auth_providers を TRUNCATE CASCADE
            (users が deleted_at を持つソフトデリート設計だが E2E では完全消去)
          - Redis:    DB 0 (アプリのデフォルト DB) を FLUSHDB
            (session / state / rate limit すべて wipe)
        """
        _ensure_test_reset_enabled()

        conn = await _connect_local_db()
        try:
            # 対象テーブルを明示列挙する (CASCADE で users → auth_providers / generation_requests
            # / problems の FK を辿る)。将来 submissions 等が users FK を持った時に
            # 意図しない巻き込みを防ぐため、reset 対象を増やす時はこの行を編集する強制力を持たせる。
            # problems は user_id を持たないが、E2E で問題行が累積しないよう同時に消す。
            await conn.execute(
                "TRUNCATE TABLE users, auth_providers, "
                "generation_requests, problems, jobs "
                "RESTART IDENTITY CASCADE"
            )
        finally:
            await conn.close()

        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        r: redis.Redis = redis.from_url(redis_url)
        try:
            await r.flushdb()
        finally:
            await r.aclose()

        return {"status": "reset"}

    @app.post("/_test/complete-generation-request/{request_id}")
    async def complete_generation_request(
        request_id: UUID = Path(..., description="生成リクエストの ID"),
    ) -> dict[str, str]:
        """生成リクエストを「完了」状態に押し込む E2E 専用エンドポイント。

        本来は Worker (apps/workers/generation) が処理して
        generation_requests.status を completed にし、produced_problem_id に
        新しい problems.id を書き込む。R1-3 時点では Worker は skeleton のみで
        実際の生成は動かないため、E2E では DB を直接書き換えてフローを進める。

        手順:
          1. problems に最小限の 1 行を INSERT して problem_id を確定
          2. generation_requests を completed + produced_problem_id で UPDATE
        """
        _ensure_test_reset_enabled()

        # problems の NOT NULL 列を全部埋める。中身は E2E ダミーで OK。
        # JSONB 列 (examples / test_cases / judge_scores) は json 文字列を渡す。
        # 注意：カラム構成を変えたらここも同期する必要がある（drift 検出経路の
        # 外で書いているため、自動では気付けない）。SSoT は ../../api/app/models/problems.py。
        conn = await _connect_local_db()
        try:
            problem_id_row = await conn.fetchrow(
                """
                INSERT INTO problems
                  (title, description, category, difficulty, language,
                   examples, test_cases, reference_solution, judge_scores)
                VALUES
                  ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8, $9::jsonb)
                RETURNING id
                """,
                "E2E ダミー問題",
                "E2E テストが状態遷移を確認するためのダミー問題本文。",
                "array",
                "easy",
                "typescript",
                json.dumps([]),
                json.dumps([]),
                "export const solve = () => null;",
                json.dumps({}),
            )
            if problem_id_row is None:
                raise HTTPException(status_code=500, detail="problems INSERT failed")
            problem_id = problem_id_row["id"]

            updated = await conn.execute(
                """
                UPDATE generation_requests
                SET status = 'completed',
                    produced_problem_id = $1,
                    updated_at = NOW()
                WHERE id = $2
                """,
                problem_id,
                request_id,
            )
        finally:
            await conn.close()

        # asyncpg の execute は "UPDATE n" を返す。n=0 は対象行なしを示す。
        if updated.endswith(" 0"):
            raise HTTPException(
                status_code=404,
                detail=f"generation_requests.id={request_id} が見つからない",
            )

        return {"status": "completed", "problem_id": str(problem_id)}

    @app.post("/_test/fail-generation-request/{request_id}")
    async def fail_generation_request(
        request_id: UUID = Path(..., description="生成リクエストの ID"),
    ) -> dict[str, str]:
        """生成リクエストを「失敗」状態に押し込む E2E 専用エンドポイント。

        complete 側と同様、Worker 未実装期間の代替として DB を直接書き換える。
        produced_problem_id は NULL のまま残す（失敗時は問題が生まれない）。
        """
        _ensure_test_reset_enabled()

        conn = await _connect_local_db()
        try:
            updated = await conn.execute(
                """
                UPDATE generation_requests
                SET status = 'failed',
                    updated_at = NOW()
                WHERE id = $1
                """,
                request_id,
            )
        finally:
            await conn.close()

        if updated.endswith(" 0"):
            raise HTTPException(
                status_code=404,
                detail=f"generation_requests.id={request_id} が見つからない",
            )

        return {"status": "failed"}

    return app


def main() -> int:
    """CLI エントリポイント。uvicorn 経由でサーバを起動する。"""
    parser = argparse.ArgumentParser(description="Mock GitHub OAuth server (E2E only)")
    parser.add_argument(
        "--port",
        type=int,
        default=18001,
        help="bind port (既定 18001、Backend / web の port と衝突しない値)",
    )
    args = parser.parse_args()

    # bind host は 127.0.0.1 固定。E2E 専用 + /_test/reset の破壊的操作を持つため
    # 0.0.0.0 公開を意図しない値で起動できないようにする (--host 引数自体を廃止)。
    # log_level は CI ノイズ削減のため warning に絞る。
    uvicorn.run(
        _build_app(),
        host="127.0.0.1",
        port=args.port,
        log_level="warning",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
