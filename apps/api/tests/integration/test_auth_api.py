# /auth/* ルーターの結合テスト。
#
# テスト方針：
#   - 実 FastAPI アプリ（main.app）+ 実 Postgres + fakeredis（_client 差し込み）
#     + respx（GitHub API 全モック）の組み合わせ
#   - 各 redirect 先・Set-Cookie・Redis 上のセッション・DB の行を観測する
#
# 関わる要件：
#   - authentication.md §1.4 / §2.4 共通 API + GitHub 固有 API
#   - §2.5 バリデーション
#   - 受け入れ条件全般

from collections.abc import Awaitable
from typing import cast

import fakeredis.aioredis
import respx
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.models.auth_providers import AuthProvider
from app.models.users import User

from ._helpers import (
    _TOKEN_URL,
    extract_cookie_value,
    stub_github_success,
)


async def _smembers(redis: fakeredis.aioredis.FakeRedis, key: str) -> set[str]:
    return await cast("Awaitable[set[str]]", redis.smembers(key))


async def _hgetall(redis: fakeredis.aioredis.FakeRedis, key: str) -> dict[str, str]:
    return await cast("Awaitable[dict[str, str]]", redis.hgetall(key))


class TestUnauthenticated:
    async def test_異常系_未認証でGET_auth_meは401(
        self, client: AsyncClient
    ) -> None:
        res = await client.get("/auth/me")
        assert res.status_code == 401

    async def test_異常系_未認証でPOST_auth_logoutは401(
        self, client: AsyncClient
    ) -> None:
        # CSRF middleware が認証情報なしの POST を 401 で弾く（dep 到達前）。
        res = await client.post("/auth/logout")
        assert res.status_code == 401

    async def test_異常系_stale_session_cookie付きの401は両Cookieを削除する(
        self, client: AsyncClient
    ) -> None:
        """Cookie はあるが Redis に session が無い stale 状態の loop 防止。

        Frontend (authed) layout の useGetAuthMe → 401 → /login → /login Server
        の hasSessionCookie → redirect で原画面 → 再び 401 ... の無限ループを
        構造的に断ち切る。401 を返した時点で session_id / csrf_token Cookie を
        Max-Age=0 で物理削除する（main.py の clear_stale_session_cookie_on_401
        middleware）。
        """
        settings = get_settings()
        # 署名形式に合わない / Redis にも対応 session が無い stale Cookie を
        #   ブラウザに残っている想定でクライアントに積む。
        client.cookies.set(settings.session_cookie_name, "garbage.value")

        res = await client.get("/auth/me")
        assert res.status_code == 401

        # Set-Cookie 群を全部見て、session_id と csrf_token の両方が
        # Max-Age=0（または expires=過去）で削除指示されていることを確認。
        set_cookies = res.headers.get_list("set-cookie")
        session_clear = any(
            settings.session_cookie_name in sc
            and ("Max-Age=0" in sc or "expires=Thu, 01 Jan 1970" in sc)
            for sc in set_cookies
        )
        csrf_clear = any(
            settings.csrf_cookie_name in sc
            and ("Max-Age=0" in sc or "expires=Thu, 01 Jan 1970" in sc)
            for sc in set_cookies
        )
        assert session_clear, f"session_id 削除 Set-Cookie が出ていない: {set_cookies}"
        assert csrf_clear, f"csrf_token 削除 Set-Cookie が出ていない: {set_cookies}"

    async def test_異常系_Cookieなしの401はSet_Cookieを発行しない(
        self, client: AsyncClient
    ) -> None:
        """純粋な未ログイン（Cookie 無し）の 401 では余計な Set-Cookie を出さない。

        clear_stale_session_cookie_on_401 middleware は session_id Cookie が
        リクエストに付いている時だけ発火する仕様。
        """
        settings = get_settings()
        # クライアントに何の Cookie も積まずに /auth/me を叩く。
        assert settings.session_cookie_name not in client.cookies

        res = await client.get("/auth/me")
        assert res.status_code == 401

        set_cookies = res.headers.get_list("set-cookie")
        # session 関連の Set-Cookie が一切出ていないこと。
        assert not any(settings.session_cookie_name in sc for sc in set_cookies)
        assert not any(settings.csrf_cookie_name in sc for sc in set_cookies)


