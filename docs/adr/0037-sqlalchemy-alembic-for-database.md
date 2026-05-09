# 0037. DB ORM・マイグレーションに SQLAlchemy 2.0（async）+ Alembic を採用

- **Status**: Accepted
- **Date**: 2026-05-09
- **Decision-makers**: 神保 陽平

## Context（背景・課題）

[ADR 0033](./0033-backend-language-pivot-to-python.md) でバックエンドを Python に pivot した結果、TS 版で採用していた **Drizzle ORM**（[ADR 0017](./0017-drizzle-orm-over-prisma.md)、Superseded by 0033）が使えなくなった。Python 側の **ORM とマイグレーションツールを選定**する必要がある。

選定にあたっての制約・要請：

- **async ネイティブ**：FastAPI（[ADR 0034](./0034-fastapi-for-backend.md)）と LLM SDK の async 親和性に合わせ、DB 層も async/await で記述したい
- **型安全性**：Pyright（[ADR 0020](./0020-python-code-quality.md)）で型チェックが効くこと
- **Postgres ジョブキュー対応**：`SELECT FOR UPDATE SKIP LOCKED` / `LISTEN/NOTIFY`（→ [ADR 0004](./0004-postgres-as-job-queue.md)）が ORM 越しでも自然に書けること、必要なら生 SQL に降りられること
- **マイグレーション運用**：Drizzle で確立した「スキーマ変更 → マイグレーションファイル生成 → 適用」のフローを Python でも維持
- **エコシステム成熟度**：production 採用実績、IDE 補完、breaking change への対応速度

判断のために参照した情報源：

