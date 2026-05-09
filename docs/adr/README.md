# Architecture Decision Records（ADR）

重要な技術・設計判断を **1 ファイル 1 決定** で記録するディレクトリ。判断が変わった時は本文を直接書き換えて最新状態に保つ（履歴は git log で辿れる）。

## 目的

- 「なぜ X を選んだのか？」を後から辿れるようにする
- 検討した代替案・トレードオフを残し、将来の見直しに活かす
- ポートフォリオ・チーム内での設計レビューの素材にする

---

## 📚 カテゴリ別索引（31 件）

採用担当者・面接官の方は、興味のある観点から該当 ADR を探せます。

### 🏗️ アーキテクチャ判断（7 件）

システム構造・データフロー・コンポーネント間連携に関わる中核判断。

| ADR | タイトル | キーワード |
|---|---|---|
| [0001](./0001-postgres-as-job-queue.md) | Postgres をジョブキューに採用（Redis Streams / RabbitMQ / NATS 等を不採用） | SKIP LOCKED / LISTEN/NOTIFY / Outbox 不要 |
| [0006](./0006-redis-not-for-job-queue.md) | Redis をジョブキュー用途では使わない（キャッシュ・セッション・レート制限のみ） | 役割の明確化 / 二系統回避 |
| [0008](./0008-disposable-sandbox-container.md) | 採点コンテナの使い捨て方式（ウォームプール不採用） | セキュリティ × スループット |
| [0009](./0009-custom-llm-judge.md) | LLM-as-a-Judge を自前実装（DeepEval / Ragas 等の依存を回避） | 評価ロジックの差別化軸 |
| [0010](./0010-phased-language-introduction.md) | 言語の段階導入（MVP は TS+Go、R7 で Python 追加） | ポリグロット戦略 |
| [0011](./0011-llm-provider-abstraction.md) | LLM プロバイダ抽象化戦略（特定モデルへの依存を排除） | ベンダーロックイン回避 / 可逆な判断の遅延 |
| [0017](./0017-w3c-trace-context-in-job-payload.md) | W3C Trace Context をジョブペイロードに埋め込んでプロセス境界トレース連携を実現 | 分散トレース / SpanLink / OTel Messaging |

### 🔧 技術スタック判断（5 件）

各レイヤで採用する具体的な技術・フレームワーク・ライブラリの選定。

| ADR | タイトル | キーワード |
|---|---|---|
| [0003](./0003-codemirror-over-monaco.md) | CodeMirror 6 採用（Monaco Editor 不採用） | バンドル軽量化 / モバイル対応 |
| [0004](./0004-nestjs-for-backend.md) | バックエンド API に NestJS を採用（Hono / Fastify / Express 不採用） | DI / Module / Guard / レイヤード設計 |
| [0005](./0005-go-for-grading-worker.md) | 採点ワーカーを Go で実装（Node / Rust 不採用） | シングルバイナリ / goroutine / Docker SDK |
| [0015](./0015-github-oauth-with-extensible-design.md) | 認証は GitHub OAuth のみ実装、ただし複数プロバイダへ拡張可能な設計 | Strategy パターン / users + auth_providers |
| [0016](./0016-drizzle-orm-over-prisma.md) | ORM に Drizzle を採用（Prisma 不採用） | 型推論 / 生 SQL 親和性 / コールドスタート |

### ☁️ インフラ判断（2 件）

クラウド・ホスティング・インフラ運用に関わる判断。

| ADR | タイトル | キーワード |
|---|---|---|
| [0002](./0002-aws-single-cloud.md) | AWS 単独クラウド（マルチクラウド不採用） | エコシステム集中 / 複雑度回避 |
| [0007](./0007-upstash-redis-over-elasticache.md) | Upstash Redis 採用（ElastiCache 不採用） | サーバレス / 無料枠 / コスト効率 |

### 📋 開発規律判断（9 件）

モノレポ運用・コード品質・型生成・ツール導入規律など、**開発体験を支える判断**。

