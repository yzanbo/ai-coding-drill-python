# problems テーブル：LLM が生成し、サンドボックス検証 + Judge 評価を通った問題。
#   本テーブルへの書き込みは Worker（apps/workers/grading が R1〜R6 兼務、
#   R7 以降は apps/workers/generation に分離）が担当する。
#   Backend は本 PR では「問題が完成したかどうかを generation_requests 経由で
#   返す」読み取り側に立ち、本テーブルへの直接書き込みは行わない。
#
# 関わる要件：
#   - docs/requirements/4-features/problem-generation.md
#   - docs/requirements/3-cross-cutting/01-data-model.md（ER 図 + ソフトデリート方針）

import uuid
from datetime import datetime

from sqlalchemy import String, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Problem(Base):
    """LLM 生成 + サンドボックス検証 + Judge 評価を通った TypeScript 問題。

    ## カラム
    - id                 : UUID（gen_random_uuid()）
    - title              : 一覧表示用の短いタイトル（255 文字）
    - description        : 問題本文（Markdown）。長文を想定して上限なし
    - category           : "string" / "array" / "recursion" / "async" / "type-puzzle"
                           （許可値は問題生成リクエストのバリデーションで縛る、
                           DB は方針変更に追随しやすいよう VARCHAR で受ける）
    - difficulty         : "easy" / "medium" / "hard"
    - language           : "typescript" のみ MVP（将来拡張のため文字列で持つ）
    - examples           : 入出力例（[{ input, output, explanation? }, ...]）
    - test_cases         : 検証用テストケース（[{ input, expected }, ...]）
    - reference_solution : 模範解答 TS コード
    - judge_scores       : Judge LLM の評価スコア（5 軸 + コメント）
    - created_at         : 作成時刻
    - updated_at         : 最終更新時刻（問題修正・公開停止等で書き換わる）
    - deleted_at         : ソフトデリート印。NULL = 生きている行、非 NULL = 削除済
                           （ADR 0048、users / problems / submissions が対象）

    ## 設計メモ
    - 本 PR ではモデル定義のみ。INSERT は Worker（次 PR）の責務
    - インデックスは MVP では張らない（一覧クエリは R1-4 で初めて発生、
      着手時に `(category, difficulty, created_at DESC) WHERE deleted_at IS NULL` 等を追加）
    """

    __tablename__ = "problems"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(16), nullable=False)
    language: Mapped[str] = mapped_column(String(32), nullable=False)
    examples: Mapped[list[dict]] = mapped_column(JSONB, nullable=False)
    test_cases: Mapped[list[dict]] = mapped_column(JSONB, nullable=False)
    reference_solution: Mapped[str] = mapped_column(String, nullable=False)
    judge_scores: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )
    # deleted_at: NULL = 生きている / 非 NULL = 削除済（ADR 0048 のソフトデリート）。
    #   クエリ側で WHERE deleted_at IS NULL を明示的に書く（暗黙フィルタは使わない）。
    deleted_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
