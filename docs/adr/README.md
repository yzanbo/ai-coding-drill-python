# Architecture Decision Records（ADR）

重要な技術・設計判断を **1 ファイル 1 決定** で記録するディレクトリ。判断が変わった時は本文を直接書き換えて最新状態に保つ（履歴は git log で辿れる）。

## 目的

- 「なぜ X を選んだのか？」を後から辿れるようにする
- 検討した代替案・トレードオフを残し、将来の見直しに活かす
- ポートフォリオ・チーム内での設計レビューの素材にする

---

## 📚 索引（思考順序＝採番順、全 41 件）

ADR 番号は **プロジェクトをゼロから設計する際に考えるべき順序**で付番されている。最上位の戦略判断（Tier 1）から始まり、抽象度の高い順にアーキテクチャ → インフラ → 技術スタック → 開発規律と階層を下りていく。各階層内では「メタ方針 → 個別判断」「基盤 → 派生」の順に並ぶ。

### Tier 1: 戦略・全体方針（4 件）

プロジェクト全体を規定する最上位の制約・原則。後続の全 ADR の前提となる。

| ADR | タイトル | キーワード |
|---|---|---|
| [0001](./0001-requirements-as-5-buckets.md) | 要件定義書を「時系列 × 変更頻度」の 5 バケット構造に再編 | ドキュメント設計 / SSoT / 読む順序と書く順序 |
| [0002](./0002-aws-single-cloud.md) | AWS 単独クラウド（マルチクラウド不採用） | エコシステム集中 / 複雑度回避 |
| [0003](./0003-phased-language-introduction.md) | レイヤ別ポリグロット構成（Python + Go + TypeScript） | ポリグロット戦略 / 役割別配置 |
| [0033](./0033-backend-language-pivot-to-python.md) | バックエンドを Python に pivot（NestJS → Python） | 言語切替 / 設計の言語非依存性 / 採用面接駆動 |

### Tier 2: アーキテクチャ（9 件）

システム全体の論理構造、データ・ジョブの流れ、コンポーネント間連携に関わる中核判断。

| ADR | タイトル | キーワード |
|---|---|---|
| [0004](./0004-postgres-as-job-queue.md) | Postgres をジョブキューに採用（Redis Streams / RabbitMQ / NATS 等を不採用） | SKIP LOCKED / LISTEN/NOTIFY / Outbox 不要 |
| [0005](./0005-redis-not-for-job-queue.md) | Redis をジョブキュー用途では使わない（キャッシュ・セッション・レート制限のみ） | 役割の明確化 / 二系統回避 |
| [0006](./0006-json-schema-as-single-source-of-truth.md) | 共有データ型は Pydantic を Single Source of Truth とし、用途別伝送路（OpenAPI / JSON Schema）で各言語に展開 | Pydantic-first / FastAPI 自動 OpenAPI / Hey API + quicktype |
| [0007](./0007-llm-provider-abstraction.md) | LLM プロバイダ抽象化戦略（特定モデルへの依存を排除） | ベンダーロックイン回避 / 可逆な判断の遅延 |
| [0008](./0008-custom-llm-judge.md) | LLM-as-a-Judge を自前実装（DeepEval / Ragas 等の依存を回避） | 評価ロジックの差別化軸 |
| [0009](./0009-disposable-sandbox-container.md) | 採点コンテナの使い捨て方式（ウォームプール不採用） | セキュリティ × スループット |
| [0010](./0010-w3c-trace-context-in-job-payload.md) | W3C Trace Context をジョブペイロードに埋め込んでプロセス境界トレース連携を実現 | 分散トレース / SpanLink / OTel Messaging |
| [0011](./0011-github-oauth-with-extensible-design.md) | 認証は GitHub OAuth のみ実装、ただし複数プロバイダへ拡張可能な設計 | Strategy パターン / users + auth_providers |
| [0040](./0040-worker-grouping-and-llm-in-worker.md) | Worker を apps/workers/<name>/ 配下にグループ化し、LLM 呼び出しを Worker に集約 | 複数 Worker / LLM 非同期 / プロンプト Worker 内化 |

