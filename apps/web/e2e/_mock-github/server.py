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
    本サーバはステートレスだが、後続テストで「name 変更」「Cancel」等の異常系を
    扱うため、特殊な code 値で挙動を分岐させる方式を採用：
    - code=cancel_*  → /authorize で error=access_denied を返す（Cancel ボタン押下相当）
    - code=user_name_a / code=user_name_b → /user で異なる name を返す
    - 上記以外 → 既定の test user を返す

起動方法（Playwright globalSetup or webServer から）：
    uv run python apps/web/e2e/_mock-github/server.py --port 18001

CI では Playwright `webServer` configuration で本スクリプトを自動起動する。
"""

from __future__ import annotations

import argparse
import sys
from urllib.parse import urlencode

import uvicorn
from fastapi import FastAPI, Form, Header, Query, Response
from fastapi.responses import JSONResponse, RedirectResponse

# 既定の test user。OAuth 完走後に Backend が DB に保存する想定の値。
_DEFAULT_USER = {
    "id": 999_000_001,
    "login": "e2e-testuser",
    "name": "E2E Test User",
    "email": "e2e-testuser@example.com",
}

# code → user profile mapping。テストごとに違う user を返したい時に使う。
# code=cancel_* / code=invalid_* は /authorize 側で別経路に分岐する。
_USER_VARIANTS: dict[str, dict[str, object]] = {
    # name 変更テスト用: 同 id + 違う name の 2 つの変種
    "user_name_a": {**_DEFAULT_USER, "name": "Original Name"},
    "user_name_b": {**_DEFAULT_USER, "name": "Updated Name"},
    # name 未設定 (None) → display_name が login にフォールバックする経路
    "user_no_name": {**_DEFAULT_USER, "name": None},
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
        # 後段の /user で返す user 変種を選ぶ識別子。code に埋めて redirect する。
        _user_variant: str = Query(""),
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

        # 正常系: code を生成して redirect。code は後続の /access_token / /user で
        # 「どの user 変種を返すか」を Backend に伝える経路として使う (実 GitHub では
        # 不透明 code だが mock では情報を埋め込む)。
        code = _user_variant or "auto"
        return RedirectResponse(
            url=f"{redirect_uri}?{urlencode({'code': code, 'state': state})}",
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
        # Authorization ヘッダから token を抜き、token 末尾の code から user 変種を復元する。
        # 例: "token mock_token::user_name_a" → "user_name_a"
        if not authorization.lower().startswith("token "):
            return JSONResponse({"message": "Unauthorized"}, status_code=401)
        token = authorization.split(" ", 1)[1]
        if not token.startswith("mock_token::"):
            return JSONResponse({"message": "Bad token"}, status_code=401)
        variant_key = token.split("::", 1)[1]
        user_profile = _USER_VARIANTS.get(variant_key, _DEFAULT_USER)
        return JSONResponse(user_profile, status_code=200)

    @app.get("/_health")
    async def health() -> dict[str, str]:
        """Playwright globalSetup から起動確認に使う最小エンドポイント。"""
        return {"status": "ok"}

    return app


def main() -> int:
    """CLI エントリポイント。uvicorn 経由でサーバを起動する。"""
    parser = argparse.ArgumentParser(description="Mock GitHub OAuth server (E2E only)")
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="bind host (既定 127.0.0.1、外部公開はしない)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=18001,
        help="bind port (既定 18001、Backend / web の port と衝突しない値)",
    )
    args = parser.parse_args()

    # log_level は CI ノイズ削減のため warning に絞る。debug が必要なら --log-level info で起動。
    uvicorn.run(
        _build_app(),
        host=args.host,
        port=args.port,
        log_level="warning",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
