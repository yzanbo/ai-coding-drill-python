# 統合テストの共通ヘルパ。
#
# 目的：
#   - GitHub OAuth スタブ（token 交換 + user 取得を respx で intercept）
#   - Set-Cookie ヘッダーから Cookie value を取り出す
#   - 「ログイン状態のクライアント」を 1 関数で組み立てる（テスト先頭での
#      使い回しを楽にする）
#
# 配置理由：
#   pytest の fixture にはせず素の関数として置く。@respx.mock が掛かった
#   テスト関数の中から呼ばれる前提で、fixture 化すると mock 文脈と
#   fixture スコープの兼ね合いが煩雑になるため（respx は per-test mock 推奨）。
#
# 命名は他テストと同じく leading underscore（テスト内部 API の慣習）。

import uuid
from typing import Any

import respx
from httpx import AsyncClient

from app.core.config import get_settings

# GitHub OAuth のエンドポイント（services/github_oauth.py が叩く 2 URL）。
# テスト側で 1 度だけ定義して、respx の intercept 対象にする。
_TOKEN_URL = "https://github.com/login/oauth/access_token"
_USER_API_URL = "https://api.github.com/user"


def stub_github_success(
    *,
    gh_id: int = 12345,
    name: str | None = "Taro",
    login: str = "taro",
    email: str | None = "taro@example.com",
) -> None:
    """GitHub OAuth の token 交換 + user 取得を成功レスポンスで intercept する。

    @respx.mock が掛かったテスト内から呼ぶ。
    """
    respx.post(_TOKEN_URL).respond(
        200, json={"access_token": "gho_dummy", "token_type": "bearer"}
    )
    respx.get(_USER_API_URL).respond(
        200, json={"id": gh_id, "name": name, "login": login, "email": email}
    )


def extract_cookie_value(response: Any, name: str) -> str:
    """Set-Cookie ヘッダーから指定 Cookie の値だけを取り出す。

    httpx の response.cookies は Domain 属性次第で取れないことがあるため、
    Set-Cookie 文字列を直接パースする。
    """
    set_cookie_headers = response.headers.get_list("set-cookie")
    prefix = f"{name}="
    for header in set_cookie_headers:
        if header.startswith(prefix):
            # "name=value; Path=/; ..." → value だけ取る。
            return header[len(prefix) :].split(";", 1)[0]
    raise AssertionError(f"Set-Cookie '{name}' not found in {set_cookie_headers!r}")


async def login_via_github(client: AsyncClient, *, gh_id: int = 1) -> str:
    """GitHub OAuth スタブでログインして CSRF ヘッダー値を返す。

    副作用：
      - client.cookies に session_id / csrf_token Cookie がセットされる
      - DB に users + auth_providers が 1 件ずつ作られる
      - Redis（fakeredis）にセッションハッシュが作られる

    返り値の csrf_token は POST 系の X-CSRF-Token ヘッダーにそのまま使う。
    呼び出し側のテスト関数に @respx.mock デコレータが必須。
    """
    stub_github_success(gh_id=gh_id, name=f"u{gh_id}", login=f"u{gh_id}", email=None)

    start = await client.get("/auth/github")
    state_token = start.headers["location"].split("state=")[1].split("&")[0]
    cb = await client.get(f"/auth/github/callback?code=ok&state={state_token}")

    settings = get_settings()
    signed = extract_cookie_value(cb, settings.session_cookie_name)
    csrf = extract_cookie_value(cb, settings.csrf_cookie_name)
    client.cookies.set(settings.session_cookie_name, signed)
    client.cookies.set(settings.csrf_cookie_name, csrf)
    return csrf


async def current_user_id(client: AsyncClient) -> uuid.UUID:
    """ログイン済みクライアントの user.id を /auth/me から取る（テスト観測用）。"""
    res = await client.get("/auth/me")
    assert res.status_code == 200
    return uuid.UUID(res.json()["id"])
