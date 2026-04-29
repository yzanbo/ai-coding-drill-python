# 07. 技術スタック

> **このドキュメントの守備範囲**：各レイヤで採用する技術（What）と選定理由（Why）、ライブラリ・サービスの具体名、コスト試算。
> **コンポーネントの責務・データフロー・ジョブ動作の仕組み**は [04_architecture.md](./04_architecture.md) を参照。

---

## リポジトリ・モノレポ構成

- **Turborepo + pnpm workspaces** を採用（→ [ADR 0012](../../adr/0012-turborepo-pnpm-monorepo.md)）
  - pnpm workspaces：JS/TS パッケージの依存解決・リンク（土台）
  - Turborepo：ビルド順序・並列実行・キャッシュ・Vercel リモートキャッシュ（上層）
  - Go は `go mod`、Python（Phase 7）は `uv` を使い、Turborepo は `package.json` script から薄く統合
- ディレクトリ構成の最終版は [ADR 0012](../../adr/0012-turborepo-pnpm-monorepo.md) を参照

## コード品質ツール

- **Biome**（lint + format、Rust 製で高速）を TS で書かれた全アプリ・全パッケージで統一使用（→ [ADR 0013](../../adr/0013-biome-for-tooling.md)）
  - 共有設定：`packages/config/biome-config/`
  - ESLint + Prettier の組み合わせは不採用
- **TypeScript（`tsc --noEmit`）** で型チェック（Biome は型チェックを行わないため必須）
- 補完ツール（Knip / lefthook / commitlint / syncpack 等）は MVP では導入せず、必要性が確認できた段階で追加
- **Go**：`gofmt` + `golangci-lint`
- **Python（Phase 7）**：`ruff`（Linter + Formatter 統合）

## 共有型・スキーマ（JSON Schema を SSoT）

- **JSON Schema を Single Source of Truth とし、各言語向けの型を自動生成**する設計（→ [ADR 0014](../../adr/0014-json-schema-as-single-source-of-truth.md)）
- 配置：`packages/shared-types/`
  - `schemas/`：JSON Schema 本体（SSoT）
  - `generated/ts/`：Zod スキーマ + TS 型（コミットする）
  - `generated/go/`：Go struct（gitignore、build 時生成）
  - `generated/python/`：Pydantic モデル（gitignore、build 時生成、Phase 7）
- 生成ツール候補：`json-schema-to-zod`（TS）、`quicktype`（Go）、`datamodel-code-generator`（Python）
- 選定理由：3 言語間の型整合性を構造的に保証、スキーマ変更が 1 箇所で全言語追従、新言語追加コスト最小

---

## フロントエンド

- **Next.js**（App Router, TypeScript） — フロント専用と位置付け、API Route は最小限
- **Tailwind CSS**
- **CodeMirror 6**（コード入力）
  - `@codemirror/lang-javascript`（TypeScript ハイライト）
  - `@typescript/vfs` + `@valtown/codemirror-ts`（ブラウザ内型診断・補完）
  - 選定理由：Monaco 比でバンドル 10〜20 倍軽量（~200KB）、Next.js との親和性（Worker/SSR ハマりなし）、モバイル・アクセシビリティ対応、サーバ採点前の即時型フィードバックで UX 向上
- **TanStack Query**（Client Component 側のサーバー状態管理）
  - 用途を限定：採点結果ポーリング、ジョブステータス監視、学習履歴の再取得・キャッシュ、解答送信（`useMutation` + 楽観的更新）
  - 一覧・詳細の単純取得は RSC で直接 `fetch` し役割分担を明確化
  - 選定理由：ポーリング・リトライ・キャッシュが標準装備、非同期ジョブ中心の本サービスで UX 効果が高い