| ADR | タイトル | キーワード |
|---|---|---|
| [0012](./0012-turborepo-pnpm-monorepo.md) | モノレポツールに Turborepo + pnpm workspaces を採用 | ビルドキャッシュ / 並列実行 |
| [0013](./0013-biome-for-tooling.md) | TypeScript のコード品質ツールに Biome を採用、設定はリポジトリルートに直接配置 | Rust 製高速 / 設定統一 / 単一設定スキャン |
| [0014](./0014-json-schema-as-single-source-of-truth.md) | 共有データ型は JSON Schema を Single Source of Truth とし各言語向けに自動生成 | 3 言語型整合 / 新言語追加コスト最小 |
| [0018](./0018-phase-0-tooling-discipline.md) | 補完ツール（Knip / lefthook / commitlint / syncpack）を R0 から導入 | YAGNI 例外条件 / 不可逆コスト膨張 |
| [0019](./0019-requirements-as-5-buckets.md) | 要件定義書を「時系列 × 変更頻度」の 5 バケット構造に再編 | ドキュメント設計 / SSoT / 読む順序と書く順序 |
| [0020](./0020-go-code-quality.md) | Go のコード品質ツールに gofmt + golangci-lint を採用 | Go 標準 / メタリンター / `go build` 内蔵型チェック |
| [0021](./0021-python-code-quality.md) | Python のコード品質ツールに ruff を採用、型チェッカーは Phase 7 着手時に決定 | Astral 統合 / 可逆な判断の遅延 |
| [0022](./0022-github-actions-incremental-scope.md) | GitHub Actions のスコープを段階的に拡張（R0 は commitlint + Biome + typecheck のみ） | YAGNI / 段階拡張 / 無料枠節約 |
| [0023](./0023-github-actions-as-ci-cd.md) | CI/CD ツールに GitHub Actions を採用（CircleCI / Jenkins / Tekton 等を不採用） | コードホスト統合 / OIDC キーレス / 可逆性 |
| [0024](./0024-dependabot-auto-update-policy.md) | 依存関係の自動更新ポリシー（Dependabot を採用、週次 / メジャー除外 / グループ化） | 脆弱性追従 / SHA ピン止め前提 / commitlint 規約準拠 |
| [0025](./0025-commit-scope-convention.md) | コミット scope 規約（モノレポ領域 8 種 + 自動更新用 deps / deps-dev の列挙制） | scope-enum / Dependabot 連携 / SSoT |
| [0026](./0026-github-actions-sha-pinning.md) | GitHub Actions のサードパーティアクションを SHA でピン止め（タグ書き換え攻撃対策） | サプライチェーン攻撃耐性 / fail-closed / Dependabot 前提 |
| [0027](./0027-commitlint-base-commit-fetch.md) | commitlint の base コミット取得を iterative deepen 方式で行う（GitHub Git プロトコル非互換回避） | shallow-exclude 不可 / `--deepen=20` ループ / 累積コミット数非依存 |
| [0028](./0028-config-file-format-priority.md) | 設定ファイル形式の選定方針（自由選択時は TS > JSONC > YAML の優先順位） | ツール強制 / ecosystem 慣習 / 型安全 |
| [0029](./0029-syncpack-package-json-consistency.md) | モノレポ内 package.json の整合性を syncpack で機械強制（versionGroups / semverGroups の最小限ルールセット） | sameRange / `^` 統一 / workspace:* 強制 / `.ts` 設定で型安全 |
| [0030](./0030-ci-success-umbrella-job.md) | CI Required status checks を集約ジョブ `ci-success` で 1 本化（umbrella job パターン） | Ruleset 不変 / `needs.*.result` / `if: always()` |
| [0031](./0031-github-repository-settings.md) | GitHub リポジトリ設定の方針（ブランチ保護 / マージ動作 / Actions / Security / Features） | デフォルト値棚卸し / 機械強制最大化 / 1 人運用前提 |

---

## 📝 連番一覧（時系列）

書かれた順序で全 31 件を一覧する場合：

