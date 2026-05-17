# 0044. Backend に Repository パターンを採用（Service / Repository / ORM の 3 層分離、ポートフォリオ駆動の判断）

- **Status**: Accepted
- **Date**: 2026-05-17
- **Decision-makers**: 神保

## Context（背景・課題）

apps/api のレイヤ構成は当初、[backend-layers.md](../requirements/5-roadmap/r0-setup/backend-layers.md) と [.claude/rules/backend.md](../../.claude/rules/backend.md) で **Repository 不採用**（Service が `AsyncSession` から SQLAlchemy 2.0 を直接呼ぶ単層構成）と決めていた。当時の不採用根拠は：

- 本 Backend は [ADR 0040](./0040-worker-grouping-and-llm-in-worker.md) により責務が薄い（auth + CRUD + job enqueue + 結果取得のみ。LLM 呼び出しは Worker 側）
- Repository クラスは ORM への delegating wrapper になりやすく ROI が低い
- 複雑クエリが複数 Service で重複し始めたら `app/queries/<feature>.py` の関数群（クラス化しない）に段階的に切り出して対応する

一方、本プロジェクトの最上位目標は **「ポートフォリオとして公開可能な水準で完成させる」**（→ [01-roadmap.md: ビジョン](../requirements/5-roadmap/01-roadmap.md#ビジョン変わらない北極星)）であり、ROI 観点だけでは決定できない領域がある。具体的には：

- 採用面接の評価軸は「設計パターンの理解と使い分けができる」であり、「Service 単層を選んだ判断」を語るより「Repository を明示的に置いた構造を見せて根拠を語る」ほうが**パターン語彙の共有**が即座にできる
- Service / Repository / ORM の 3 層は中・大規模アプリで業界標準であり、面接官が `apps/api/app/repositories/` を見れば**追加の説明なしに**設計意図を読み取れる
- 「ROI が低い」のは事実だが、**学習用・説明可能性を ROI に優先する**判断は本プロジェクトの文脈で正当化できる

この再評価により、当初の「単層構成 + 段階導入」を覆して Repository パターンを最初から採用する。

## Decision（決定内容）

**`apps/api/app/repositories/` を新設し、Router → Service → Repository → ORM の 3 層分離を採用する。** `queries/` の段階導入は廃止し、データアクセスは Repository に統一する。

### 各レイヤの責務

| レイヤ | 責務 | 持たないもの |
|---|---|---|
| `routers/` | HTTP リクエスト / レスポンスの橋渡し、Service の組み立て | DB クエリ・ビジネスロジック |
| `services/` | ビジネスロジック（バリデーション / 計算 / 分岐 / 認可チェック）、トランザクション境界、Pydantic への詰め替え | SQLAlchemy クエリの実体 |
| `repositories/` | SQLAlchemy クエリ実装（`select` / `insert` / `update` / `delete` + `await session.execute(...)`）、ORM オブジェクトを返却 | ビジネスロジック・トランザクション制御・Pydantic への変換 |
| `models/` | SQLAlchemy モデル定義（テーブル設計図） | クエリ・ビジネスロジック |

### 実装パターン

- **1 集約 1 ファイル**：`app/repositories/<feature>.py`、クラス名は `<Feature>Repository`（例：`ProblemRepository` / `SubmissionRepository`）
- **`AsyncSession` は Service が DI で受け取り、Repository に渡す**：`self.repo = <Feature>Repository(session)`
- **トランザクション境界は Service**：`async with session.begin():` ブロック内で Repository メソッドを呼ぶ
- **Repository の戻り値は ORM モデル**：Service 側で `<Feature>Response.model_validate(obj)` に詰め替える（境界を schemas/ に集約、→ [ADR 0006](./0006-json-schema-as-single-source-of-truth.md)）
- **trivial 例外は維持**：`health_check` のような INSERT 1 行 / SELECT 1 行レベルは router 直書きを許容（backend.md step 8 の health 疎通の運用）

### import 方向（追加・更新）

| レイヤ | import してよい | import 禁止 |
|---|---|---|
| `services/` | `repositories` / `schemas` / `models`（型注釈用途のみ）/ `core` | `routers` / `deps` / `db` を直接（DB 操作は repository 経由） |
| `repositories/`（新設） | `models` / `db` / `core` | `services` / `routers` / `schemas`（戻り値は ORM、変換は Service） |

## Why（採用理由）

### 1. ポートフォリオ価値 — 設計パターン語彙の即時共有

- 採用面接で `apps/api/app/repositories/` の存在が**追加説明なしで**「Service / Repository / ORM 分離を理解している」シグナルになる
- Repository は中〜大規模 SaaS のデファクト、業界での認知度が高く、面接官・レビュアー側のメンタルモデルと一致する
- 「単層を選んだ判断」を語るより、「Repository を置く / 置かない判断を比較した結果を語れる」ほうが**設計判断の幅の広さ**を可視化できる

### 2. テスタビリティ — Service / Repository の検査軸が分離

- Service の単体テストで Repository を `AsyncMock` でスタブ化できる（SQLAlchemy 依存なしでビジネスロジック網羅）
- Repository は実 DB（Testcontainers / docker-compose）に対して SQL 挙動だけを検証する責務分担に切り替えられる
- 元の方針（Repository モック不採用 = false positive リスク）は「ORM オブジェクトを Repository を介さず Service が直接扱う」前提に基づく。Repository を**インタフェース境界として明示**すれば、その境界でのモックは false positive を生まない
- ADR 0038 のテスト方針（Repository モック不採用の前提）は本 ADR で更新される（→ §References）

### 3. 責務の明示的分離 — 境界が物理的に別ファイル

- 「ビジネスロジック」と「DB クエリ」が**別ファイル**になり、読み手が責務境界を grep で即特定できる
- Service ファイルから SQLAlchemy 構文が消え、ビジネスルール（バリデーション / 認可 / 分岐）に集中して読める
- 新規参画者（自分自身を含む）の認知負荷低減

### 4. 将来の進化に対する構造的余地

- Repository を `typing.Protocol` でインタフェース化することで、複数実装の差し替え（in-memory / SQL / 外部 API）が構造的に可能になる
- CQRS（Command / Query 分離）への移行余地（`<Feature>QueryRepository` / `<Feature>CommandRepository`）
- 別データソース（S3 / Redis / 外部 API）に対する Repository を作る際、既存パターンに乗せられる

### 5. 「ROI 分析を上書きする判断」の明示

- 本プロジェクトは ROI 最大化が最上位目標ではなく、**ポートフォリオ・学習価値**が最上位目標（→ [01-roadmap.md: ビジョン](../requirements/5-roadmap/01-roadmap.md#ビジョン変わらない北極星)）
- 「ROI が低い」という事実を認めた上で、それでも採用する判断を ADR に明文化することで、**規模に応じた判断 + 例外条件を語れる設計者**という評価軸自体を可視化する
- これは [ADR 0021](./0021-r0-tooling-discipline.md)（補完ツールを R0 から導入）の「遅延の不可逆性が高い判断には YAGNI を適用しない」と同型のメタ判断

## Alternatives Considered（検討した代替案）

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| **Service 単層**（元の決定） | Service が `AsyncSession` から SQLAlchemy 2.0 を直接呼ぶ。Repository は不採用、複雑クエリは `app/queries/<feature>.py` の関数群に段階導入 | ROI 観点では最適だが、ポートフォリオで「分離パターンの理解」を示せない。面接で「なぜ Repository を置かない判断をした？」と聞かれた時、「Backend が薄いから」だけでは設計判断の幅を示しきれない |
| **`queries/` 段階導入**（元の fallback） | 単層 Service の中で、複数 Service で重複し始めた SQL を `queries/<feature>.py` の関数群に切り出す | 「クラス化された明示的レイヤ」より格下扱いされやすい。`def get_problems_by_user(session, user_id) -> list[Problem]:` のような関数群は **Repository を関数で表現したもの**であり、ならば最初からクラスで Repository を作るほうが構造として一貫する |
| **DDD 風 4 層**（presentation / application / domain / infrastructure） | 業界の重量級パターン | apps/api 規模に対して過剰。Aggregate Root / Domain Event / Value Object 等の概念がプロジェクト規模に見合わない。Repository だけ採用してもパターン認知のメリットは取れる |
| **Repository + Unit of Work**（UoW） | Repository に加えて UoW でトランザクション境界を扱う | FastAPI の `Depends` + `AsyncSession` でトランザクション境界が既に表現されており、UoW は機能重複。`async with session.begin():` で十分 |
| **Active Record スタイル**（モデルクラスにクエリメソッドを集約） | `Problem.find_by_id(session, id)` のようにモデル自体にクエリを生やす | SQLAlchemy 2.0 の Mapped[T] 型注釈ベース API と相性が悪く、慣習からも外れる。テストで「モデル + クエリ」が一体化し、純粋データ構造と振る舞いが分離できない |

## Consequences（結果・トレードオフ）

### 得られるもの

- **採用面接で即可視化**：`apps/api/app/repositories/` の存在が「Service / Repository / ORM 分離を理解している」シグナル
- **Service の単体テストが Repository モックで書ける**：SQLAlchemy 依存なしでロジック網羅
- **Repository 単体テストで SQL 挙動の検証に集中**：責務分離テスト
- **読み手の認知負荷低減**：ビジネスロジックと DB クエリが別ファイル、grep で責務境界が即特定
- **将来の置換余地**：in-memory Repository / 別 ORM / 別データソースへの差し替えが構造的に可能

### 失うもの・受容するリスク

- **boilerplate の増加**：薄い CRUD（INSERT 1 行 / SELECT 1 行）でも「Service → Repository」の 1 段が出る
  - **対策**：`health_check` 等の trivial ケースは router 直書きを許容（既存の health 例外を維持）
- **delegating wrapper の頻出**：Repository メソッドが「`session.execute()` を 1 行呼ぶだけ」の状態が頻出
  - **受容**：ポートフォリオ用途では「層が薄くてもパターンとして存在する」事自体が価値。boilerplate を機能の少なさの裏返しとして受容する
- **学習コストの増加**：新規参画者は「なぜ薄くても Repository を置くか」の文脈理解が必要
  - **対策**：[apps/api/app/repositories/README.md](../../apps/api/app/repositories/README.md) に「なぜ薄くても Repository を置くか（ポートフォリオ駆動）」を明記
- **`/backend-new-module` で生成するファイルが 1 つ増える**：models / schemas / services / **repositories** / routers の 5 ファイル
  - **対策**：skill 側のテンプレを更新（→ §References の skill ファイル群）

### 将来の見直しトリガー

- **本番 SaaS としてスケールする段階に到達**し、ポートフォリオ用途を卒業した時。Repository が boilerplate に見えるなら CQRS / 関数群への解体に進む
- **FastAPI / SQLAlchemy 公式が Repository パターンの推奨を更新**した場合（現状はどちらも中立、テンプレートの選択肢として提示）
- **Service 1 : Repository メソッド 1 の比率が長期間続き、抽象化価値が見出せない**と判定した場合（Service と Repository の統合検討）
- **複数データソース（in-memory / S3 / 外部 API）が必要になり、Repository インタフェースの恩恵を本格活用する段階**に達した場合（この時点で Protocol 化を導入）

## References

- [01-roadmap.md: ビジョン](../requirements/5-roadmap/01-roadmap.md#ビジョン変わらない北極星) — ポートフォリオ駆動の最上位目標
- [backend-layers.md](../requirements/5-roadmap/r0-setup/backend-layers.md) — R0-4 手順 SSoT（本 ADR を反映して更新）
- [.claude/rules/backend.md](../../.claude/rules/backend.md) — 実装契約 SSoT（本 ADR を反映して更新）
- [apps/api/app/repositories/README.md](../../apps/api/app/repositories/README.md) — レイヤ概要
- [ADR 0006](./0006-json-schema-as-single-source-of-truth.md) — Pydantic SSoT、schemas/ を境界に置く根拠（Repository が ORM を返し、Service が schemas に詰め替える設計と整合）
- [ADR 0034](./0034-fastapi-for-backend.md) — FastAPI 採用、機能別フラット構成
- [ADR 0037](./0037-sqlalchemy-alembic-for-database.md) — SQLAlchemy 2.0 + Alembic
- [ADR 0038](./0038-test-frameworks.md) — テストフレームワーク（Repository モック不採用方針は本 ADR で更新）
- [ADR 0040](./0040-worker-grouping-and-llm-in-worker.md) — Backend の責務が薄い根拠（Repository を置く ROI が低い元の論拠でもある）
- [ADR 0021](./0021-r0-tooling-discipline.md) — 「YAGNI を適用しない判断」の同型メタ判断
- [02-architecture.md: 設計スタイル](../requirements/2-foundation/02-architecture.md#設計スタイル)
- skill 系（本 ADR に追従して更新）：[backend-new-module](../../.claude/skills/backend-new-module/SKILL.md) / [backend-test](../../.claude/skills/backend-test/SKILL.md) / [backend-implement](../../.claude/skills/backend-implement/SKILL.md) / [onboarding](../../.claude/skills/onboarding/SKILL.md)
