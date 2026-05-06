# AI Coding Drill

> LLM が自動生成したプログラミング問題を、サンドボックス環境で検証・採点する学習サイト。
> 「LLM の出力を信用せず、サンドボックスで動作保証する」設計思想を実装したポートフォリオプロジェクト。

🚀 **デモ**：_（デプロイ後に追記予定。R5 完了時に公開）_
📊 **ステータス**：**設計フェーズ完了 / R1 着手予定**（[ロードマップ](docs/requirements/5-roadmap/01-roadmap.md) 参照）
📚 **設計判断**：[ADR](docs/adr/) として体系的に記録（最新件数は [索引](docs/adr/README.md) を参照）
🛠️ **セットアップして動かしたい場合**：[CONTRIBUTING.md](CONTRIBUTING.md) を参照

---

## 📊 現在の進捗（2026-05 時点）

| フェーズ | 状態 | 完了内容 |
|---|---|---|
| **設計フェーズ** | ✅ **完了** | ADR / 要件定義書 5 バケット（うち R0 で `06-dev-workflow` / `07-github-settings` を新設） / アーキテクチャ図 3 種 / プロダクトバックログ |
| **R0** 基盤整備 | ⏳ **着手予定** | モノレポ・Docker Compose・CI 雛形・補完ツール一式 |
| **R1** MVP（最小貫通） | ⏳ 未着手 | F-01〜F-05 の一気通貫動作 |
| **R2〜R5** 仕上げ | ⏳ 未着手 | 品質保証 / サンドボックス強化 / 観測性 / 公開 |

> **ポートフォリオとしての位置づけ**：
> 現時点では **設計力・ドキュメント力**が成果物の中心です。実装フェーズ（R1〜）が進むにつれ、動くサービス・スクリーンショット・デモ動画・ベンチマーク結果を順次追加していきます。
>
> - **設計シニア / アーキテクト枠**：現時点で十分に評価可能（[ADR](docs/adr/) を中心に閲覧推奨）
> - **フルスタック枠**：R1（MVP 動作）完成までお待ちいただくか、設計判断の議論を中心に評価をお願いします
>
> 進捗は [5-roadmap/01-roadmap.md](docs/requirements/5-roadmap/01-roadmap.md) で更新します。

---

## 🎯 ポートフォリオとして見てほしいもの

採用担当者・面接官の方は、以下の順で読むと短時間で評価できます：