| # | タイトル | カテゴリ |
|---|---|---|
| [0001](./0001-postgres-as-job-queue.md) | Postgres をジョブキューに採用 | 🏗️ アーキテクチャ |
| [0002](./0002-aws-single-cloud.md) | AWS 単独クラウド | ☁️ インフラ |
| [0003](./0003-codemirror-over-monaco.md) | CodeMirror 6 採用 | 🔧 技術スタック |
| [0004](./0004-nestjs-for-backend.md) | バックエンド API に NestJS を採用 | 🔧 技術スタック |
| [0005](./0005-go-for-grading-worker.md) | 採点ワーカーを Go で実装 | 🔧 技術スタック |
| [0006](./0006-redis-not-for-job-queue.md) | Redis をジョブキュー用途では使わない | 🏗️ アーキテクチャ |
| [0007](./0007-upstash-redis-over-elasticache.md) | Upstash Redis 採用 | ☁️ インフラ |
| [0008](./0008-disposable-sandbox-container.md) | 採点コンテナの使い捨て方式 | 🏗️ アーキテクチャ |
| [0009](./0009-custom-llm-judge.md) | LLM-as-a-Judge を自前実装 | 🏗️ アーキテクチャ |
| [0010](./0010-phased-language-introduction.md) | 言語の段階導入 | 🏗️ アーキテクチャ |
| [0011](./0011-llm-provider-abstraction.md) | LLM プロバイダ抽象化戦略 | 🏗️ アーキテクチャ |
| [0012](./0012-turborepo-pnpm-monorepo.md) | Turborepo + pnpm workspaces | 📋 開発規律 |
| [0013](./0013-biome-for-tooling.md) | TypeScript のコード品質ツールに Biome を採用、設定はリポジトリルート直接配置 | 📋 開発規律 |
| [0014](./0014-json-schema-as-single-source-of-truth.md) | JSON Schema を SSoT に | 📋 開発規律 |
| [0015](./0015-github-oauth-with-extensible-design.md) | GitHub OAuth + 拡張可能設計 | 🔧 技術スタック |
| [0016](./0016-drizzle-orm-over-prisma.md) | ORM に Drizzle 採用 | 🔧 技術スタック |
| [0017](./0017-w3c-trace-context-in-job-payload.md) | W3C Trace Context をジョブペイロードに埋め込む | 🏗️ アーキテクチャ |
| [0018](./0018-phase-0-tooling-discipline.md) | 補完ツールを R0 から導入 | 📋 開発規律 |
| [0019](./0019-requirements-as-5-buckets.md) | 要件定義書を 5 バケット時系列構造に再編 | 📋 開発規律 |
| [0020](./0020-go-code-quality.md) | Go のコード品質ツール（gofmt + golangci-lint） | 📋 開発規律 |
| [0021](./0021-python-code-quality.md) | Python のコード品質ツール（ruff、型チェッカーは Phase 7 着手時決定） | 📋 開発規律 |
| [0022](./0022-github-actions-incremental-scope.md) | GitHub Actions のスコープを段階的に拡張 | 📋 開発規律 |
| [0023](./0023-github-actions-as-ci-cd.md) | CI/CD ツールに GitHub Actions を採用 | 📋 開発規律 |
| [0024](./0024-dependabot-auto-update-policy.md) | 依存関係の自動更新ポリシー（Dependabot） | 📋 開発規律 |
| [0025](./0025-commit-scope-convention.md) | コミット scope 規約（モノレポ領域 + 自動更新用 deps / deps-dev） | 📋 開発規律 |
| [0026](./0026-github-actions-sha-pinning.md) | GitHub Actions のサードパーティアクションを SHA でピン止め | 📋 開発規律 |
| [0027](./0027-commitlint-base-commit-fetch.md) | commitlint の base コミット取得を iterative deepen 方式で行う | 📋 開発規律 |
| [0028](./0028-config-file-format-priority.md) | 設定ファイル形式の選定方針（TS > JSONC > YAML の優先順位） | 📋 開発規律 |
| [0029](./0029-syncpack-package-json-consistency.md) | モノレポ内 package.json の整合性を syncpack で機械強制 | 📋 開発規律 |
| [0030](./0030-ci-success-umbrella-job.md) | CI Required status checks を集約ジョブ ci-success で 1 本化 | 📋 開発規律 |
| [0031](./0031-github-repository-settings.md) | GitHub リポジトリ設定の方針（Ruleset / マージ動作 / Actions / Security / Features） | 📋 開発規律 |

---

## 🎯 リリースとの関係

各リリース（[5-roadmap/01-roadmap.md](../requirements/5-roadmap/01-roadmap.md) 参照）で参照される ADR：