- [FastAPI with Async SQLAlchemy, SQLModel, and Alembic - TestDriven.io](https://testdriven.io/blog/fastapi-sqlmodel/)
- [FastAPI + SQLAlchemy 2.0: Modern Async Patterns](https://dev-faizan.medium.com/fastapi-sqlalchemy-2-0-modern-async-database-patterns-7879d39b6843)
- [Patterns and Practices for using SQLAlchemy 2.0 with FastAPI](https://chaoticengineer.hashnode.dev/fastapi-sqlalchemy)

## Decision（決定内容）

DB アクセスとマイグレーションに **SQLAlchemy 2.0（async）+ Alembic** を採用する。

- **ORM**：`sqlalchemy[asyncio]` 2.x（`AsyncEngine` / `AsyncSession`）
- **マイグレーション**：`alembic`（SQLAlchemy 標準ペア）
- **接続ドライバ**：`asyncpg`（Postgres 用 async ドライバ）
- **モデル定義**：SQLAlchemy 2.0 の `DeclarativeBase` + `Mapped[T]` 型注釈方式（Pyright で型推論が効く新スタイル）
- **Pydantic との分離**：DB モデル（SQLAlchemy）と API スキーマ（Pydantic）を**別レイヤとして明示的に分離**（FastAPI コミュニティ慣習に従う）
- **ジョブキュー用クエリ**：`SELECT FOR UPDATE SKIP LOCKED` 等は SQLAlchemy Core / `text()` で生 SQL を埋め込む方針（→ [ADR 0004](./0004-postgres-as-job-queue.md)）
- **マイグレーションコミット方針**：自動生成された Alembic スクリプトは git 管理し、内容を必ず人間レビューする（[ADR 0017](./0017-drizzle-orm-over-prisma.md) で確立した思想を継承）

## Why（採用理由）

### 1. async API が成熟（2.0 で完全書き直し）

- SQLAlchemy 2.0 で **async API が完全リファクタリング**され、`AsyncEngine` / `AsyncSession` が production 安定
- FastAPI（async ネイティブ）+ asyncpg + SQLAlchemy 2.0 async の組み合わせは 2026 年の Python web 標準スタック
- LLM プロバイダ呼び出し（[ADR 0007](./0007-llm-provider-abstraction.md)）と DB I/O が同じ async コンテキストで並列化できる

### 2. Pyright での型推論が効く

- `Mapped[T]` / `mapped_column()` 方式により、カラム型 → Pyright の型推論が完全に伝播
- SQLAlchemy 2.0 の `select()` / `Result` API は型ヒント前提で設計されており、IDE 補完が実用域
- Pyright `strict` モード（[ADR 0020](./0020-python-code-quality.md)）への引き上げに耐える型表現

### 3. Postgres 高度機能への自然なアクセス

- `LISTEN/NOTIFY` / `SELECT FOR UPDATE SKIP LOCKED` / 部分インデックス / JSONB 演算子等の **Postgres 固有機能**が Core API / `text()` で素直に書ける
- ORM 抽象化に縛られず、必要に応じて生 SQL に降りられる柔軟性は Drizzle 採用判断（[ADR 0017](./0017-drizzle-orm-over-prisma.md)）と同じ思想
- ジョブキュー実装（[ADR 0004](./0004-postgres-as-job-queue.md)）で Postgres 固有機能を多用する本プロジェクトに適合

### 4. Alembic は SQLAlchemy 標準ペア

- SQLAlchemy 作者陣が開発するマイグレーションツール、両者の整合性が保証される
- `--autogenerate` でモデル定義差分からマイグレーションスクリプトを生成
- 生成スクリプトは Python ファイルなので diff レビュー可能、複雑な migration（データ移行付き等）も同じ枠組みで書ける
- Drizzle Kit の `drizzle-kit generate` 相当の運用感

### 5. エコシステム最大手

- Python ORM の事実上のスタンダード、**production 実績は他の追随を許さない**
- Stack Overflow / GitHub issue / 公式ドキュメントの量が圧倒的、トラブルシュートが容易
- 採用面接でも「SQLAlchemy 経験」は標準的に問われる、portfolio 価値が高い

## Alternatives Considered（検討した代替案）

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| **SQLAlchemy 2.0 + Alembic（採用）** | Python ORM デファクト + 標準マイグレーション | — |
| SQLModel + Alembic | FastAPI 作者製、Pydantic と SQLAlchemy を統合（モデル定義 = API スキーマ） | 型統合の美しさは魅力的だが、(1) **「SQLAlchemy / Pydantic 最新機能の追従が遅れている」**との 2026 年評価、(2) PostgreSQL async 操作のドキュメントが手薄、(3) FastAPI コミュニティ慣習として「DB モデルと API スキーマは分離する」のが大規模化に強いとされる |
| Tortoise ORM | Django 風 API、async ネイティブ | エコシステムが SQLAlchemy より小さい、Pyright 対応も薄い、Postgres 高度機能対応が弱い |
| Piccolo ORM | async ネイティブ、type-safe を謳う新興 | エコシステム未成熟、Alembic 相当のマイグレーションツールも自前で運用実績が浅い |
| 生 SQL + asyncpg | ORM を使わず生 SQL のみ | 型安全性が脆い、マイグレーション運用を自前で構築する必要、ボイラープレートが増える |
| Django ORM | Django 同梱の ORM | FastAPI と組み合わせる事例少、Django 全体の導入を強いる |
| peewee | 軽量 ORM | async 対応が不完全、Postgres 固有機能が弱い |

## Consequences（結果・トレードオフ）

### 得られるもの

- **async DB アクセス**：FastAPI と LLM SDK と並列性を活かす I/O 設計が可能
- **Pyright で型推論が効く**：`Mapped[T]` 方式により ORM 利用箇所まで型が通る
- **Postgres 高度機能**：ジョブキュー / 部分インデックス / JSONB を ORM 抽象化に縛られず使える
- **マイグレーション運用が ecosystem 標準**：Alembic は SQLAlchemy 公式ペア、トラブル時の情報量が圧倒的
- **採用市場での portfolio 価値**：SQLAlchemy 経験は採用面接で標準的に問われる

### 失うもの・受容するリスク

- **DB モデルと API スキーマの二重定義**：SQLAlchemy（ORM）と Pydantic（API）でモデルを別々に書く必要がある（mapper / converter 層が増える）。SQLModel が解決しようとしていた問題を本 ADR では受け入れる
- **学習コストが Tortoise / Piccolo より高い**：SQLAlchemy 2.0 は Core / ORM 2 層構造、async / sync 両対応で API が広い
- **`Mapped[T]` 新スタイルへの慣れ**：レガシーな `Column()` 直接記述スタイルから移行するためのキャッチアップが必要（ただし新規プロジェクトなので影響軽微）
- **Alembic 自動生成の限界**：複雑なスキーマ変更（カラム rename / データ移行）は手書き補正が必要

### 将来の見直しトリガー

- **SQLModel の async / Pyright サポートが SQLAlchemy 2.0 に追いつく場合** → 「**DB モデルと API スキーマの統合**」価値が再評価可能になるため、SQLModel への移行を検討
- **ORM が運用 pain になる場合**（複雑クエリの ORM 表現が困難 / パフォーマンス問題）→ 生 SQL + asyncpg への部分的移行を検討（SQLAlchemy Core で段階的に降りられるため移行は局所的）
- **Postgres 以外の DB 採用が必要になる場合**（極めて低確率）→ SQLAlchemy は元々 multi-DB 対応のため移行コスト最小

## References

- [ADR 0033: バックエンドを Python に pivot](./0033-backend-language-pivot-to-python.md)（本 ADR の前提）
- [ADR 0034: バックエンド API に FastAPI を採用](./0034-fastapi-for-backend.md)（async DB の前提）
- [ADR 0017: Drizzle ORM 採用](./0017-drizzle-orm-over-prisma.md)（Superseded by 0033、TS 版時点の対応判断、思想は本 ADR が継承）
- [ADR 0004: Postgres をジョブキューに採用](./0004-postgres-as-job-queue.md)（Postgres 固有機能依存の前提）
- [ADR 0007: LLM プロバイダ抽象化](./0007-llm-provider-abstraction.md)（async I/O 並列性の前提）
- [ADR 0020: Python のコード品質ツールに ruff + pyright を採用](./0020-python-code-quality.md)（Pyright で型推論が効く前提）
- [SQLAlchemy 2.0 公式](https://docs.sqlalchemy.org/en/20/)
- [Alembic 公式](https://alembic.sqlalchemy.org/)
- [asyncpg 公式](https://magicstack.github.io/asyncpg/)
- [FastAPI + Async SQLAlchemy + Alembic（TestDriven.io）](https://testdriven.io/blog/fastapi-sqlmodel/)