### Tier 3: インフラ（2 件）

クラウド・ホスティング詳細。AWS 単独方針（Tier 1）からの合理的逸脱を含む。

| ADR | タイトル | キーワード |
|---|---|---|
| [0012](./0012-upstash-redis-over-elasticache.md) | Upstash Redis 採用（ElastiCache 不採用） | サーバレス / 無料枠 / コスト効率 |
| [0013](./0013-vercel-for-frontend-hosting.md) | Frontend ホスティングに Vercel を採用（AWS Amplify / S3+CloudFront 不採用） | Next.js ファーストパーティ統合 / 無料枠 / AWS 単独方針からの 2 例目の例外 |

### Tier 4: 技術スタック（12 件）

各レイヤで採用する具体的な技術・フレームワーク・ライブラリの選定。

| ADR | タイトル | キーワード |
|---|---|---|
| [0014](./0014-nestjs-for-backend.md) | バックエンド API に NestJS を採用（Hono / Fastify / Express 不採用）*(Superseded by 0033)* | DI / Module / Guard / レイヤード設計（移行軌跡として保持） |
| [0015](./0015-codemirror-over-monaco.md) | CodeMirror 6 採用（Monaco Editor 不採用） | バンドル軽量化 / モバイル対応 |
| [0016](./0016-go-for-grading-worker.md) | 採点ワーカーを Go で実装(Node / Rust 不採用) | シングルバイナリ / goroutine / Docker SDK |
| [0017](./0017-drizzle-orm-over-prisma.md) | ORM に Drizzle を採用（Prisma 不採用）*(Superseded by 0033, 0037)* | 型推論 / 生 SQL 親和性 / コールドスタート（移行軌跡として保持） |
| [0018](./0018-biome-for-tooling.md) | TypeScript のコード品質ツールに Biome を採用、設定は `apps/web/` 配下に直接配置 *(Accepted, Amended by 0033 / 0036)* | Rust 製高速 / 設定統一 / 単一設定スキャン（Frontend 用途として継続採用） |
| [0019](./0019-go-code-quality.md) | Go のコード品質ツールに gofmt + golangci-lint を採用 | Go 標準 / メタリンター / `go build` 内蔵型チェック |
| [0020](./0020-python-code-quality.md) | Python のコード品質ツールに ruff + pyright を採用 | lint+format 統合 / 型仕様準拠率 98% / Pylance IDE 統合 |
| [0034](./0034-fastapi-for-backend.md) | バックエンド API に FastAPI を採用 | Python / 型ヒント駆動 / OpenAPI 自動生成 |
| [0035](./0035-uv-for-python-package-management.md) | Python のパッケージ管理・モノレポ管理に uv を採用 | Astral 統合 / 10〜100x 高速 / workspace + lockfile 一体化 |
| [0037](./0037-sqlalchemy-alembic-for-database.md) | DB ORM・マイグレーションに SQLAlchemy 2.0（async）+ Alembic を採用 | async ネイティブ / Pyright 型推論 / Postgres 高度機能 |
| [0038](./0038-test-frameworks.md) | テストフレームワーク確定（pytest / Vitest / Playwright / Go testing） | レイヤ別デファクト / async 対応 / E2E クロスブラウザ |
| [0041](./0041-observability-stack-grafana-and-sentry.md) | 観測性スタックに Grafana 系（Loki / Tempo / Prometheus / Grafana）+ Sentry を採用 | OSS / 3 系統 1 画面統合 / Grafana Cloud 無料枠 / OTLP ネイティブ |

### Tier 5: 開発規律（14 件）

モノレポ運用・コード品質・型生成・ツール導入規律など、**開発体験を支える判断**。先頭 2 つはメタ方針。