→ コンポーネントの責務は [04: Frontend](./04_architecture.md#frontend)

---

## バックエンド API（NestJS / TypeScript）

- **決定**：NestJS（TypeScript）
- 選定理由：
  - 実務で使用しているフレームワークで MVP の実装速度を最大化
  - DI / Module / Guard / Interceptor によりレイヤード設計が綺麗に書け、テスタビリティが高い
  - 求人市場で評価が高く、ポートフォリオで「設計力を持つバックエンドエンジニア」として強くアピールできる
- 主要ライブラリ：
  - 認証：`@nestjs/passport` + Passport（GitHub OAuth）
  - バリデーション：`class-validator` + `class-transformer`
  - OpenAPI：`@nestjs/swagger`
  - キュー（Producer）：Prisma / Drizzle から `jobs` テーブルへ INSERT（専用ライブラリ不使用）
  - テスト：Jest（NestJS 標準）

→ Module 構成・責務・設計スタイルは [04: Backend API](./04_architecture.md#backend-apinestjs)

---

## 採点ワーカー（Go）

- **決定**：Go
- 選定理由：
  - シングルバイナリ・小さな Docker イメージ・高速起動でランニングコスト削減
  - `github.com/docker/docker/client` による Docker 操作
  - goroutine による並列採点
  - ポートフォリオとして「言語を使い分ける設計判断」を語れる
- 主要ライブラリ：
  - HTTP / ヘルスチェック：標準 `net/http`
  - Docker 操作：`github.com/docker/docker/client`
  - Postgres 接続：`github.com/jackc/pgx/v5`（ジョブキュー取得・結果書き戻し、`LISTEN/NOTIFY` 対応）
  - Redis 接続：`github.com/redis/go-redis`（LLM キャッシュ参照時のみ）
  - 構造化ログ：標準 `log/slog`
  - OpenTelemetry：`go.opentelemetry.io/otel`
  - テスト：標準 `testing` + `testify`

→ ワーカーの役割・並列処理・サンドボックス起動の流れは [04: 採点ワーカー](./04_architecture.md#採点ワーカーgo)

---

## ジョブキュー（Postgres `SELECT FOR UPDATE SKIP LOCKED`）

- **決定**：Postgres の `jobs` テーブル + 行ロックでキュー化（専用ミドルウェアを使わない）
- 選定理由：
  - 既存 DB 再利用でインフラ追加なし、バックアップ/PITR を一元化
  - 解答登録とジョブ登録を同一トランザクションで実行可能（Outbox パターン不要、二重書き込み問題なし）
  - `pg`（Node）・`pgx`（Go）どちらも生 SQL で操作でき、ライブラリロックイン回避
  - `SELECT * FROM jobs WHERE state='failed'` で観測性最強
  - 想定規模（数百ジョブ/日）に対しスループット余裕が 3 桁
- テーブル設計（概要）：
  - `id / queue / payload(JSONB) / state / attempts / run_at / locked_at / locked_by / last_error / created_at`
  - インデックス：`(queue, state, run_at)`
- ペイロードは JSONB、スキーマは JSON Schema で管理し TS / Go 両方に型生成
- 取得方式：`LISTEN/NOTIFY` + 30 秒間隔の低頻度ポーリングのハイブリッド
- スケール時の移行先：NATS JetStream（ファンアウト・Pub/Sub が必要になった場合）

→ 動作仕組み・運用作法・ジョブの流れは [04: ジョブキュー](./04_architecture.md#ジョブキューpostgres-select-for-update-skip-locked)

---

## データベース

- **PostgreSQL 16**
- ORM / マイグレーション：Prisma または Drizzle ORM
- 用途：アプリデータ（users, problems, submissions）+ ジョブキュー（`jobs` テーブル）

---

## キャッシュ / セッション

- **Upstash Redis**（無料枠・リクエスト課金）
- 用途：LLM レスポンスキャッシュ、セッション、レート制限
- 選定理由：
  - ElastiCache は無料枠なし（最小 ~$10/月）、用途的に高耐久性は過剰
  - Upstash 無料枠で本プロジェクトのトラフィックを十分にカバー、サーバレスで運用負荷ゼロ
  - 「AWS 一本」を維持しつつ、コスト効率の合理的判断として一部 SaaS を採用
- レート制限実装：Sliding Log 方式（Redis ZSET、`@nestjs/throttler` + Redis ストレージ）
  - 大規模化時は Window Counter 方式への移行を検討
- トラフィック増で無料枠超過時は ElastiCache へ移行検討

---

## LLM

### モデル選定方針
**特定モデル・特定ベンダーに依存しない設計**を最優先。`LlmProvider` 抽象化レイヤを介して呼び出し、設定ファイル（YAML）でモデルを差し替え可能とする。

- 切替候補：Anthropic Claude / Google Gemini / OpenAI / OpenRouter（DeepSeek・Llama 等を含む）/ 自前ホスティング
- 抽象化レイヤに集約する責務：構造化出力の正規化、キャッシュ、コスト計測、観測性スパン、リトライ・フォールバック
- 具体的なモデル選定は MVP 実装着手時に決定し、Phase 2 以降にベンチマークと運用ログに基づいて適時更新
- 詳細は [ADR 0011: LLM プロバイダ抽象化戦略](../../adr/0011-llm-provider-abstraction.md)

### 想定ライブラリ
- `@anthropic-ai/sdk`（Anthropic 採用時）
- `@google/generative-ai`（Gemini 採用時）
- `openai` ライブラリ（OpenAI / OpenRouter 経由の DeepSeek 等で使用）
- `instructor` / `zod`（構造化出力のバリデーション）

### LLM-as-a-Judge
- 自前実装（NestJS の `GenerationModule` 内、多軸スコアリング）
- 既存フレームワーク（DeepEval の `G-Eval` 等）は参考にするが、問題生成ドメインに特化した自前評価器を採用
- 理由：評価ロジック自体がポートフォリオの差別化軸、フレームワーク依存を避ける（[ADR 0009](../../adr/0009-custom-llm-judge.md)）
- 生成モデルと Judge モデルは別プロバイダ・別モデルにする（自己評価バイアス回避）

---

## サンドボックス

- 実行対象：TypeScript コード（`tsx` or `esbuild` でトランスパイル → Node.js で実行）
- テストランナー：Vitest（ユーザー解答 + 生成テストケースを合成して実行）
- 型チェック：`tsc --noEmit`（型パズル系カテゴリで使用）
- ランタイムの段階的進化：
  - フェーズ 1：Docker（`--network none`, `--read-only`, 各種制限）
  - フェーズ 2：gVisor（runsc ランタイム）
  - フェーズ 3（任意）：Firecracker microVM
- 言語アダプタ層を抽象化し、将来的な Python・他言語追加に備える

→ 使い捨てコンテナ方式の根拠と隔離設計は [04: サンドボックスランナー](./04_architecture.md#サンドボックスランナーgo-ワーカー内で実行)

---

## 品質評価まわりのツール

- **ミューテーションテスト**：`stryker-js`（TS 向け、Phase 2 以降）
- **LLM-as-a-Judge**：自前実装（上述）

---

## インフラ

### クラウド：AWS（確定）
- 選定理由：求人需要・情報量・エコシステム、マルチクラウドは複雑度コスト超過のため不採用

### IaC
- Terraform（モジュール化：network / db / ecs / worker / monitoring）

### デプロイ先

| コンポーネント | サービス | 備考 |
|---|---|---|
| Frontend | Vercel | Next.js とのファーストパーティ統合、無料枠 |
| Backend API | ECS Fargate（最小タスク 1） | cold start 回避 |
| 採点ワーカー | EC2 t4g.small | Docker Engine + Go バイナリ。gVisor/Firecracker 拡張のため |
| DB（兼ジョブキュー） | RDS PostgreSQL（db.t4g.micro） | 無料枠活用 |
| キャッシュ | Upstash Redis | 上述の選定理由 |
| コンテナレジストリ | ECR | |
| シークレット | Secrets Manager / Parameter Store | |
| DNS / SSL | Route 53 + ACM | |
| コスト管理 | AWS Budgets | 月額上限アラート |

### コスト目安
- 標準構成：~$25〜50/月
- 最適化構成（Upstash + Spot Instance 等）：~$10〜15/月

→ 物理配置の論理と責務分離は [04: インフラの論理配置](./04_architecture.md#インフラの論理配置)

---

## 観測性

- **OpenTelemetry SDK**
- **Grafana Cloud**（無料枠）または自前 Grafana + Loki + Tempo + Prometheus
- **Sentry**（無料枠、エラー追跡）

---

## CI/CD

- **GitHub Actions**
- pre-commit（lint/format）
- Dependabot
- PR 時：lint、型チェック、テスト
- main マージ時：Docker build → ECR push → デプロイ
- Terraform plan/apply もワークフロー化

---

## テスト

- **Jest**（NestJS 標準。API・LLM パイプライン・ユニット・E2E スペック）
- Go 標準 `testing` + `testify`（採点ワーカー）
- **Playwright**（E2E）
- テストカバレッジ：Codecov

---

## 将来追加予定（次バージョン・Phase 7）

### Python（オフライン評価・分析パイプライン）
- 生成済み問題の一括再評価バッチ（Judge プロンプト改善時の回帰テスト）
- 重複検出（embedding + クラスタリング）、カテゴリ・難易度分布分析
- 学習履歴の分析、Jupyter Notebook での可視化レポート
- 人間評価 vs LLM Judge の相関分析（Judge の信頼性モニタリング）
- RAG による教材準拠問題生成を追加する場合は Ragas を評価フレームワークとして導入検討
- ライブラリ候補：`pydantic`, `instructor`, `llama-index`, `pandas`, `scikit-learn`（クラスタリング）, `sentence-transformers`（embedding）

---

## 選定理由の README 反映方針

各技術について「なぜ選んだか」「他候補と比較して何を優先したか」を README に書く。これが面接で最も評価される。
