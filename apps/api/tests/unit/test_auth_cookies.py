# core/cookies.sign_sid / unsign_sid のユニットテスト。
#
# テスト方針：
#   - 実 Serializer（itsdangerous.URLSafeSerializer）を使う。秘密鍵は
#     get_settings().session_signing_secret（.env の dev 値）をそのまま使う
#     ため、Settings のキャッシュには触らない
#   - 改ざん / 不正形式 / 長さ上限を検証
#
# 関わる要件：
#   - authentication.md §1.3 セッション（Cookie 署名は実装ディテール）

from app.core.cookies import sign_sid, unsign_sid


class TestSignUnsignSidRoundTrip:
    def test_正常系_署名と復号で同じ値が戻る(self) -> None:
        """sign → unsign の round-trip で元の sid が一致する。"""
        original = "abc123_token_urlsafe_dummy"
        signed = sign_sid(original)
        assert unsign_sid(signed) == original

    def test_正常系_署名値は元の値と異なる(self) -> None:
        """署名済み Cookie 値は生 sid と別文字列（itsdangerous が "." で連結する形）。"""
        original = "abc123"
        signed = sign_sid(original)
        assert signed != original
        assert "." in signed


class TestUnsignSidInvalid:
    def test_異常系_空文字はNone(self) -> None:
        assert unsign_sid("") is None

    def test_異常系_改ざんされた値はNone(self) -> None:
        """末尾 1 文字を書き換えた値は BadSignature → None に変換される。"""
        signed = sign_sid("abc123")
        tampered = signed[:-1] + ("Z" if signed[-1] != "Z" else "A")
        assert unsign_sid(tampered) is None

    def test_異常系_無関係なゴミ文字列はNone(self) -> None:
        """署名形式に従わない値も None。"""
        assert unsign_sid("not-a-signed-value") is None

    def test_異常系_1024文字超は早期Noneで弾く(self) -> None:
        """DoS ガード（itsdangerous に渡す前に長さで弾く）。"""
        huge = "x" * 2000
        assert unsign_sid(huge) is None