| ADR | タイトル | キーワード |
|---|---|---|
| [0021](./0021-r0-tooling-discipline.md) | 補完ツール（lefthook / commitlint / Knip / syncpack / ruff / pyright / pip-audit / deptry）を R0 から導入 | YAGNI 例外条件 / 不可逆コスト膨張 |
| [0022](./0022-config-file-format-priority.md) | 設定ファイル形式の選定方針（自由選択時は TS > JSONC > YAML の優先順位） | ツール強制 / ecosystem 慣習 / 型安全 |
| [0023](./0023-turborepo-pnpm-monorepo.md) | モノレポツールに Turborepo + pnpm workspaces を採用 *(Superseded by 0033, 0036)* | ビルドキャッシュ / 並列実行（Frontend は pnpm workspaces のみに縮小、Python 側は [ADR 0035](./0035-uv-for-python-package-management.md) の uv に置換、tool 版数 / タスクランナーは [ADR 0039](./0039-mise-for-task-runner-and-tool-versions.md) の mise に分離） |
| [0024](./0024-syncpack-package-json-consistency.md) | package.json の整合性を syncpack で機械強制し、設定は `apps/web/` 配下に直接配置 *(Accepted, Amended by 0033 / 0036)* | 重複検知 / キー順整形 / `^` 統一の 3 ルールに縮小（Frontend 用途として継続採用、Python 側は uv lockfile で代替） |
| [0036](./0036-frontend-monorepo-pnpm-only.md) | Frontend モノレポ管理を pnpm workspaces のみに縮小（Turborepo 不採用） | 単一 Next.js app では Turborepo の価値ドライバが効かず |
| [0039](./0039-mise-for-task-runner-and-tool-versions.md) | タスクランナー兼 tool 版数管理に mise を採用 | polyglot 横断タスク / pyenv+nvm+goenv 統合 / Turborepo 空席を埋める |
| [0025](./0025-github-actions-as-ci-cd.md) | CI/CD ツールに GitHub Actions を採用（CircleCI / Jenkins / Tekton 等を不採用） | コードホスト統合 / OIDC キーレス / 可逆性 |
| [0026](./0026-github-actions-incremental-scope.md) | GitHub Actions のスコープを段階的に拡張（R0 は commitlint + Biome + typecheck のみ） | YAGNI / 段階拡張 / 無料枠節約 |
| [0027](./0027-github-actions-sha-pinning.md) | GitHub Actions のサードパーティアクションを SHA でピン止め（タグ書き換え攻撃対策） | サプライチェーン攻撃耐性 / fail-closed / Dependabot 前提 |
| [0028](./0028-dependabot-auto-update-policy.md) | 依存関係の自動更新ポリシー（Dependabot を採用、週次 / メジャー除外 / グループ化） | 脆弱性追従 / SHA ピン止め前提 / commitlint 規約準拠 |
| [0029](./0029-commit-scope-convention.md) | コミット scope 規約（モノレポ領域 8 種 + 自動更新用 deps / deps-dev の列挙制） | scope-enum / Dependabot 連携 / SSoT |
| [0030](./0030-commitlint-base-commit-fetch.md) | commitlint の base コミット取得を iterative deepen 方式で行う（GitHub Git プロトコル非互換回避） | shallow-exclude 不可 / `--deepen=20` ループ / 累積コミット数非依存 |
| [0031](./0031-ci-success-umbrella-job.md) | CI Required status checks を集約ジョブ `ci-success` で 1 本化（umbrella job パターン） | Ruleset 不変 / `needs.*.result` / `if: always()` |
| [0032](./0032-github-repository-settings.md) | GitHub リポジトリ設定の方針（ブランチ保護 / マージ動作 / Actions / Security / Features） | デフォルト値棚卸し / 機械強制最大化 / 1 人運用前提 |

---

## 🎯 リリースとの関係

