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


def _parse_db_url(db_url: str) -> tuple[str | None, str]:
    """DATABASE_URL からホストと DB 名（パス先頭の "/" を除いた部分）を返す。

    sqlalchemy 形式 (postgresql+asyncpg://...) もそのまま受け取れるよう、
    "+driver" を取り除いてから urlparse する。
    """
    if not db_url:
        return None, ""
    normalized = db_url
    if normalized.startswith("postgresql+"):
        idx = normalized.find("://")
        if idx > 0:
            normalized = "postgresql" + normalized[idx:]
    try:
        parsed = urlparse(normalized)
    except ValueError:
        return None, ""
    db_name = parsed.path.lstrip("/") if parsed.path else ""
    return parsed.hostname, db_name


def _ensure_test_db_url(db_url: str) -> None:
    """E2E 用エンドポイントが触ってよい DB か検証する（issue #86 の積極的 allowlist）。

    二重ガード:
      1. ホストが localhost / 127.0.0.1 / ::1 のいずれかであること
      2. DB 名が `_test` で終わること（dev DB `ai_coding_drill` を絶対に消さない）

    これにより、誤って dev の DATABASE_URL を E2E プロセスに渡しても TRUNCATE が
    走らない構造にする。
    """
    host, db_name = _parse_db_url(db_url)
    if host not in _LOCAL_DB_HOSTS:
        raise HTTPException(
            status_code=403,
            detail="DATABASE_URL のホストが localhost / 127.0.0.1 / ::1 以外は拒否",
        )
    if not db_name.endswith("_test"):
        raise HTTPException(
            status_code=403,
            detail=(
                f"DATABASE_URL の DB 名 '{db_name}' は _test で終わっていないため拒否"
                "（E2E は専用 DB ai_coding_drill_test でのみ実行可、issue #86）"
            ),
        )