1. **[本 README のハイライト](#ハイライト)** ← 今ここ（差別化軸の概要）
2. **[ADR（設計判断の記録）](docs/adr/)** ← 設計力アピールの中核
3. **[要件定義書 5 バケット構造](docs/requirements/)** ← ドキュメント設計力
4. **個別機能の詳細仕様**：[F-01](docs/requirements/4-features/F-01-github-oauth-auth.md) 〜 [F-05](docs/requirements/4-features/F-05-learning-history.md)
5. **動くデモ** ← R5 公開後

### 評価軸別の見どころマップ

| 評価したい観点 | 推奨閲覧 |
|---|---|
| 設計判断・トレードオフの言語化能力 | [docs/adr/](docs/adr/) — 全 ADR の索引 |
| アーキテクチャ設計力 | [02-architecture.md](docs/requirements/2-foundation/02-architecture.md) + [ADR 0001](docs/adr/0001-postgres-as-job-queue.md) / [0008](docs/adr/0008-disposable-sandbox-container.md) / [0017](docs/adr/0017-w3c-trace-context-in-job-payload.md) |
| LLM アプリ設計力 | [03-llm-pipeline.md](docs/requirements/2-foundation/03-llm-pipeline.md) + [ADR 0009](docs/adr/0009-custom-llm-judge.md) / [0011](docs/adr/0011-llm-provider-abstraction.md) |
| セキュリティ・サンドボックス設計 | [ADR 0008](docs/adr/0008-disposable-sandbox-container.md) + [F-04 自動採点](docs/requirements/4-features/F-04-auto-grading.md) |
| 観測性設計（分散トレース連携） | [04-observability.md](docs/requirements/2-foundation/04-observability.md) + [ADR 0017](docs/adr/0017-w3c-trace-context-in-job-payload.md) |
| ドキュメント設計力 | [docs/requirements/README.md](docs/requirements/README.md)（5 バケット時系列構造） |
| アジャイル運用力 | [5-roadmap/01-roadmap.md](docs/requirements/5-roadmap/01-roadmap.md)（DoR / DoD / バックログ / リスクレジスタ） |

---

## ハイライト

このプロジェクトの差別化軸：

1. **LLM 生成 × サンドボックス検証 × 多層品質保証パイプライン**
   生成された問題は、模範解答がサンドボックスで動作することを確認するまで DB に保存されない。「動かないコードが混入する」既存サービスの根本問題を構造的に解決。
   → 詳細：[03-llm-pipeline.md](docs/requirements/2-foundation/03-llm-pipeline.md) / [ADR 0008](docs/adr/0008-disposable-sandbox-container.md)

2. **品質評価の 4 レイヤ防御**（決定論チェック / LLM-as-a-Judge / ユーザー行動シグナル / 集合的評価）
   ミューテーションテスト・複数モデルによる多軸評価・人間評価との相関分析を組み合わせ、LLM 生成物の品質を継続的に担保。
   → 詳細：[ADR 0009: LLM-as-a-Judge を自前実装](docs/adr/0009-custom-llm-judge.md)

3. **TypeScript + Go のポリグロット構成**（R7 で Python 追加）
   実装速度（NestJS）・採点ワーカーの軽量並列性（Go）・LLM/評価エコシステム（Python）を、フェーズに応じて適材適所で導入。
   → 詳細：[ADR 0010: 言語の段階導入](docs/adr/0010-phased-language-introduction.md)

4. **Postgres ジョブキュー**（`SELECT FOR UPDATE SKIP LOCKED` + `LISTEN/NOTIFY`）
   外部キューミドルウェア不要、解答登録とジョブ登録を同一トランザクションで処理。Outbox パターン回避。
   → 詳細：[ADR 0001: Postgres をジョブキューに採用](docs/adr/0001-postgres-as-job-queue.md) / [ADR 0006](docs/adr/0006-redis-not-for-job-queue.md)

5. **使い捨てコンテナによるサンドボックス**（Docker → gVisor → Firecracker の段階強化）
   ジョブごとにコンテナを生成・破棄。前回実行の影響が原理的に残らない強い隔離。
   → 詳細：[ADR 0008: 使い捨てサンドボックスコンテナ](docs/adr/0008-disposable-sandbox-container.md)

6. **LLM プロバイダ抽象化レイヤ**（Anthropic / Google / OpenAI / OpenRouter を差し替え可能）
   モデル選定はベンチマークに基づき適時更新。「アーキテクチャ判断とモデル選定を分離する」設計原則を実装。
   → 詳細：[ADR 0011: LLM プロバイダ抽象化戦略](docs/adr/0011-llm-provider-abstraction.md)

7. **W3C Trace Context をジョブペイロードに埋め込んだプロセス境界トレース連携**
   NestJS（Producer）→ Postgres → Go ワーカー（Consumer）が単一 trace_id で連結可視化。標準仕様準拠でベンダー非依存。
   → 詳細：[ADR 0017: W3C Trace Context をジョブペイロードに埋め込む](docs/adr/0017-w3c-trace-context-in-job-payload.md)

8. **JSON Schema を SSoT とする 3 言語横断型生成**（TS / Go / Python）
   スキーマ変更が 1 箇所で全言語追従。新言語追加コスト最小。
   → 詳細：[ADR 0014: JSON Schema を SSoT に](docs/adr/0014-json-schema-as-single-source-of-truth.md)

9. **AWS 単独 + IaC（Terraform）+ 観測性（OTel + Grafana + Sentry）**
   コスト最適化（月 $10〜30）・無料枠活用・運用設計まで含めたエンドツーエンドの構成。
   → 詳細：[ADR 0002: AWS 単独](docs/adr/0002-aws-single-cloud.md) / [04-observability.md](docs/requirements/2-foundation/04-observability.md)

---

## 📚 設計判断（ADR）索引

複数案を検討して 1 つを選んだ判断は、すべて [docs/adr/](docs/adr/) に **1 ファイル 1 決定 / Append-only** で記録しています。

### 🏗️ アーキテクチャ判断

| ADR | タイトル | キーワード |
|---|---|---|
| [0001](docs/adr/0001-postgres-as-job-queue.md) | Postgres をジョブキューに採用 | SKIP LOCKED / LISTEN/NOTIFY / Outbox 不要 |
| [0006](docs/adr/0006-redis-not-for-job-queue.md) | Redis をジョブキューでは使わない | 役割の明確化 |
| [0008](docs/adr/0008-disposable-sandbox-container.md) | 使い捨てサンドボックスコンテナ | セキュリティ × スループット |
| [0009](docs/adr/0009-custom-llm-judge.md) | LLM-as-a-Judge を自前実装 | DeepEval / Ragas 不採用 |
| [0010](docs/adr/0010-phased-language-introduction.md) | 言語の段階導入（TS+Go → Python） | ポリグロット戦略 |
| [0011](docs/adr/0011-llm-provider-abstraction.md) | LLM プロバイダ抽象化戦略 | ベンダーロックイン回避 |
| [0017](docs/adr/0017-w3c-trace-context-in-job-payload.md) | W3C Trace Context をジョブペイロードに埋め込む | プロセス境界トレース連携 |

### 🔧 技術スタック判断

| ADR | タイトル | キーワード |
|---|---|---|
| [0003](docs/adr/0003-codemirror-over-monaco.md) | CodeMirror 6 採用（Monaco 不採用） | バンドル軽量化 |
| [0004](docs/adr/0004-nestjs-for-backend.md) | バックエンドに NestJS 採用 | DI / Module / レイヤード設計 |
| [0005](docs/adr/0005-go-for-grading-worker.md) | 採点ワーカーを Go で実装 | シングルバイナリ / goroutine |
| [0015](docs/adr/0015-github-oauth-with-extensible-design.md) | GitHub OAuth + 拡張可能設計 | Strategy パターン |
| [0016](docs/adr/0016-drizzle-orm-over-prisma.md) | ORM に Drizzle 採用（Prisma 不採用） | 型推論 / 生 SQL 親和性 |

### ☁️ インフラ判断

| ADR | タイトル | キーワード |
|---|---|---|
| [0002](docs/adr/0002-aws-single-cloud.md) | クラウドは AWS 単独 | マルチクラウド不採用 |
| [0007](docs/adr/0007-upstash-redis-over-elasticache.md) | Upstash Redis 採用 | サーバレス / 無料枠 |

### 📋 開発規律判断

| ADR | タイトル | キーワード |
|---|---|---|
| [0012](docs/adr/0012-turborepo-pnpm-monorepo.md) | Turborepo + pnpm workspaces | モノレポ運用 |
| [0013](docs/adr/0013-biome-for-tooling.md) | TS のコード品質ツールに Biome を採用、設定はルート直接配置 | Rust 製 / 高速 / 単一設定 |
| [0014](docs/adr/0014-json-schema-as-single-source-of-truth.md) | JSON Schema を SSoT に | 3 言語型自動生成 |
| [0018](docs/adr/0018-phase-0-tooling-discipline.md) | 補完ツールを R0 から導入 | Knip / lefthook / commitlint / syncpack |
| [0019](docs/adr/0019-requirements-as-5-buckets.md) | 要件定義書を 5 バケット時系列構造に再編 | ドキュメント設計 / SSoT / 読む順序 vs 書く順序 |
| [0020](docs/adr/0020-go-code-quality.md) | Go のコード品質ツール（gofmt + golangci-lint） | Go 標準 / メタリンター |
| [0021](docs/adr/0021-python-code-quality.md) | Python のコード品質ツール（ruff、型チェッカーは Phase 7 着手時決定） | Astral 統合 / 可逆な判断の遅延 |
| [0022](docs/adr/0022-github-actions-incremental-scope.md) | GitHub Actions のスコープを段階的に拡張（R0 は最小） | YAGNI / 段階拡張 / 無料枠節約 |
| [0023](docs/adr/0023-github-actions-as-ci-cd.md) | CI/CD ツールに GitHub Actions を採用 | コードホスト統合 / OIDC キーレス |
| [0024](docs/adr/0024-dependabot-auto-update-policy.md) | 依存関係の自動更新ポリシー（Dependabot） | 週次 / メジャー除外 / グループ化 |
| [0025](docs/adr/0025-commit-scope-convention.md) | コミット scope 規約（モノレポ領域 + 自動更新用 deps / deps-dev） | scope-enum / Dependabot 連携 |
| [0026](docs/adr/0026-github-actions-sha-pinning.md) | サードパーティアクションを SHA でピン止め | サプライチェーン攻撃耐性 |
| [0027](docs/adr/0027-commitlint-base-commit-fetch.md) | commitlint の base コミット取得を iterative deepen 方式で | shallow-exclude 不可 / `--deepen=20` |
| [0028](docs/adr/0028-config-file-format-priority.md) | 設定ファイル形式の選定方針（TS > JSONC > YAML） | ツール強制 / ecosystem 慣習 |
| [0029](https://github.com/yzanbo/ai-coding-drill/pull/15) | syncpack によるモノレポ `package.json` 整合性ゲート（**PR #15 マージ予定**） | バージョン揃え / `workspace:*` 強制 |
| [0030](docs/adr/0030-ci-success-umbrella-job.md) | CI Required status checks を集約ジョブ `ci-success` で 1 本化 | umbrella job / `needs.*.result` |
| [0031](docs/adr/0031-github-repository-settings.md) | GitHub リポジトリ設定の方針（Ruleset / マージ動作 / Actions / Security） | デフォルト変更項目の棚卸し |

→ 索引一覧：[docs/adr/README.md](docs/adr/README.md)
→ ADR 運用ルール：1 決定 1 ファイル / Append-only / 代替案・トレードオフ・将来見直しトリガーを必ず記録

---

## 技術スタック概要

| レイヤ | 採用技術 |
|---|---|
| **フロントエンド** | Next.js（App Router）+ Tailwind CSS + CodeMirror 6 + TanStack Query |
| **バックエンド API** | NestJS（TypeScript）+ Passport（GitHub OAuth）+ Drizzle ORM |
| **採点ワーカー** | Go + Docker クライアント（公式）+ pgx |
| **データストア** | PostgreSQL 16（DB + ジョブキュー兼任）+ Upstash Redis（キャッシュ・セッション） |
| **LLM** | プロバイダ抽象化（Anthropic / Gemini / OpenAI / OpenRouter 差し替え可） |
| **サンドボックス** | Docker（使い捨てコンテナ）→ R3 で gVisor → R9 で Firecracker |
| **モノレポ** | Turborepo + pnpm workspaces |
| **コード品質** | Biome（lint+format）+ TypeScript（tsc）+ gofmt + golangci-lint |
| **インフラ** | AWS（ECS Fargate + EC2 + RDS + ECR + Route 53）+ Terraform |
| **観測性** | OpenTelemetry + Grafana + Loki + Tempo + Sentry |
| **CI/CD** | GitHub Actions |

詳細は [2-foundation/05-runtime-stack.md](docs/requirements/2-foundation/05-runtime-stack.md) を参照。

---

## アーキテクチャ概要

```
[User Browser]
     ↓
[Next.js (Vercel)]
     ↓
[NestJS API (ECS Fargate)]
     ├── PostgreSQL (RDS) ← jobs テーブルが LISTEN/NOTIFY でワーカーに通知
     ├── Upstash Redis（キャッシュ・セッション）
     └── LLM API（プロバイダ抽象化レイヤ経由）
            ↓
[Go 採点ワーカー (EC2)]
     ├── Docker Engine
     └── 使い捨て採点コンテナ（Vitest 実行）
```

詳細は [2-foundation/02-architecture.md](docs/requirements/2-foundation/02-architecture.md) を参照。

---

## リリース計画

| リリース | アウトカム | 状態 |
|---|---|---|
| R0 | 基盤整備（モノレポ・Docker Compose・CI 雛形・補完ツール一式） | _未着手_ |
| R1 | MVP（認証・問題生成・採点・最低限フロント・一気通貫動作） | _未着手_ |
| R2 | 品質保証パイプライン（Judge・ミューテーションテスト・非同期ジョブ完成） | _未着手_ |
| R3 | サンドボックス強化（gVisor + ベンチマーク） | _未着手_ |
| R4 | 観測性（OTel・Grafana・Sentry・管理ダッシュボード） | _未着手_ |
| R5 | 仕上げ（IaC・E2E・本番デプロイ・README 完成） | _未着手_ |
| R6 以降 | 任意（適応型出題・LLM ヒント・Python 評価パイプライン・多言語化・Firecracker） | _任意_ |

詳細は [5-roadmap/01-roadmap.md](docs/requirements/5-roadmap/01-roadmap.md) を参照。

---

## ドキュメント索引

### 要件定義書（5 バケット時系列構造）

| # | バケット | 役割 | 変更頻度 |
|---|---|---|---|
| 1 | [1-vision/](docs/requirements/1-vision/) | プロジェクトビジョン・ペルソナ・ユーザーストーリー | 極小 |
| 2 | [2-foundation/](docs/requirements/2-foundation/) | 非機能・アーキテクチャ・LLM パイプライン・観測性・実装技術・開発フロー | 小 |
| 3 | [3-cross-cutting/](docs/requirements/3-cross-cutting/) | ER 図・API 共通仕様 | 中 |
| 4 | [4-features/](docs/requirements/4-features/) | 個別機能（F-XX）の詳細仕様 | 大 |
| 5 | [5-roadmap/](docs/requirements/5-roadmap/) | ロードマップ・プロダクトバックログ・スプリント運用 | 大 |

→ 全体マップ：[docs/requirements/README.md](docs/requirements/README.md)

### 個別機能（4-features/）

| ID | 機能名 |
|---|---|
| [F-01](docs/requirements/4-features/F-01-github-oauth-auth.md) | GitHub OAuth ログイン |
| [F-02](docs/requirements/4-features/F-02-problem-generation.md) | 問題生成リクエスト |
| [F-03](docs/requirements/4-features/F-03-problem-display-and-answer.md) | 問題表示・解答入力 |
| [F-04](docs/requirements/4-features/F-04-auto-grading.md) | 自動採点 |
| [F-05](docs/requirements/4-features/F-05-learning-history.md) | 学習履歴・統計 |

### その他

- [SYSTEM_OVERVIEW.md](SYSTEM_OVERVIEW.md) — 物理配置・コンポーネントの責務・ジョブの流れ
- [docs/runbook/](docs/runbook/) — 運用 Runbook（R4 以降で整備）

---

## 設計原則

このプロジェクトで一貫している設計判断の哲学：

- **可逆な判断は遅延させる**：LLM モデル選定・Python 型チェッカー選定など、市場が変化する領域は実装着手時に決定
- **過剰設計を避ける**：使うか分からない抽象化を先取りで作らない（YAGNI）
- **ただし拡張容易性は構造的に確保**：認証プロバイダ・LLM プロバイダ・サンドボックスランタイムは差し替え可能に
- **遅延の不可逆性が高い判断には YAGNI を適用しない**：プロセス境界トレース連携や補完ツールは R0 から導入（[ADR 0017](docs/adr/0017-w3c-trace-context-in-job-payload.md) / [ADR 0018](docs/adr/0018-phase-0-tooling-discipline.md)）
- **規模に応じた選定**：このプロジェクト規模（小〜中）に最適なツールを選ぶ。Bazel・Kafka・Nx 等の "本格派" は不採用
- **設計判断を ADR で記録**：「なぜそう決めたか」「他案は何だったか」を Append-only で残す

---

## 開発参加・セットアップ

このプロジェクトをローカルで動かしたい場合は **[CONTRIBUTING.md](CONTRIBUTING.md)** を参照してください。
セットアップ手順 / 環境変数 / 開発コマンド / トラブルシューティング / カスタムコマンド一覧 が掲載されています。

---

## ライセンス

[MIT License](LICENSE) © 2026 Yohei Jinbo

---

## 著者

神保 陽平 — Backend / AI Engineer 候補