各リリース（[5-roadmap/01-roadmap.md](../requirements/5-roadmap/01-roadmap.md) 参照）で参照される ADR：

| リリース | 主な参照 ADR |
|---|---|
| **R0** 基盤立ち上げ | [0004](./0004-postgres-as-job-queue.md) / [0006](./0006-json-schema-as-single-source-of-truth.md) / [0018](./0018-biome-for-tooling.md) / [0020](./0020-python-code-quality.md) / [0021](./0021-r0-tooling-discipline.md) / [0022](./0022-config-file-format-priority.md) / [0025](./0025-github-actions-as-ci-cd.md) / [0026](./0026-github-actions-incremental-scope.md) / [0027](./0027-github-actions-sha-pinning.md) / [0028](./0028-dependabot-auto-update-policy.md) / [0029](./0029-commit-scope-convention.md) / [0030](./0030-commitlint-base-commit-fetch.md) / [0031](./0031-ci-success-umbrella-job.md) / [0032](./0032-github-repository-settings.md) / [0033](./0033-backend-language-pivot-to-python.md) / [0034](./0034-fastapi-for-backend.md) / [0035](./0035-uv-for-python-package-management.md) / [0036](./0036-frontend-monorepo-pnpm-only.md) / [0037](./0037-sqlalchemy-alembic-for-database.md) / [0039](./0039-mise-for-task-runner-and-tool-versions.md) |
| **R1** MVP（最小貫通） | [0006](./0006-json-schema-as-single-source-of-truth.md) / [0007](./0007-llm-provider-abstraction.md) / [0009](./0009-disposable-sandbox-container.md) / [0010](./0010-w3c-trace-context-in-job-payload.md) / [0011](./0011-github-oauth-with-extensible-design.md) / [0015](./0015-codemirror-over-monaco.md) / [0016](./0016-go-for-grading-worker.md) / [0019](./0019-go-code-quality.md) / [0034](./0034-fastapi-for-backend.md) / [0037](./0037-sqlalchemy-alembic-for-database.md) / [0038](./0038-test-frameworks.md) / [0040](./0040-worker-grouping-and-llm-in-worker.md) |
| **R2** 品質保証パイプライン | [0007](./0007-llm-provider-abstraction.md) / [0008](./0008-custom-llm-judge.md) / [0040](./0040-worker-grouping-and-llm-in-worker.md) |
| **R3** サンドボックス強化 | [0009](./0009-disposable-sandbox-container.md) |
| **R4** 観測性 | [0010](./0010-w3c-trace-context-in-job-payload.md) / [0041](./0041-observability-stack-grafana-and-sentry.md) |
| **R5** 仕上げ・公開 | [0002](./0002-aws-single-cloud.md) / [0012](./0012-upstash-redis-over-elasticache.md) / [0013](./0013-vercel-for-frontend-hosting.md) |
| **R7** 問題生成 Worker 分離 | [0003](./0003-phased-language-introduction.md) / [0040](./0040-worker-grouping-and-llm-in-worker.md) |

---

## 📌 注目 ADR（採用担当者向け）

差別化軸として特に深く読んでほしい 6 件：

1. **[0001: 要件定義書を 5 バケット時系列構造に再編](./0001-requirements-as-5-buckets.md)** — ドキュメント設計の判断を ADR 化した珍しい例、時系列 × 変更頻度での物理分離
2. **[0006: Pydantic を SSoT に、用途別伝送路で各言語へ展開](./0006-json-schema-as-single-source-of-truth.md)** — 3 言語（TS/Go/Python）横断の型整合性を構造的に保証
3. **[0007: LLM プロバイダ抽象化戦略](./0007-llm-provider-abstraction.md)** — ベンダーロックイン回避、可逆な判断の遅延という設計哲学
4. **[0009: 使い捨てサンドボックスコンテナ](./0009-disposable-sandbox-container.md)** — セキュリティ × スループットのトレードオフ判断、段階的隔離強化（Docker → gVisor → Firecracker）
5. **[0010: W3C Trace Context をジョブペイロードに埋め込む](./0010-w3c-trace-context-in-job-payload.md)** — プロセス境界トレース連携、SpanLink vs Parent-Child の議論、OTel Messaging Semantic Conventions 準拠
6. **[0021: 補完ツールを R0 から導入](./0021-r0-tooling-discipline.md)** — 「遅延の不可逆性が高い判断には YAGNI を適用しない」というメタ方針の確立

