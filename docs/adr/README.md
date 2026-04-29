# Architecture Decision Records（ADR）

重要な技術・設計判断を 1 ファイル 1 決定で記録するディレクトリ。

## 目的

- 「なぜ X を選んだのか？」を後から辿れるようにする
- 検討した代替案・トレードオフを残し、将来の見直しに活かす
- ポートフォリオ・チーム内での設計レビューの素材にする

## 運用ルール

### ファイル命名
- `NNNN-kebab-case-title.md`
- 例：`0001-postgres-as-job-queue.md`、`0002-aws-single-cloud.md`
- 連番は採番順、欠番不可

### ステータス
- `Proposed`：提案中、議論中
- `Accepted`：採用決定、実装に反映
- `Deprecated`：もう使っていないが履歴として残す
- `Superseded by NNNN`：別の ADR で上書きされた

### 不変性
- 一度 `Accepted` した ADR は**本文を書き換えない**
- 変更したい場合は新しい ADR を作って前の ADR の `Status` を `Superseded by NNNN` に更新する
- 履歴の Append-only を徹底する

### 書くタイミング
- 設計上の選択肢が複数あり、どれかを選んだとき
- 「なぜこうしたんだっけ？」と後から問われそうなとき
- 一般的でない選択をしたとき（標準から外れる場合は必ず）

### 書かないもの
- 自明な技術選定（HTTPS を使う、UTF-8 を使う等）
- コーディング規約レベルの細かい実装詳細
- 個人の好みや一時的な決定

## テンプレート
新規作成時は [template.md](./template.md) をコピーして使う。

## 書き溜め予定（実装中に順次作成）

このプロジェクトで ADR にする予定の決定：

- 0001: Postgres `SELECT FOR UPDATE SKIP LOCKED` をジョブキューに採用（Redis Streams / RabbitMQ / NATS 等を不採用）
- 0002: AWS 単独クラウド（マルチクラウド不採用）
- 0003: CodeMirror 6 採用（Monaco Editor 不採用）
- 0004: NestJS 採用（Hono / Fastify / Express 不採用）
- 0005: 採点ワーカーを Go で実装（Node / Rust 不採用）
- 0006: Redis をジョブキュー用途で不採用、キャッシュ・セッション・レート制限のみ
- 0007: Upstash Redis 採用（ElastiCache 不採用）
- 0008: 採点コンテナの使い捨て方式（ウォームプール不採用）
- 0009: LLM-as-a-Judge を自前実装（DeepEval / Ragas 等の依存を回避）
- 0010: 言語の段階導入（MVP は TS+Go、Phase 7 で Python 追加）
- 0011: LLM プロバイダ抽象化戦略（特定モデルへの依存を排除）
- 0012: モノレポツールに Turborepo + pnpm workspaces を採用
- 0013: コード品質ツールに Biome を採用（ESLint + Prettier 不採用）
- 0014: 共有データ型は JSON Schema を Single Source of Truth とし各言語向けに自動生成
- 0015: 認証は GitHub OAuth のみ実装、ただし複数プロバイダへ拡張可能な設計とする

実装中に発生した新たな決定も都度追加する。