class TestAuthGithub:
    async def test_正常系_GET_auth_githubは302でstateがURLに乗る(
        self, client: AsyncClient, fake_redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        res = await client.get("/auth/github")
        assert res.status_code == 302
        location = res.headers["location"]
        assert location.startswith("https://github.com/login/oauth/authorize?")
        assert "state=" in location

        # Redis に state レコードが書かれていること（next_path は空文字）。
        # state クエリ値を取り出して直接 GET で照合する。
        state_token = location.split("state=")[1].split("&")[0]
        stored = await fake_redis.get(f"state:{state_token}")
        assert stored == ""

    async def test_正常系_next_が有効な相対パスならstate_recordに同梱される(
        self, client: AsyncClient, fake_redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        res = await client.get("/auth/github?next=/problems")
        location = res.headers["location"]
        state_token = location.split("state=")[1].split("&")[0]
        stored = await fake_redis.get(f"state:{state_token}")
        assert stored == "/problems"

    async def test_正常系_next_が外部URLなら空文字に正規化される(
        self, client: AsyncClient, fake_redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        """オープンリダイレクト対策：外部 URL は黙ってホームへ。"""
        res = await client.get("/auth/github?next=https://evil.com")
        location = res.headers["location"]
        state_token = location.split("state=")[1].split("&")[0]
        stored = await fake_redis.get(f"state:{state_token}")
        assert stored == ""


class TestAuthGithubCallbackErrors:
    async def test_異常系_codeもstateも無いとstate_invalidへ302(
        self, client: AsyncClient
    ) -> None:
        res = await client.get("/auth/github/callback")
        assert res.status_code == 302
        assert "/login?auth_error=state_invalid" in res.headers["location"]

    async def test_異常系_error_access_deniedはoauth_canceledへ302(
        self, client: AsyncClient
    ) -> None:
        res = await client.get("/auth/github/callback?error=access_denied")
        assert res.status_code == 302
        assert "/login?auth_error=oauth_canceled" in res.headers["location"]

    async def test_異常系_state不一致はstate_invalidへ302(
        self, client: AsyncClient
    ) -> None:
        res = await client.get("/auth/github/callback?code=x&state=no-such")
        assert res.status_code == 302
        assert "/login?auth_error=state_invalid" in res.headers["location"]

    @respx.mock
    async def test_異常系_state一致でもGitHub_token交換失敗ならoauth_failed(
        self, client: AsyncClient
    ) -> None:
        respx.post(_TOKEN_URL).respond(500)

        # state を 1 つ発行して照合させる。
        start = await client.get("/auth/github")
        state_token = start.headers["location"].split("state=")[1].split("&")[0]

        res = await client.get(f"/auth/github/callback?code=x&state={state_token}")
        assert res.status_code == 302
        assert "/login?auth_error=oauth_failed" in res.headers["location"]


class TestAuthGithubCallbackSuccess:
    @respx.mock
    async def test_正常系_新規ユーザーでDBとRedisに反映_Cookie発行(
        self, client: AsyncClient, fake_redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        stub_github_success(gh_id=999, name="New", login="newuser", email="new@x.com")

        start = await client.get("/auth/github")
        state_token = start.headers["location"].split("state=")[1].split("&")[0]

        res = await client.get(f"/auth/github/callback?code=ok&state={state_token}")

        # ホームへ 302。
        assert res.status_code == 302
        assert res.headers["location"].endswith("/")

        # Set-Cookie で session_id と csrf_token の 2 つが発行される。
        set_cookie = res.headers.get_list("set-cookie")
        names = [c.split("=", 1)[0] for c in set_cookie]
        assert get_settings().session_cookie_name in names
        assert get_settings().csrf_cookie_name in names

        # DB に users + auth_providers の行が 1 件ずつ作られる。
        async with AsyncSessionLocal() as s:
            users = (await s.execute(select(User))).scalars().all()
            providers = (await s.execute(select(AuthProvider))).scalars().all()
        assert len(users) == 1
        assert users[0].display_name == "New"
        assert users[0].email == "new@x.com"
        assert len(providers) == 1
        assert providers[0].provider == "github"
        assert providers[0].provider_id == "999"
        assert providers[0].user_id == users[0].id

        # Redis に session:<sid> + user:<id>:sessions が作られている。
        sessions = await _smembers(fake_redis, f"user:{users[0].id}:sessions")
        assert len(sessions) == 1

    @respx.mock
    async def test_正常系_callbackのリダイレクト先はFrontendの絶対URL(
        self, client: AsyncClient
    ) -> None:
        """authentication.md §2.4: Backend と Frontend は別オリジンで動く構成のため、
        callback の Location ヘッダは Frontend オリジンを含む absolute URL でなければ
        ならない。相対パスを返してしまうとブラウザは Backend オリジンに解決してしまい、
        別オリジン構成では正しい画面に遷移できない。
        """
        stub_github_success(gh_id=555, name="Abs", login="abs", email=None)

        start = await client.get("/auth/github")
        state_token = start.headers["location"].split("state=")[1].split("&")[0]
        res = await client.get(f"/auth/github/callback?code=ok&state={state_token}")

        assert res.status_code == 302
        location = res.headers["location"]
        # frontend_base_url を起点にした絶対 URL であること。
        # 相対パス（"/" 単独 等）を返していた場合はこの assert で落ちる。
        frontend_base = get_settings().frontend_base_url.rstrip("/")
        assert location.startswith(frontend_base + "/"), (
            f"Location must be absolute Frontend URL, got: {location}"
        )

    @respx.mock
    async def test_正常系_同じprovider_idで再ログインしてもusersは1件のまま(
        self, client: AsyncClient
    ) -> None:
        """authentication.md §2.1：同一 provider_id なら既存 users を再利用。"""
        stub_github_success(gh_id=42, name="A", login="a", email="a@x.com")

        # 1 回目ログイン。
        start = await client.get("/auth/github")
        state_token = start.headers["location"].split("state=")[1].split("&")[0]
        await client.get(f"/auth/github/callback?code=ok&state={state_token}")

        # 2 回目ログイン（同じ provider_id だが name/email を変えて再ログイン）。
        respx.reset()
        stub_github_success(gh_id=42, name="A renamed", login="a", email="newer@x.com")
        start2 = await client.get("/auth/github")
        state_token2 = start2.headers["location"].split("state=")[1].split("&")[0]
        await client.get(f"/auth/github/callback?code=ok2&state={state_token2}")

        async with AsyncSessionLocal() as s:
            users = (await s.execute(select(User))).scalars().all()
            providers = (await s.execute(select(AuthProvider))).scalars().all()
        # users / auth_providers ともに 1 件のまま（重複しない）。
        assert len(users) == 1
        assert len(providers) == 1
        # display_name / email は最新値で上書きされている（§2.1）。
        assert users[0].display_name == "A renamed"
        assert users[0].email == "newer@x.com"

    @respx.mock
    async def test_正常系_初回ログインで旧Cookie無しでも例外なく動く(
        self, client: AsyncClient
    ) -> None:
        """_invalidate_previous_session の no-op パス（Cookie 無し）を明示的に検証。

        Cookie 無し初回ログインは新規ユーザーテストでも暗黙に通っているが、
        旧セッション無効化の no-op 経路を契約として独立に固定する。
        """
        stub_github_success(gh_id=100, name="N", login="n", email=None)
        start = await client.get("/auth/github")
        state_token = start.headers["location"].split("state=")[1].split("&")[0]

        # クライアントに session_id Cookie を一切積まずに callback を叩く。
        assert get_settings().session_cookie_name not in client.cookies
        res = await client.get(f"/auth/github/callback?code=ok&state={state_token}")

        # 例外なく 302 + Set-Cookie に到達する。
        assert res.status_code == 302
        assert _extract_session_cookie(res)  # 値が取れる

    @respx.mock
    async def test_正常系_署名不正の旧Cookieが付いていても新規ログイン成功(
        self, client: AsyncClient
    ) -> None:
        """_invalidate_previous_session の no-op パス（unsign_sid 失敗）を検証。

        悪意のあるブラウザ拡張 / 古い手書き Cookie 等で署名不正な session_id が
        付いていても、新規 sid 発行に支障を出さない契約。
        """
        stub_github_success(gh_id=101, name="M", login="m", email=None)

        # 署名形式に合わない値を持ったまま callback。
        client.cookies.set(get_settings().session_cookie_name, "garbage.value")

        start = await client.get("/auth/github")
        state_token = start.headers["location"].split("state=")[1].split("&")[0]
        res = await client.get(f"/auth/github/callback?code=ok&state={state_token}")

        # 例外なく 302 + 新しい sid Cookie が発行される。
        assert res.status_code == 302
        new_signed = _extract_session_cookie(res)
        assert new_signed != "garbage.value"

    @respx.mock
    async def test_正常系_再ログインで旧sidがRedisから破棄される(
        self, client: AsyncClient, fake_redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        """authentication.md §1.3「ログイン時の旧セッション無効化」+ 受け入れ条件。"""
        stub_github_success(gh_id=1, name="x", login="x", email=None)

        # 1 回目ログイン → Cookie をクライアントに記憶させる。
        start1 = await client.get("/auth/github")
        state1 = start1.headers["location"].split("state=")[1].split("&")[0]
        cb1 = await client.get(f"/auth/github/callback?code=c1&state={state1}")
        # client.cookies に session_id が積まれる（http のスキーム差異で残らない場合は
        # Set-Cookie から手で詰める）。
        old_signed = _extract_session_cookie(cb1)
        client.cookies.set(get_settings().session_cookie_name, old_signed)

        # 2 回目ログイン（同じクライアントから state を取り直す → callback）。
        respx.reset()
        stub_github_success(gh_id=1, name="x", login="x", email=None)
        start2 = await client.get("/auth/github")
        state2 = start2.headers["location"].split("state=")[1].split("&")[0]
        cb2 = await client.get(f"/auth/github/callback?code=c2&state={state2}")
        new_signed = _extract_session_cookie(cb2)

        # 旧 sid と新 sid は別物。
        assert old_signed != new_signed

        # 旧 sid に対応する Redis ハッシュが消えている。
        from app.core.cookies import unsign_sid

        old_sid = unsign_sid(old_signed)
        assert old_sid is not None
        old_hash = await _hgetall(fake_redis, f"session:{old_sid}")
        assert old_hash == {}


class TestAuthMeAndLogout:
    @respx.mock
    async def test_正常系_ログイン後にGET_auth_meがユーザー情報を返す(
        self, client: AsyncClient
    ) -> None:
        stub_github_success(gh_id=7, name="Hanako", login="hanako", email="h@x.com")

        start = await client.get("/auth/github")
        state_token = start.headers["location"].split("state=")[1].split("&")[0]
        cb = await client.get(f"/auth/github/callback?code=ok&state={state_token}")
        # ASGI のレスポンスを介して Cookie をクライアントに移す。
        signed = _extract_session_cookie(cb)
        client.cookies.set(get_settings().session_cookie_name, signed)

        res = await client.get("/auth/me")
        assert res.status_code == 200
        body = res.json()
        assert body["displayName"] == "Hanako"
        assert body["email"] == "h@x.com"
        assert "id" in body

    @respx.mock
    async def test_正常系_logoutで204_RedisセッションとCookieが消える(
        self, client: AsyncClient, fake_redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        stub_github_success(gh_id=8, name="L", login="l", email=None)

        start = await client.get("/auth/github")
        state_token = start.headers["location"].split("state=")[1].split("&")[0]
        cb = await client.get(f"/auth/github/callback?code=ok&state={state_token}")

        # ログイン直後の Cookie 値を取得（Cookie に sid と csrf_token）。
        signed = _extract_session_cookie(cb)
        csrf = _extract_csrf_cookie(cb)
        client.cookies.set(get_settings().session_cookie_name, signed)
        client.cookies.set(get_settings().csrf_cookie_name, csrf)

        # ログアウト：X-CSRF-Token を載せて POST。
        res = await client.post("/auth/logout", headers={"X-CSRF-Token": csrf})
        assert res.status_code == 204
        # authentication.md §1.6: API は 204 のみ返し、リダイレクト指示（302）は含まない
        # （遷移は Frontend が制御するため、Location ヘッダは付けない契約）。
        assert "location" not in res.headers

        # Redis 上のセッションが消えている。
        from app.core.cookies import unsign_sid

        sid = unsign_sid(signed)
        assert sid is not None
        stored = await _hgetall(fake_redis, f"session:{sid}")
        assert stored == {}


class TestCookieAttributes:
    """ログイン成功時 / ログアウト時の Set-Cookie 属性を観測する。

    Cookie 属性は authentication.md §1.3 と 02-api-conventions.md の CSRF 節で
    定義された契約（HttpOnly / Secure / SameSite=Lax / Path=/）の SSoT。
    属性が落ちると XSS で sid 奪取 / CSRF 防御無効化 等の致命的な穴になるため、
    実 Set-Cookie ヘッダー文字列で確認する。
    """

    @respx.mock
    async def test_正常系_session_id_CookieはHttpOnly付き(
        self, client: AsyncClient
    ) -> None:
        """session_id は JS から触れない（XSS 対策）。"""
        stub_github_success(gh_id=200, name="X", login="x", email=None)
        start = await client.get("/auth/github")
        state_token = start.headers["location"].split("state=")[1].split("&")[0]
        cb = await client.get(f"/auth/github/callback?code=ok&state={state_token}")

        line = _extract_set_cookie_header(cb, get_settings().session_cookie_name)
        # Set-Cookie 属性は大小文字混在のため lower で比較。
        assert "httponly" in line.lower()

    @respx.mock
    async def test_正常系_csrf_token_CookieはHttpOnly無し(
        self, client: AsyncClient
    ) -> None:
        """csrf_token は Frontend が JS で読んで X-CSRF-Token に詰める契約。"""
        stub_github_success(gh_id=201, name="X", login="x", email=None)
        start = await client.get("/auth/github")
        state_token = start.headers["location"].split("state=")[1].split("&")[0]
        cb = await client.get(f"/auth/github/callback?code=ok&state={state_token}")

        line = _extract_set_cookie_header(cb, get_settings().csrf_cookie_name)
        assert "httponly" not in line.lower()

    @respx.mock
    async def test_正常系_両CookieにSameSite_Lax_と_Path_が付く(
        self, client: AsyncClient
    ) -> None:
        """SameSite=Lax で別オリジン POST に sid が乗らない / Path=/ でサイト全域。"""
        stub_github_success(gh_id=202, name="X", login="x", email=None)
        start = await client.get("/auth/github")
        state_token = start.headers["location"].split("state=")[1].split("&")[0]
        cb = await client.get(f"/auth/github/callback?code=ok&state={state_token}")

        for name in (
            get_settings().session_cookie_name,
            get_settings().csrf_cookie_name,
        ):
            line = _extract_set_cookie_header(cb, name).lower()
            assert "samesite=lax" in line
            assert "path=/" in line

    @respx.mock
    async def test_正常系_cookie_domain未指定ならDomain属性は出ない(
        self, client: AsyncClient
    ) -> None:
        """テスト環境では cookie_domain=None（host-only）。Domain= が出るとサブドメイン
        共有が暗黙に有効化されるため、明示設定なしでは絶対に出ないことを契約として固定。
        """
        # 前提：fixture が動く環境では get_settings().cookie_domain is None
        assert get_settings().cookie_domain is None

        stub_github_success(gh_id=203, name="X", login="x", email=None)
        start = await client.get("/auth/github")
        state_token = start.headers["location"].split("state=")[1].split("&")[0]
        cb = await client.get(f"/auth/github/callback?code=ok&state={state_token}")

        for name in (
            get_settings().session_cookie_name,
            get_settings().csrf_cookie_name,
        ):
            line = _extract_set_cookie_header(cb, name).lower()
            assert "domain=" not in line

    @respx.mock
    async def test_正常系_logoutのSetCookieもset時と属性が揃う(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        """delete_cookie で Domain / Path / SameSite を set 時と揃えないと、ブラウザが
        別 Cookie と判定して delete が効かず Cookie が残る既知の罠（routers/auth.py 内
        コメント）。set / delete 両方の Set-Cookie 行から属性集合を取って一致を確認する。
        """
        del fake_redis  # fixture 起動だけ
        stub_github_success(gh_id=204, name="X", login="x", email=None)

        # 1. ログイン → set 時の Set-Cookie を採取。
        start = await client.get("/auth/github")
        state_token = start.headers["location"].split("state=")[1].split("&")[0]
        cb = await client.get(f"/auth/github/callback?code=ok&state={state_token}")

        signed = _extract_session_cookie(cb)
        csrf = _extract_csrf_cookie(cb)
        client.cookies.set(get_settings().session_cookie_name, signed)
        client.cookies.set(get_settings().csrf_cookie_name, csrf)

        set_session_line = _extract_set_cookie_header(
            cb, get_settings().session_cookie_name
        )
        set_csrf_line = _extract_set_cookie_header(cb, get_settings().csrf_cookie_name)

        # 2. ログアウト → delete 時の Set-Cookie を採取。
        logout_res = await client.post(
            "/auth/logout", headers={"X-CSRF-Token": csrf}
        )
        assert logout_res.status_code == 204

        del_session_line = _extract_set_cookie_header(
            logout_res, get_settings().session_cookie_name
        )
        del_csrf_line = _extract_set_cookie_header(
            logout_res, get_settings().csrf_cookie_name
        )

        # 3. SameSite / Path / Domain の有無が set / delete で一致していること。
        #    Max-Age / Expires は意図的に異なる（set: TTL、delete: 0 / 過去日時）
        #    ので除外する。
        for attr in ("samesite=lax", "path=/", "domain="):
            assert (attr in set_session_line.lower()) == (
                attr in del_session_line.lower()
            ), f"session_id の {attr} が set と delete で食い違う"
            assert (attr in set_csrf_line.lower()) == (
                attr in del_csrf_line.lower()
            ), f"csrf_token の {attr} が set と delete で食い違う"


def _extract_session_cookie(response: object) -> str:
    """Set-Cookie ヘッダーから session_id Cookie の値だけを取り出す。

    httpx の response.cookies を使うと Domain 属性次第で取れないことがあるため、
    Set-Cookie 文字列を直接パースする（共通実装は _helpers.extract_cookie_value）。
    """
    settings = get_settings()
    return extract_cookie_value(response, settings.session_cookie_name)


def _extract_csrf_cookie(response: object) -> str:
    settings = get_settings()
    return extract_cookie_value(response, settings.csrf_cookie_name)


def _extract_set_cookie_header(response: object, name: str) -> str:
    """Set-Cookie ヘッダーの該当 Cookie について行全体（属性まで含む）を返す。"""
    set_cookie_headers = response.headers.get_list("set-cookie")  # type: ignore[attr-defined]
    prefix = f"{name}="
    for header in set_cookie_headers:
        if header.startswith(prefix):
            return header
    raise AssertionError(f"Set-Cookie '{name}' not found in {set_cookie_headers!r}")