| リリース | 主な参照 ADR |
|---|---|
| **R0** 基盤整備 | [0012](./0012-turborepo-pnpm-monorepo.md) / [0013](./0013-biome-for-tooling.md) / [0014](./0014-json-schema-as-single-source-of-truth.md) / [0018](./0018-phase-0-tooling-discipline.md) / [0022](./0022-github-actions-incremental-scope.md) / [0023](./0023-github-actions-as-ci-cd.md) / [0024](./0024-dependabot-auto-update-policy.md) / [0025](./0025-commit-scope-convention.md) / [0026](./0026-github-actions-sha-pinning.md) / [0027](./0027-commitlint-base-commit-fetch.md) / [0028](./0028-config-file-format-priority.md) / [0029](./0029-syncpack-package-json-consistency.md) / [0030](./0030-ci-success-umbrella-job.md) / [0031](./0031-github-repository-settings.md) |
| **R1** MVP（最小貫通） | [0001](./0001-postgres-as-job-queue.md) / [0003](./0003-codemirror-over-monaco.md) / [0004](./0004-nestjs-for-backend.md) / [0005](./0005-go-for-grading-worker.md) / [0008](./0008-disposable-sandbox-container.md) / [0011](./0011-llm-provider-abstraction.md) / [0015](./0015-github-oauth-with-extensible-design.md) / [0016](./0016-drizzle-orm-over-prisma.md) / [0017](./0017-w3c-trace-context-in-job-payload.md) |
| **R2** 品質保証パイプライン | [0009](./0009-custom-llm-judge.md) / [0011](./0011-llm-provider-abstraction.md) |
| **R3** サンドボックス強化 | [0008](./0008-disposable-sandbox-container.md) |
| **R4** 観測性 | [0017](./0017-w3c-trace-context-in-job-payload.md) |
| **R5** 仕上げ・公開 | [0002](./0002-aws-single-cloud.md) / [0007](./0007-upstash-redis-over-elasticache.md) |
| **R7** Python 分析パイプライン | [0010](./0010-phased-language-introduction.md) / [0021](./0021-python-code-quality.md) |

---

## 📌 注目 ADR（採用担当者向け）

差別化軸として特に深く読んでほしい 6 件：

1. **[0008: 使い捨てサンドボックスコンテナ](./0008-disposable-sandbox-container.md)** — セキュリティ × スループットのトレードオフ判断、段階的隔離強化（Docker → gVisor → Firecracker）
2. **[0011: LLM プロバイダ抽象化戦略](./0011-llm-provider-abstraction.md)** — ベンダーロックイン回避、可逆な判断の遅延という設計哲学
3. **[0014: JSON Schema を SSoT に](./0014-json-schema-as-single-source-of-truth.md)** — 3 言語（TS/Go/Python）横断の型整合性を構造的に保証
4. **[0017: W3C Trace Context をジョブペイロードに埋め込む](./0017-w3c-trace-context-in-job-payload.md)** — プロセス境界トレース連携、SpanLink vs Parent-Child の議論、OTel Messaging Semantic Conventions 準拠
5. **[0018: 補完ツールを R0 から導入](./0018-phase-0-tooling-discipline.md)** — 「遅延の不可逆性が高い判断には YAGNI を適用しない」というメタ方針の確立
6. **[0019: 要件定義書を 5 バケット時系列構造に再編](./0019-requirements-as-5-buckets.md)** — ドキュメント設計の判断を ADR 化した珍しい例、時系列 × 変更頻度での物理分離

---

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

### 更新方針

- ADR 本文は**いつでも書き換え可能**。判断が変わったら最新状態に直接反映し、ドキュメントを「現時点の答え」として保つ
- 過去の判断履歴を辿りたい場合は `git log -p docs/adr/<file>.md` で参照する（書き換え時に判断の根拠・経緯はコミットメッセージに残す）
- 別の ADR で**完全に置き換えられた**場合のみ `Status` を `Superseded by NNNN` に更新する（リネーム / 統合 / 廃止など、ファイル自体を残しつつ無効化したい時）

### 書くタイミング

- 設計上の選択肢が複数あり、どれかを選んだとき
- 「なぜこうしたんだっけ？」と後から問われそうなとき
- 一般的でない選択をしたとき（標準から外れる場合は必ず）

### 書かないもの

- 自明な技術選定（HTTPS を使う、UTF-8 を使う等）
- コーディング規約レベルの細かい実装詳細
- 個人の好みや一時的な決定

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