---

## 運用ルール

### ファイル命名

- `NNNN-kebab-case-title.md`
- 例：`0004-postgres-as-job-queue.md`、`0002-aws-single-cloud.md`
- 連番は **思考順序（Tier 1 → Tier 5）**で付番、欠番不可

### ステータス

本プロジェクトでは ADR を**決定後に書く運用**（提案段階では起票しない）を採用しているため、`Proposed` は使わない。

- `Accepted`：採用決定、実装に反映
- `Amended by NNNN`：採用判断は維持しつつ前提（言語スタック・配置範囲・ルールセット等）が後続 ADR で更新された
- `Deprecated`：もう使っていないが履歴として残す
- `Superseded by NNNN`：別の ADR で完全に置き換えられた（採用判断そのものが取り消された）

### 更新方針

- ADR 本文は**いつでも書き換え可能**。判断が変わったら最新状態に直接反映し、ドキュメントを「現時点の答え」として保つ
- 過去の判断履歴を辿りたい場合は `git log -p docs/adr/<file>.md` で参照する（書き換え時に判断の根拠・経緯はコミットメッセージに残す）
- 別の ADR で**完全に置き換えられた**場合は `Status` を `Superseded by NNNN` に更新する（採用判断そのものが取り消された場合。リネーム / 統合 / 廃止など、ファイル自体を残しつつ無効化したい時）
- **採用判断は維持しつつ前提（言語スタックや配置範囲）が大きく変わった**場合は `Status` を `Accepted（<適用範囲>、Amended by NNNN）` の形式に更新する。本文冒頭の Note で「採用は維持・XX に再配置 / ルールセット縮小」等の更新内容を明記する。例：[ADR 0018](./0018-biome-for-tooling.md)（Biome 採用は維持、Frontend 用途に縮小・設定を `apps/web/` 配下に閉じる）/ [ADR 0024](./0024-syncpack-package-json-consistency.md)（syncpack 採用は維持、`apps/web/.syncpackrc.ts` に再配置・ルール 3 件に縮小）

### 書くタイミング

- 設計上の選択肢が複数あり、どれかを選んだとき
- 「なぜこうしたんだっけ？」と後から問われそうなとき
- 一般的でない選択をしたとき（標準から外れる場合は必ず）

### 書かないもの

- 自明な技術選定（HTTPS を使う、UTF-8 を使う等）
- コーディング規約レベルの細かい実装詳細
- 個人の好みや一時的な決定

### 新規 ADR の挿入位置

新規 ADR を追加する際は **思考順序のどの Tier に属するか**を判断し、**該当 Tier の末尾**に追加する（既存 ADR の番号を再採番しない）。Tier 内の細かい順序が崩れる場合は受容する（厳密な「メタ → 個別」順を維持するために全 ADR を再採番するコストは見合わない）。

### 推奨セクション構成

各 ADR は以下を必ず含める（→ [template.md](./template.md)）：

- **Status / Date / Decision-makers**
- **Context**（背景・課題）
- **Decision**（決定内容）
- **Alternatives Considered**（検討した代替案 — トレードオフ表で）
- **Consequences**（結果・トレードオフ + 将来の見直しトリガー）
- **References**（関連する要件定義書・他 ADR・外部資料）

---

## テンプレート

新規作成時は [template.md](./template.md) をコピーして使う。

実装中に発生した新たな決定も都度追加する。
