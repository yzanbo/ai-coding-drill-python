# services/github_oauth.GitHubOAuthClient のユニットテスト。
#
# テスト方針：
#   - respx で httpx.AsyncClient のレスポンスをパターンマッチでモック
#   - 共有 httpx クライアントの lifespan を fixture で open / close する
#   - GitHub の壊れた応答（200 + error body / id 非 int 等）を網羅
#
# 関わる要件：
#   - authentication.md §2.1 GitHub から取得する情報 + display_name 決定ルール
#   - §2.4 GET /auth/github/callback の失敗時 302（state_invalid / oauth_failed）

from collections.abc import AsyncIterator

import httpx
import pytest
import respx

from app.core.http_client import close_http_client, open_http_client
from app.services.github_oauth import GitHubOAuthClient, GitHubOAuthError

# GitHub の固定エンドポイント（github_oauth.py のプライベート定数を直接読まず、
# 仕様 URL として再記述する。実装が変わったらここも合わせて変える）。
_TOKEN_URL = "https://github.com/login/oauth/access_token"
_USER_API_URL = "https://api.github.com/user"


@pytest.fixture(autouse=True)
async def http_client_lifespan() -> AsyncIterator[None]:
    """各テストで共有 httpx クライアントを開閉する（services が get_http_client を呼ぶため）。"""
    await open_http_client()
    yield
    await close_http_client()


def _stub_token_ok(token: str = "gho_dummy_token") -> respx.Route:
    return respx.post(_TOKEN_URL).respond(
        200,
        json={"access_token": token, "token_type": "bearer", "scope": ""},
    )


def _stub_user_ok(
    *,
    id_: int = 12345,
    name: str | None = "Taro Yamada",
    login: str = "taro",
    email: str | None = "taro@example.com",
) -> respx.Route:
    return respx.get(_USER_API_URL).respond(
        200,
        json={"id": id_, "name": name, "login": login, "email": email},
    )


class TestBuildAuthorizeUrl:
    def test_正常系_stateとclient_idとredirect_uriがクエリに含まれる(self) -> None:
        client = GitHubOAuthClient()
        url = client.build_authorize_url(state="abc-state-token")
        assert url.startswith("https://github.com/login/oauth/authorize?")
        assert "state=abc-state-token" in url
        assert "client_id=" in url
        assert "redirect_uri=" in url


class TestExchangeCodeHappy:
    @respx.mock
    async def test_正常系_nameが入っていればdisplay_nameはname(self) -> None:
        _stub_token_ok()
        _stub_user_ok(name="Taro Yamada", login="taro")

        result = await GitHubOAuthClient().exchange_code(code="ok-code")
        assert result.provider_id == "12345"
        assert result.display_name == "Taro Yamada"
        assert result.email == "taro@example.com"

    @respx.mock
    async def test_正常系_nameがNoneならloginにフォールバック(self) -> None:
        _stub_token_ok()
        _stub_user_ok(name=None, login="taro")

        result = await GitHubOAuthClient().exchange_code(code="ok-code")
        assert result.display_name == "taro"

    @respx.mock
    async def test_正常系_nameが空白のみでもloginにフォールバック(self) -> None:
        _stub_token_ok()
        _stub_user_ok(name="   ", login="taro")

        result = await GitHubOAuthClient().exchange_code(code="ok-code")
        assert result.display_name == "taro"

    @respx.mock
    async def test_正常系_emailがNoneならNoneのまま保存(self) -> None:
        _stub_token_ok()
        _stub_user_ok(email=None)

        result = await GitHubOAuthClient().exchange_code(code="ok-code")
        assert result.email is None

    @respx.mock
    async def test_正常系_emailが空文字でもNoneに正規化(self) -> None:
        _stub_token_ok()
        _stub_user_ok(email="")

        result = await GitHubOAuthClient().exchange_code(code="ok-code")
        assert result.email is None


class TestExchangeCodeTokenErrors:
    @respx.mock
    async def test_異常系_token_endpointが非200ならGitHubOAuthError(self) -> None:
        respx.post(_TOKEN_URL).respond(500, text="server error")

        with pytest.raises(GitHubOAuthError):
            await GitHubOAuthClient().exchange_code(code="bad")

    @respx.mock
    async def test_異常系_token_endpointがJSONを返さない(self) -> None:
        """rate limit や障害で HTML / text が返るケース。"""
        respx.post(_TOKEN_URL).respond(
            200,
            text="<html>rate limited</html>",
            headers={"content-type": "text/html"},
        )

        with pytest.raises(GitHubOAuthError):
            await GitHubOAuthClient().exchange_code(code="bad")

    @respx.mock
    async def test_異常系_token_endpointが200_errorフィールド付き(self) -> None:
        """code が無効な時 GitHub は 200 で error ボディを返す仕様。"""
        respx.post(_TOKEN_URL).respond(
            200,
            json={"error": "bad_verification_code", "error_description": "..."},
        )

        with pytest.raises(GitHubOAuthError):
            await GitHubOAuthClient().exchange_code(code="bad")

    @respx.mock
    async def test_異常系_token_endpointにaccess_tokenが含まれない(self) -> None:
        respx.post(_TOKEN_URL).respond(200, json={"token_type": "bearer"})

        with pytest.raises(GitHubOAuthError):
            await GitHubOAuthClient().exchange_code(code="bad")


class TestExchangeCodeUserErrors:
    @respx.mock
    async def test_異常系_user_endpointが非200ならGitHubOAuthError(self) -> None:
        _stub_token_ok()
        respx.get(_USER_API_URL).respond(403, json={"message": "forbidden"})

        with pytest.raises(GitHubOAuthError):
            await GitHubOAuthClient().exchange_code(code="ok-code")

    @respx.mock
    async def test_異常系_user_endpointがJSONを返さない(self) -> None:
        _stub_token_ok()
        respx.get(_USER_API_URL).respond(200, text="not json")

        with pytest.raises(GitHubOAuthError):
            await GitHubOAuthClient().exchange_code(code="ok-code")

    @respx.mock
    async def test_異常系_idが整数でないとGitHubOAuthError(self) -> None:
        """壊れたレスポンスで provider_id 不正を保存前に弾く。"""
        _stub_token_ok()
        respx.get(_USER_API_URL).respond(
            200,
            json={"id": "not-int", "name": "x", "login": "y"},
        )

        with pytest.raises(GitHubOAuthError):
            await GitHubOAuthClient().exchange_code(code="ok-code")

    @respx.mock
    async def test_異常系_nameもloginも欠落ならGitHubOAuthError(self) -> None:
        """display_name が決まらないので fail-fast。"""
        _stub_token_ok()
        respx.get(_USER_API_URL).respond(
            200,
            json={"id": 1, "name": None, "login": None},
        )

        with pytest.raises(GitHubOAuthError):
            await GitHubOAuthClient().exchange_code(code="ok-code")


class TestExchangeCodeRequestPayload:
    @respx.mock
    async def test_正常系_token_endpoint呼び出しにUserAgentが付く(self) -> None:
        """GitHub REST API は User-Agent 必須（無いと 403）。"""
        token_route = _stub_token_ok()
        _stub_user_ok()

        await GitHubOAuthClient().exchange_code(code="ok-code")

        # 直近の request の headers に User-Agent が入っていることを確認。
        assert token_route.called
        sent: httpx.Request = token_route.calls.last.request
        assert "user-agent" in {k.lower() for k in sent.headers}
