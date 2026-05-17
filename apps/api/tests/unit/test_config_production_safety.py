# core/config.Settings._check_production_safety のユニットテスト。
#
# テスト方針：
#   - Settings() は .env を読み込むため、引数を明示して .env / 環境変数を上書きする
#     （Pydantic v2 では __init__ に渡した値が env_file より優先される）
#   - 各ケースで「production + 1 項目だけ NG」のように単一変数を変えて差分検証
#
# 関わる要件：
#   - 01-non-functional.md §セキュリティ「本番デフォルト値の安全装置」

import pytest
from pydantic import ValidationError

from app.core.config import Settings

# 32 文字ぴったりの強い鍵（ダミー）。production チェックを素通りさせる用。
_STRONG_SECRET = "x" * 32


def _make_settings(**overrides: object) -> Settings:
    """安全側の本番設定を作る。overrides で個別フィールドを差し替える。"""
    base: dict[str, object] = {
        "app_env": "production",
        "session_signing_secret": _STRONG_SECRET,
        "cookie_secure": True,
        "github_client_id": "dummy-client-id",
        "github_client_secret": "dummy-client-secret",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


class TestProductionSafetyDevEnv:
    def test_正常系_devではpaceholderが残っていても素通り(self) -> None:
        """dev / test / staging では安全装置は発動しない。"""
        Settings(
            app_env="dev",
            session_signing_secret="dev-only-change-me",
            cookie_secure=False,
            github_client_id="",
            github_client_secret="",
        )

    def test_正常系_stagingでも素通り(self) -> None:
        Settings(
            app_env="staging",
            session_signing_secret="dev-only-change-me",
            cookie_secure=False,
        )


class TestProductionSafetyHappy:
    def test_正常系_本番要件を全て満たせば起動できる(self) -> None:
        s = _make_settings()
        assert s.app_env == "production"
        assert s.cookie_secure is True


class TestProductionSafetyReject:
    def test_異常系_本番でdev_placeholderが残っていると起動拒否(self) -> None:
        with pytest.raises(ValidationError) as exc:
            _make_settings(session_signing_secret="dev-only-change-me")
        assert "SESSION_SIGNING_SECRET" in str(exc.value)

    def test_異常系_本番で署名鍵が32文字未満だと起動拒否(self) -> None:
        with pytest.raises(ValidationError) as exc:
            _make_settings(session_signing_secret="x" * 31)
        assert "at least" in str(exc.value)

    def test_異常系_本番でCOOKIE_SECUREがfalseだと起動拒否(self) -> None:
        with pytest.raises(ValidationError) as exc:
            _make_settings(cookie_secure=False)
        assert "COOKIE_SECURE" in str(exc.value)

    def test_異常系_本番でGITHUB_CLIENT_ID空欄だと起動拒否(self) -> None:
        with pytest.raises(ValidationError) as exc:
            _make_settings(github_client_id="")
        assert "GITHUB_CLIENT_ID" in str(exc.value)

    def test_異常系_本番でGITHUB_CLIENT_SECRET空欄だと起動拒否(self) -> None:
        with pytest.raises(ValidationError) as exc:
            _make_settings(github_client_secret="")
        assert "GITHUB_CLIENT_SECRET" in str(exc.value)