async def _connect_local_db() -> asyncpg.Connection:
    """E2E 用テストエンドポイントから Postgres に繋ぐためのヘルパー。

    - DATABASE_URL が localhost 系 + DB 名末尾 `_test` 以外なら 403 を投げて誤接続を防ぐ
    - SQLAlchemy 形式（postgresql+asyncpg://...）を asyncpg 用の素の形式に直す
    """
    db_url = os.environ.get("DATABASE_URL", "")
    _ensure_test_db_url(db_url)
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

        破壊的操作のため三重ガード:
          1. 環境変数 E2E_RESET_ENABLED=true を必須にする（誤起動防止）
          2. DATABASE_URL のホストが localhost 系であること
          3. DATABASE_URL の DB 名が `_test` で終わること
             （dev DB `ai_coding_drill` の TRUNCATE を構造的に防ぐ、issue #86）

        対象:
          - Postgres: users / auth_providers / generation_requests / problems /
                      submissions / jobs を TRUNCATE CASCADE
          - Redis:    FLUSHDB（接続先 DB index は REDIS_URL に従う）
        """
        _ensure_test_reset_enabled()

        conn = await _connect_local_db()
        try:
            # 対象テーブルを明示列挙する (CASCADE で users → auth_providers / generation_requests
            # / problems の FK を辿る)。将来 submissions 等が users FK を持った時に
            # 意図しない巻き込みを防ぐため、reset 対象を増やす時はこの行を編集する強制力を持たせる。
            # problems は user_id を持たないが、E2E で問題行が累積しないよう同時に消す。
            # submissions は users / problems に FK + ON DELETE CASCADE なので
            # 上記 TRUNCATE で消えるが、明示列挙して reset 対象を読みやすくする
            # （CASCADE の暗黙挙動に頼ると将来 FK 制約が変わった時に気付けない）。
            await conn.execute(
                "TRUNCATE TABLE users, auth_providers, "
                "generation_requests, problems, submissions, jobs "
                "RESTART IDENTITY CASCADE"
            )
        finally:
            await conn.close()

        # E2E 用 Redis は docker-compose.test.yml で 6380 に立てる（dev の 6379 とポート分離）。
        # ポートで分かれているため DB index は /0 で十分
        # （apps/web/e2e/_helpers/constants.ts と同じ既定値）。
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6380/0")
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

    @app.post("/_test/seed-problem")
    async def seed_problem(
        title: str = Query("E2E 配列の合計", description="seed する問題のタイトル"),
        category: str = Query("array", description="カテゴリ（problems.category 列に入れる文字列）"),
        difficulty: str = Query(
            "easy", description="難易度（problems.difficulty 列に入れる文字列）"
        ),
    ) -> dict[str, str]:
        """problems に 1 行 INSERT して problem_id を返す E2E 専用エンドポイント。

        R1-4 の /problems 一覧 / 詳細 / 解答送信フローを E2E で叩くために、
        Worker 未実装期間でも問題行を即座に用意できるショートカット。
        generation_requests / jobs は介在させない（最短ルートで problems を生やすだけ）。

        SSoT は apps/api/app/models/problems.py。NOT NULL 列が増えたら本関数も更新する。
        """
        _ensure_test_reset_enabled()

        conn = await _connect_local_db()
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO problems
                  (title, description, category, difficulty, language,
                   examples, test_cases, reference_solution, judge_scores)
                VALUES
                  ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8, $9::jsonb)
                RETURNING id
                """,
                title,
                "E2E 用ダミー：数値配列の合計を返す関数 solve を実装してください。",
                category,
                difficulty,
                "typescript",
                json.dumps([{"input": "[1,2,3]", "output": "6"}]),
                # test_cases.input は Worker 側 TestCase 契約（[]any）に合わせる：solve(arg1, arg2, ...)
                # の各引数を配列で並べる。ここでは solve(a: number[]) を呼ぶので input は引数 1 つの配列を
                # さらに [] で包んだ `[[1,2,3]]` / `[[]]` になる。文字列を入れると grading Worker が
                # json unmarshal で落ちて即 dead 行きになる。
                # 契約 SSoT: apps/workers/grading/internal/grading/generation_prompt.go の TestCase
                json.dumps(
                    [
                        {"input": [[1, 2, 3]], "expected": 6},
                        {"input": [[]], "expected": 0},
                    ]
                ),
                "export const solve = (a: number[]) => a.reduce((s, n) => s + n, 0);",
                json.dumps({}),
            )
            if row is None:
                raise HTTPException(status_code=500, detail="problems INSERT failed")
            problem_id = row["id"]
        finally:
            await conn.close()

        return {"problem_id": str(problem_id)}

    @app.post("/_test/seed-submission")
    async def seed_submission(
        problem_id: str = Query(..., description="対象問題の id（seed-problem の戻り値）"),
        status: str = Query("graded", description="submissions.status: pending / graded / failed"),
        passed: bool = Query(True, description="result.passed: 全テスト通過したか"),
        score: int = Query(2, description="採点スコア（passed テスト数）"),
        total: int = Query(2, description="テスト総数（result.testResults の件数）"),
    ) -> dict[str, str]:
        """submissions に 1 行 INSERT して submission_id を返す E2E 専用エンドポイント。

        R1-6 の /me/history / /me/stats / /me/weakness を E2E で叩くために、
        Worker 未起動でも graded まで遷移した行を即座に用意できるショートカット。
        jobs は介在させない（最短ルートで submissions を生やすだけ）。

        user_id 解決：直近 created_at の users 行を引く（OAuth mock で作った
        ログイン直後ユーザーが該当）。E2E では beforeEach の resetState で
        毎テスト 1 ユーザーに揃うため、この経路で確実に「呼び出し元の view から
        見える submission」を作れる。

        SSoT は apps/api/app/models/submissions.py。NOT NULL 列・result JSONB の
        スキーマが変わったら本関数も更新する。
        """
        _ensure_test_reset_enabled()

        # status の許可値ガード。SubmissionStatus enum と合わせる
        # （apps/api/app/schemas/submissions.py の SubmissionStatus）。
        if status not in {"pending", "graded", "failed"}:
            raise HTTPException(status_code=422, detail=f"invalid status: {status}")

        # result JSONB を組み立て。graded 時のみ埋め、それ以外は NULL のまま挿す。
        result_json: str | None = None
        result_score: int | None = None
        if status == "graded":
            test_results = [
                {
                    "name": f"case{i + 1}",
                    "passed": passed if i < score else False,
                    "durationMs": 50,
                }
                for i in range(total)
            ]
            result_payload = {
                "passed": passed,
                "durationMs": 100,
                "testResults": test_results,
            }
            if not passed:
                result_payload["failureKind"] = "test_failed"
            result_json = json.dumps(result_payload)
            result_score = score

        conn = await _connect_local_db()
        try:
            # user_id 解決：直近 created_at の users 行を引く。
            #   beforeEach の resetState で毎テスト 1 ユーザーに揃うため
            #   ORDER BY created_at DESC LIMIT 1 で OAuth mock で作った直近の
            #   ログインユーザーが取れる。email 一致引きは GitHub 側で email を
            #   非公開設定にしているユーザーで NULL になりうるため使わない。
            user_row = await conn.fetchrow(
                "SELECT id FROM users ORDER BY created_at DESC LIMIT 1",
            )
            if user_row is None:
                raise HTTPException(
                    status_code=404,
                    detail="user not found（先に loginViaMockGithub を呼ぶ必要があります）",
                )
            user_id: UUID = user_row["id"]

            row = await conn.fetchrow(
                """
                INSERT INTO submissions
                  (user_id, problem_id, code, status, result, score,
                   graded_at)
                VALUES
                  ($1, $2, $3, $4::varchar, $5::jsonb, $6,
                   CASE WHEN $4::varchar IN ('graded', 'failed') THEN NOW() ELSE NULL END)
                RETURNING id
                """,
                user_id,
                UUID(problem_id),
                "export const solve = (a: number[]) => a.reduce((s, n) => s + n, 0);",
                status,
                result_json,
                result_score,
            )
            if row is None:
                raise HTTPException(status_code=500, detail="submissions INSERT failed")
            submission_id = row["id"]
        finally:
            await conn.close()

        return {"submission_id": str(submission_id)}

    @app.post("/_test/seed-generation")
    async def seed_generation(
        status: str = Query("pending", description="generation_requests.status: pending / completed / failed / canceled"),
        category: str = Query("array", description="カテゴリ（ProblemCategory）"),
        difficulty: str = Query("easy", description="難易度（ProblemDifficulty）"),
        failure_reason: str | None = Query(None, description="failed 時に書く失敗理由"),
        produced_problem_id: str | None = Query(None, description="completed 時に紐づく problem.id"),
    ) -> dict[str, str]:
        """generation_requests に 1 行 INSERT して id を返す E2E 専用エンドポイント。

        R1-7 の /me/generations を E2E で叩くために、Worker 未起動でも各状態の行を
        直接用意できるショートカット。jobs は介在させない（履歴一覧の表示と
        cancel / retry を確認するだけなら jobs は要らない）。

        user_id 解決は seed-submission と同じく直近 users 行を採用する。
        SSoT は apps/api/app/models/generation_requests.py。
        """
        _ensure_test_reset_enabled()

        if status not in {"pending", "completed", "failed", "canceled"}:
            raise HTTPException(status_code=422, detail=f"invalid status: {status}")

        conn = await _connect_local_db()
        try:
            user_row = await conn.fetchrow(
                "SELECT id FROM users ORDER BY created_at DESC LIMIT 1",
            )
            if user_row is None:
                raise HTTPException(
                    status_code=404,
                    detail="user not found（先に loginViaMockGithub を呼ぶ必要があります）",
                )
            user_id: UUID = user_row["id"]

            row = await conn.fetchrow(
                """
                INSERT INTO generation_requests
                  (user_id, category, difficulty, status,
                   produced_problem_id, failure_reason, completed_at)
                VALUES
                  ($1, $2, $3, $4::varchar,
                   $5, $6,
                   CASE WHEN $4::varchar IN ('completed', 'failed', 'canceled') THEN NOW() ELSE NULL END)
                RETURNING id
                """,
                user_id,
                category,
                difficulty,
                status,
                UUID(produced_problem_id) if produced_problem_id else None,
                failure_reason,
            )
            if row is None:
                raise HTTPException(status_code=500, detail="generation_requests INSERT failed")
            request_id = row["id"]
        finally:
            await conn.close()

        return {"request_id": str(request_id)}

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
