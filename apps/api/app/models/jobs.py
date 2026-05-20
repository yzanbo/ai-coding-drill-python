# jobs テーブル：Postgres を「ジョブキュー」として使うための中核テーブル。
#   Backend が INSERT（+ NOTIFY）して、Worker が SELECT FOR UPDATE SKIP LOCKED で
#   1 行ずつ取って処理する。外部キューミドルウェア（SQS / Kafka / Redis）は使わない
#   （ADR 0004 / 0005）。
#
# 関わる要件：
#   - docs/requirements/3-cross-cutting/01-data-model.md（ER 図）
#   - docs/requirements/2-foundation/02-architecture.md（ジョブが流れる完全な経路）
#   - docs/adr/0004-postgres-as-job-queue.md
#   - docs/adr/0046-job-queue-delivery-guarantees.md

from datetime import datetime

from sqlalchemy import BigInteger, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Job(Base):
    """ジョブキューの 1 行。

    ## カラム
    - id          : BIGSERIAL（処理順序を直感的に扱うためアプリエンティティと違って数値 ID）
    - queue       : "default" / "grading" / "generation" 等の論理キュー名
    - type        : "problem.generate" / "submission.grade" 等のジョブ種別
                    （type ごとに payload の Pydantic スキーマが対応する、ADR 0006）
    - payload     : ジョブ固有のデータ。スキーマは app/schemas/jobs/<type>.py の
                    Pydantic が SSoT、Worker 側は quicktype 生成の Go struct で読む
    - state       : "queued" / "running" / "succeeded" / "failed"（マシン的状態）
    - attempts    : 試行回数。Worker がリトライするたびに +1（at-least-once、ADR 0046）
    - run_at      : 実行可能時刻。バックオフ時は未来時刻を入れて遅延実行する
    - locked_at   : Worker がロックを取った時刻（タイムアウト判定用）
    - locked_by   : ロックを握っている Worker 識別子
    - last_error  : 直近の失敗メッセージ（運用ログ用）
    - result      : 完了時の結果（任意の JSONB、Worker が書き戻す）
    - created_at  : 投入時刻
    - updated_at  : 最終更新時刻（state 遷移で書き換わる）

    ## 設計メモ
    - インデックス (queue, state, run_at)：Worker 取得クエリ
        SELECT ... WHERE queue=? AND state='queued' AND run_at <= NOW()
        ORDER BY run_at LIMIT 1 FOR UPDATE SKIP LOCKED
      を高速化するために必須（ADR 0004）
    - ハードデリート対象（TTL バッチで物理削除、data-model.md）→ deleted_at なし
    - 配送保証契約（at-least-once / 可視性タイムアウト / リトライ / DLQ）は ADR 0046
    """

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    queue: Mapped[str] = mapped_column(String(64), nullable=False)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    state: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default="queued",
    )
    attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
    )
    run_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )
    locked_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    locked_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
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

    __table_args__ = (
        # Worker の取得クエリ（queue + state + run_at で WHERE する）を高速化。
        Index("ix_jobs_queue_state_run_at", "queue", "state", "run_at"),
    )
