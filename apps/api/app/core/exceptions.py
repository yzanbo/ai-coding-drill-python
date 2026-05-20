# このファイルの役割：
#   業務的なエラー（リソースが見つからない / 権限が足りない / 状態が不正 等）を
#   表すドメイン例外と、それらを HTTP レスポンスに変換する handler を集約する。
#
# なぜ services 側で HTTPException を直接 raise しないか：
#   services/* が FastAPI の HTTP 層に依存すると、テスト・バッチ処理・Worker 等
#   HTTP 文脈外から呼べなくなる。services はドメイン例外を投げるだけにして、
#   HTTP への翻訳は本ファイルの handler で 1 箇所に集約する。
#   詳細は app/core/README.md §2 と .claude/rules/backend.md §Service を参照。
#
# 関連：
#   - .claude/rules/backend.md
#   - app/core/README.md §2 ドメイン例外クラス

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette import status

# ----------------------------------------------------------------------------
# ドメイン例外
# ----------------------------------------------------------------------------


class DomainError(Exception):
    """ドメイン例外の共通基底。

    handler 登録時に isinstance 判定を共通化したい時に使う。
    具体例外はこのクラスを継承して定義する。
    """


class GenerationRequestNotFoundError(DomainError):
    """指定の requestId が自分のもの（user_id 一致）として存在しない時に投げる。

    HTTP では 404 に変換する。情報漏洩防止のため「他人のリクエスト」と
    「存在しないリクエスト」を区別しないメッセージで統一する
    （problem-generation.md §画面）。
    """


# ----------------------------------------------------------------------------
# handler 群
# ----------------------------------------------------------------------------


# JSONResponse: FastAPI が標準で使う JSON 形式のレスポンス。
# starlette.status: HTTP ステータスコードの定数群。
async def _generation_request_not_found_handler(
    _request: Request,
    _exc: GenerationRequestNotFoundError,
) -> JSONResponse:
    """GenerationRequestNotFoundError → 404 JSON レスポンスに変換。"""
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": "指定された生成リクエストが見つかりません"},
    )


# ----------------------------------------------------------------------------
# 一括登録
# ----------------------------------------------------------------------------


def register_exception_handlers(app: FastAPI) -> None:
    """ドメイン例外ハンドラを FastAPI アプリにまとめて登録する。

    main.py から呼ぶ。新しいドメイン例外を追加したら、本関数内に
    app.add_exception_handler(...) を 1 行追加する。
    """
    app.add_exception_handler(
        GenerationRequestNotFoundError,
        _generation_request_not_found_handler,  # type: ignore[arg-type]
    )
