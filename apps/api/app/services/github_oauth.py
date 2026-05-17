# このファイルの役割：
#   GitHub OAuth フローのプロバイダ固有部分（URL 組み立て / code↔token 交換 /
#   ユーザー情報取得）を 1 箇所にまとめる。
#
# 設計：
#   - ADR 0011 の「拡張容易性のための 3 つの設計」のうち
#     「OAuth クライアント抽象に沿う」を実体化したクラス
#   - 将来 GoogleOAuthClient 等を追加するときは同じインタフェース（authorize URL を返す、
#     code から UserSyncInput を返す）でこのクラスと並列に書く
#   - state は外部（core/state_store.py）が管理。本クラスは渡された state を URL に
#     乗せるだけ（責務分離）
#
# 関わる要件：
#   - docs/requirements/4-features/authentication.md §2.1 / §2.3

# urlencode: クエリ文字列を組み立てる Python 標準。
from urllib.parse import urlencode

# get_http_client: アプリ起動時に開かれた共有 httpx.AsyncClient を取得する。
#   1 リクエストごとに新規 client を作らず、接続プールを再利用する。
from app.core.config import get_settings
from app.core.http_client import get_http_client
from app.schemas.auth import UserSyncInput

# GitHub の OAuth エンドポイント（公式ドキュメント記載の固定値）。
_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
_TOKEN_URL = "https://github.com/login/oauth/access_token"
_USER_API_URL = "https://api.github.com/user"

# User-Agent: GitHub REST API は User-Agent ヘッダーを必須化している
#   （無いと 403 で弾かれる）。アプリ識別できる固定値を渡しておく。
#   公式ドキュメント：https://docs.github.com/en/rest/overview/resources-in-the-rest-api#user-agent-required
_USER_AGENT = "ai-coding-drill"


class GitHubOAuthError(Exception):
    """GitHub OAuth フロー中のエラー。Router 側でハンドリングしてリダイレクトを返す。"""


class GitHubOAuthClient:
    """GitHub OAuth のプロバイダ実装。

    使い方：
        client = GitHubOAuthClient()
        url = client.build_authorize_url(state="...")           # 認可画面へ送る URL
        user_input = await client.exchange_code(code="...")     # 戻ってきた code → ユーザー情報
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._client_id = settings.github_client_id
        self._client_secret = settings.github_client_secret
        self._redirect_uri = settings.github_redirect_uri

    def build_authorize_url(self, *, state: str) -> str:
        """GitHub の認可画面に飛ばす URL を組み立てる。

        - scope は指定しない（authentication.md §2.1）。
          公開 email のユーザーからのみ email を取得する方針で、認可画面の摩擦を最小化。
        - state は core/state_store.py で発行した CSRF トークンを渡す。
        """
        params = {
            "client_id": self._client_id,
            "redirect_uri": self._redirect_uri,
            "state": state,
            # allow_signup=true（既定）で初回ユーザーも GitHub 側で新規登録できる。
            # 明示しない（GitHub 側既定が望ましい挙動）。
        }
        return f"{_AUTHORIZE_URL}?{urlencode(params)}"

    async def exchange_code(self, *, code: str) -> UserSyncInput:
        """GitHub から戻ってきた認可コードを使い、ユーザー情報まで一気に取得する。

        2 ステップ：
          1. POST /login/oauth/access_token に code を渡して access_token を得る
          2. GET /api/user に access_token を付けてプロフィールを取る

        - 取得した name / login / email から UserSyncInput を組み立てて返す
          （display_name は name → login の順でフォールバック、authentication.md §2.1）
        - 失敗時は GitHubOAuthError を raise（Router 側でキャッチして /login?auth_error=...）
        """
        # 共有 httpx クライアントを取得（lifespan で 1 個だけ作られた接続プール
        # を使い回す）。timeout 設定は core/http_client.py 側に集約済み。
        http = get_http_client()

        # 1. code → access_token 交換
        # GitHub は Accept: application/json を付けると JSON で返してくれる。
        # 付けないと form-encoded で返るため、明示的に JSON を要求する。
        token_resp = await http.post(
            _TOKEN_URL,
            data={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "code": code,
                "redirect_uri": self._redirect_uri,
            },
            headers={
                "Accept": "application/json",
                "User-Agent": _USER_AGENT,
            },
        )
        if token_resp.status_code != 200:
            raise GitHubOAuthError(
                f"GitHub token endpoint returned {token_resp.status_code}"
            )

        try:
            token_body = token_resp.json()
        except ValueError as exc:
            # rate limit や障害で HTML / プレーンテキストが返ることがある。
            # 仕様外の応答は OAuth フロー全体を失敗扱いにする。
            raise GitHubOAuthError(
                "GitHub token response is not JSON"
            ) from exc
        # GitHub は code が無効でも 200 を返して body に "error" を入れてくることがある
        # （仕様）。Bearer 失敗の隠れた経路なので明示的に弾く。
        if "error" in token_body:
            detail = token_body.get("error_description") or token_body["error"]
            raise GitHubOAuthError(f"GitHub token error: {detail}")

        access_token = token_body.get("access_token")
        if not access_token:
            raise GitHubOAuthError("GitHub token response missing access_token")

        # 2. access_token → user 情報
        # X-GitHub-Api-Version は固定（OAuth User API はバージョン未指定でも動くが
        # 互換性事故回避のため固定）。Authorization は token <value> 形式（OAuth Apps 慣習）。
        user_resp = await http.get(
            _USER_API_URL,
            headers={
                "Authorization": f"token {access_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": _USER_AGENT,
            },
        )
        if user_resp.status_code != 200:
            raise GitHubOAuthError(
                f"GitHub user endpoint returned {user_resp.status_code}"
            )
        try:
            user_body = user_resp.json()
        except ValueError as exc:
            raise GitHubOAuthError(
                "GitHub user response is not JSON"
            ) from exc

        # provider_id: GitHub の id は int。文字列化して auth_providers.provider_id に保存。
        # API が壊れた応答（id が文字列 / null / 欠落）を返したケースも明示的に弾く。
        gh_id = user_body.get("id")
        if not isinstance(gh_id, int):
            raise GitHubOAuthError("GitHub user response has invalid id")

        # display_name: name → login の順でフォールバック（authentication.md §2.1）。
        # name は null や空文字列があり得るので両方を弾く。
        name = user_body.get("name")
        login = user_body.get("login")
        if isinstance(name, str) and name.strip():
            display_name = name.strip()
        elif isinstance(login, str) and login:
            display_name = login
        else:
            # 仕様上 login は必ず存在するはず。万一来なかったらエラーで弾く
            # （以降の DB 保存で NOT NULL に引っかかる前に明示）。
            raise GitHubOAuthError("GitHub user response missing name and login")

        # email: 公開設定のユーザーだけ値が入る。それ以外は None。
        email_raw = user_body.get("email")
        email = email_raw if isinstance(email_raw, str) and email_raw else None

        return UserSyncInput(
            provider_id=str(gh_id),
            display_name=display_name,
            email=email,
        )
