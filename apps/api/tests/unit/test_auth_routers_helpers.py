# routers/auth.py 内の純粋関数 _safe_next_path と、
# schemas/auth.AuthErrorKind の最低限の契約をテストする。
#
# 関わる要件：
#   - authentication.md §2.5 バリデーション（next の同一オリジン縛り）

from app.routers.auth import _safe_next_path
from app.schemas.auth import AuthErrorKind


class TestSafeNextPath:
    def test_正常系_スラッシュ始まりの相対パスはそのまま返る(self) -> None:
        assert _safe_next_path("/problems") == "/problems"

    def test_正常系_クエリ付きでもそのまま返る(self) -> None:
        assert _safe_next_path("/problems?cat=easy") == "/problems?cat=easy"

    def test_正常系_None指定は黙ってホームへフォールバック(self) -> None:
        assert _safe_next_path(None) == "/"

    def test_正常系_空文字も黙ってホームへフォールバック(self) -> None:
        assert _safe_next_path("") == "/"

    def test_異常系_protocol_relativeはホームへフォールバック(self) -> None:
        """//evil.com を弾く（オープンリダイレクト対策）。"""
        assert _safe_next_path("//evil.com") == "/"

    def test_異常系_httpsの絶対URLはホームへフォールバック(self) -> None:
        assert _safe_next_path("https://evil.com/x") == "/"

    def test_異常系_httpの絶対URLもホームへフォールバック(self) -> None:
        assert _safe_next_path("http://evil.com/x") == "/"

    def test_異常系_スラッシュ始まりでない相対パスはホームへ(self) -> None:
        assert _safe_next_path("problems") == "/"

    def test_異常系_2048文字超はホームへフォールバック(self) -> None:
        """ログ汚染・ヘッダー注入の軽い前段フィルタ。"""
        huge = "/" + ("a" * 2048)
        assert _safe_next_path(huge) == "/"


class TestAuthErrorKind:
    def test_OAUTH_CANCELEDの文字列値(self) -> None:
        assert AuthErrorKind.OAUTH_CANCELED.value == "oauth_canceled"

    def test_OAUTH_FAILEDの文字列値(self) -> None:
        assert AuthErrorKind.OAUTH_FAILED.value == "oauth_failed"

    def test_STATE_INVALIDの文字列値(self) -> None:
        assert AuthErrorKind.STATE_INVALID.value == "state_invalid"

    def test_StrEnumとしてstrのサブクラス(self) -> None:
        """f-string や urlencode で文字列として扱える契約。"""
        assert isinstance(AuthErrorKind.OAUTH_CANCELED, str)
