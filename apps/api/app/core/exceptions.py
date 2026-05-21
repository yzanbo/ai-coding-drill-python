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

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

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


class ProblemNotFoundError(DomainError):
    """指定の problemId が存在しない / ソフトデリート済みの時に投げる。

    HTTP では 404 に変換する。problems はゲスト閲覧可能だが、
    存在しないものは認証有無に関わらず 404（problem-display-and-answer.md §受け入れ条件）。
    """


class SubmissionNotFoundError(DomainError):
    """指定の submissionId が自分のもの（user_id 一致）として存在しない時に投げる。

    HTTP では 404 に変換する。情報漏洩防止のため「他人の submission」と
    「存在しない submission」を区別しないメッセージで統一する
    （grading.md §受け入れ条件「他ユーザーの submissions/:id には 403 / 404」）。
    """


class GenerationRequestNotRetryableError(DomainError):
    """generation_request の retry が許されない状態（failed 以外）で呼ばれた時に投げる。

    HTTP では 409 Conflict に変換する。理由：
      - 404 は「リソース不存在」を意味し、所有権チェックは別途 404 で行うため
        混同しないようにする
      - 状態遷移の許容性を返す API のため 409（Conflict）が意味的に正しい
    """

    def __init__(self, current_status: str) -> None:
        super().__init__()
        self.current_status = current_status


# ----------------------------------------------------------------------------
# handler 群
# ----------------------------------------------------------------------------


# JSONResponse: FastAPI が標準で使う JSON 形式のレスポンス。
# status: HTTP ステータスコードの定数群（fastapi が starlette の同名モジュールを
#         そのまま re-export している）。
async def _generation_request_not_found_handler(
    _request: Request,
    _exc: GenerationRequestNotFoundError,
) -> JSONResponse:
    """GenerationRequestNotFoundError → 404 JSON レスポンスに変換。"""
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": "指定された生成リクエストが見つかりません"},
    )


async def _problem_not_found_handler(
    _request: Request,
    _exc: ProblemNotFoundError,
) -> JSONResponse:
    """ProblemNotFoundError → 404 JSON レスポンスに変換。"""
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": "指定された問題が見つかりません"},
    )


async def _submission_not_found_handler(
    _request: Request,
    _exc: SubmissionNotFoundError,
) -> JSONResponse:
    """SubmissionNotFoundError → 404 JSON レスポンスに変換。"""
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": "指定された解答が見つかりません"},
    )


async def _generation_request_not_retryable_handler(
    _request: Request,
    exc: GenerationRequestNotRetryableError,
) -> JSONResponse:
    """NotRetryable → 409 Conflict に変換。detail に現状 status を含める。"""
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "detail": (
                f"generation request is not retryable (status={exc.current_status})"
            ),
        },
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
    app.add_exception_handler(
        ProblemNotFoundError,
        _problem_not_found_handler,  # type: ignore[arg-type]
    )
    app.add_exception_handler(
        SubmissionNotFoundError,
        _submission_not_found_handler,  # type: ignore[arg-type]
    )
    app.add_exception_handler(
        GenerationRequestNotRetryableError,
        _generation_request_not_retryable_handler,  # type: ignore[arg-type]
    )
