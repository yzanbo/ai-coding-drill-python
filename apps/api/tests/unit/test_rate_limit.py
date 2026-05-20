# deps/rate_limit.py の単体テスト。
#   key 関数（認証時 user: / 匿名時 ip: の振り分け）と、429 ハンドラの JSON 形状を見る。
#   実 Redis やフル FastAPI スタックは噛ませない（純粋な関数の検証）。
#
# 関わる要件:
#   - docs/requirements/3-cross-cutting/02-api-conventions.md §レート制限

import json
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from slowapi.errors import RateLimitExceeded

from app.deps.rate_limit import get_rate_limit_key, rate_limit_exceeded_handler


def _make_request(*, user_obj: object | None, client_host: str = "203.0.113.1") -> MagicMock:
    """slowapi の key 関数が読む属性だけ持つ Request のスタブを返す。"""
    # state: FastAPI の Request.state は SimpleNamespace 互換（属性アクセス）。
    state = SimpleNamespace()
    if user_obj is not None:
        state.user = user_obj
    # client.host: get_remote_address が読む属性。X-Forwarded-For が無ければここに倒れる。
    request = MagicMock()
    request.state = state
    request.client = SimpleNamespace(host=client_host)
    request.headers = {}
    return request


class TestGetRateLimitKey:
    def test_正常系_認証済みユーザーは_user_プレフィックスを返す(self) -> None:
        uid = uuid4()
        # user.id だけ持てば十分（SQLAlchemy モデルでなくとも構わない）。
        user = SimpleNamespace(id=uid)
        req = _make_request(user_obj=user)

        key = get_rate_limit_key(req)

        assert key == f"user:{uid}"

    def test_正常系_state_userがNoneなら_ip_プレフィックスを返す(self) -> None:
        req = _make_request(user_obj=None, client_host="198.51.100.7")
        # 明示的に user=None を積んでも IP に倒れる経路を担保。
        req.state.user = None

        key = get_rate_limit_key(req)

        assert key == "ip:198.51.100.7"

    def test_正常系_state_user属性そのものが無くても_ip_プレフィックスに倒れる(self) -> None:
        # 未認証ルート（optional ガードを通っていない）は state.user 自体存在しない。
        # getattr 経由でフォールバックすることを担保。
        req = _make_request(user_obj=None, client_host="198.51.100.42")
        # state から user 属性を抜く（_make_request では追加しない経路）。
        if hasattr(req.state, "user"):
            del req.state.user

        key = get_rate_limit_key(req)

        assert key == "ip:198.51.100.42"


@pytest.mark.asyncio
async def test_正常系_rate_limit_exceeded_handlerは429と日本語detailを返す() -> None:
    """超過時ハンドラのレスポンス形状（429 + JSON + detail 日本語 + limit 文字列同梱）。"""
    # RateLimitExceeded は slowapi のライブラリ例外。message 引数で人間向け文字列を持つ。
    exc = RateLimitExceeded(MagicMock(limit=MagicMock(amount=5, multiples=1)))
    # detail は "5 per 1 minute" 形式の文字列が slowapi 側で組み立てられるが、
    # 本ハンドラはこれを str(exc.detail) で握って limit フィールドに転記するだけ。
    # ここではモック経由で文字列に成形済みのつもりで通す。

    res = await rate_limit_exceeded_handler(MagicMock(), exc)

    assert res.status_code == 429
    # JSONResponse.body は bytes / memoryview を返しうる union 型なので bytes 化してから decode。
    payload = json.loads(bytes(res.body).decode("utf-8"))
    expected = "リクエストが多すぎます。しばらく時間を置いてから再度お試しください。"
    assert payload["detail"] == expected
    assert "limit" in payload
