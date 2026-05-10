# AI Coding Drill（Python 版）

> LLM が自動生成したプログラミング問題を、サンドボックス環境で検証・採点する学習サイト。
> 「LLM の出力を信用せず、サンドボックスで動作保証する」設計思想を実装したポートフォリオプロジェクト。

> **このリポジトリは Python 版です**。TS 版（[`yzanbo/ai-coding-drill`](https://github.com/yzanbo/ai-coding-drill)）を [`v1.0.0-typescript`](https://github.com/yzanbo/ai-coding-drill/releases/tag/v1.0.0-typescript) タグ時点で fork し、バックエンド API を Python に pivot した派生版です。Frontend (Next.js) と採点ワーカー (Go) は維持し、バックエンドのみ言語を切り替えます。判断の背景は [ADR 0033](docs/adr/0033-backend-language-pivot-to-python.md) を参照。
>
> なお TS 版（`v1.0.0-typescript`）では共有データ型を `packages/shared-types/` に集約していましたが、Python pivot に伴い **Pydantic を SSoT に統一**し（→ [ADR 0006](docs/adr/0006-json-schema-as-single-source-of-truth.md)）、`packages/shared-types/` は廃止しました。

🚀 **デモ**：_（デプロイ後に追記予定。R5 完了時に公開）_
📊 **ステータス**：**設計フェーズ完了・実装着手前**（Python pivot に伴う ADR 0033〜0041 起票完了、R0 ツーリング着手前）
📚 **設計判断**：[ADR](docs/adr/) として体系的に記録（最新件数は [索引](docs/adr/README.md) を参照）
🛠️ **セットアップして動かしたい場合**：[CONTRIBUTING.md](CONTRIBUTING.md) を参照

---

## 📊 現在の進捗（2026-05 時点）

| フェーズ | 状態 | 内容 |
|---|---|---|
| **設計フェーズ（TS 版）** | ✅ **完了** | ADR / 要件定義書 5 バケット / アーキテクチャ図 3 種 / プロダクトバックログ — `v1.0.0-typescript` タグで凍結 |
| **Python pivot 設計** | ✅ **完了** | バックエンド言語切替（[ADR 0033](docs/adr/0033-backend-language-pivot-to-python.md)）/ FastAPI（[0034](docs/adr/0034-fastapi-for-backend.md)）/ uv（[0035](docs/adr/0035-uv-for-python-package-management.md)）/ pnpm 単独運用（[0036](docs/adr/0036-frontend-monorepo-pnpm-only.md)）/ SQLAlchemy + Alembic（[0037](docs/adr/0037-sqlalchemy-alembic-for-database.md)）/ テストフレームワーク（[0038](docs/adr/0038-test-frameworks.md)）/ mise（[0039](docs/adr/0039-mise-for-task-runner-and-tool-versions.md)）/ Worker 分割 + LLM in Worker（[0040](docs/adr/0040-worker-grouping-and-llm-in-worker.md)）/ 観測性スタック Grafana 系 + Sentry（[0041](docs/adr/0041-observability-stack-grafana-and-sentry.md)）/ ADR 0006 を Pydantic SSoT + 境界別 2 伝送路に再設計 / 要件定義書 5 バケット同期 |
| **R0**〜実装フェーズ | ⏳ 未着手 | R0 基盤立ち上げ（mise / uv / pnpm / Docker Compose / CI / 補完ツール一式）から順次着手 |

> **ポートフォリオとしての位置づけ**：
> 現時点では **設計力・ドキュメント力**が成果物の中心です。Python pivot により、同じ設計を 2 言語で実装した経験そのものを差別化軸にしていきます。実装フェーズが進むにつれ、動くサービス・スクリーンショット・デモ動画・ベンチマーク結果を順次追加します。
>
> - **設計シニア / アーキテクト枠**：現時点で十分に評価可能（[ADR](docs/adr/) を中心に閲覧推奨。設計の言語非依存性は TS 版（`v1.0.0-typescript`）と本リポジトリの差分で確認可能）
> - **フルスタック枠（Python）**：実装着手・MVP 動作完成までお待ちいただくか、設計判断の議論を中心に評価をお願いします
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
| アーキテクチャ設計力 | [02-architecture.md](docs/requirements/2-foundation/02-architecture.md) + [ADR 0004](docs/adr/0004-postgres-as-job-queue.md) / [0009](docs/adr/0009-disposable-sandbox-container.md) / [0010](docs/adr/0010-w3c-trace-context-in-job-payload.md) |
| LLM アプリ設計力 | [03-llm-pipeline.md](docs/requirements/2-foundation/03-llm-pipeline.md) + [ADR 0008](docs/adr/0008-custom-llm-judge.md) / [0007](docs/adr/0007-llm-provider-abstraction.md) |
| セキュリティ・サンドボックス設計 | [ADR 0009](docs/adr/0009-disposable-sandbox-container.md) + [F-04 自動採点](docs/requirements/4-features/F-04-auto-grading.md) |
| 観測性設計（分散トレース連携・Grafana 系統合） | [04-observability.md](docs/requirements/2-foundation/04-observability.md) + [ADR 0010](docs/adr/0010-w3c-trace-context-in-job-payload.md) / [ADR 0041](docs/adr/0041-observability-stack-grafana-and-sentry.md) |
| ドキュメント設計力 | [docs/requirements/README.md](docs/requirements/README.md)（5 バケット時系列構造） |
| アジャイル運用力 | [5-roadmap/01-roadmap.md](docs/requirements/5-roadmap/01-roadmap.md)（DoR / DoD / バックログ / リスクレジスタ） |

---

## ハイライト

このプロジェクトの差別化軸：

1. **LLM 生成 × サンドボックス検証 × 多層品質保証パイプライン**
   生成された問題は、模範解答がサンドボックスで動作することを確認するまで DB に保存されない。「動かないコードが混入する」既存サービスの根本問題を構造的に解決。
   → 詳細：[03-llm-pipeline.md](docs/requirements/2-foundation/03-llm-pipeline.md) / [ADR 0009](docs/adr/0009-disposable-sandbox-container.md)

2. **品質評価の 4 レイヤ防御**（決定論チェック / LLM-as-a-Judge / ユーザー行動シグナル / 集合的評価）
   ミューテーションテスト・複数モデルによる多軸評価・人間評価との相関分析を組み合わせ、LLM 生成物の品質を継続的に担保。
   → 詳細：[ADR 0008: LLM-as-a-Judge を自前実装](docs/adr/0008-custom-llm-judge.md)

3. **Python + Go + TypeScript のポリグロット構成**
   バックエンド API（Python / FastAPI）・採点ワーカー（Go）・フロントエンド（TypeScript / Next.js）を、レイヤごとに適材適所で導入。
   → 詳細：[ADR 0033: バックエンドを Python に pivot](docs/adr/0033-backend-language-pivot-to-python.md) / [ADR 0003: 言語の段階導入](docs/adr/0003-phased-language-introduction.md)

4. **Postgres ジョブキュー**（`SELECT FOR UPDATE SKIP LOCKED` + `LISTEN/NOTIFY`）
   外部キューミドルウェア不要、解答登録とジョブ登録を同一トランザクションで処理。Outbox パターン回避。
   → 詳細：[ADR 0004: Postgres をジョブキューに採用](docs/adr/0004-postgres-as-job-queue.md) / [ADR 0005](docs/adr/0005-redis-not-for-job-queue.md)

5. **使い捨てコンテナによるサンドボックス**（Docker → gVisor → Firecracker の段階強化）
   ジョブごとにコンテナを生成・破棄。前回実行の影響が原理的に残らない強い隔離。
   → 詳細：[ADR 0009: 使い捨てサンドボックスコンテナ](docs/adr/0009-disposable-sandbox-container.md)

6. **LLM プロバイダ抽象化レイヤ**（Anthropic / Google / OpenAI / OpenRouter を差し替え可能）
   モデル選定はベンチマークに基づき適時更新。「アーキテクチャ判断とモデル選定を分離する」設計原則を実装。
   → 詳細：[ADR 0007: LLM プロバイダ抽象化戦略](docs/adr/0007-llm-provider-abstraction.md)

7. **W3C Trace Context をジョブペイロードに埋め込んだプロセス境界トレース連携**
   FastAPI（Producer）→ Postgres → Go Worker 群（採点 / 問題生成、Consumer）が単一 trace_id で連結可視化。標準仕様準拠でベンダー非依存。
   → 詳細：[ADR 0010: W3C Trace Context をジョブペイロードに埋め込む](docs/adr/0010-w3c-trace-context-in-job-payload.md)

8. **Pydantic を SSoT に置いた境界別 2 伝送路型生成**（TS / Go）
   HTTP API 境界は FastAPI 自動 OpenAPI 3.1 → Hey API（TS 型 + Zod + クライアント生成）、Job キュー境界は Pydantic から JSON Schema 出力 → quicktype（Go struct 生成）。Python は Pydantic そのものが型なので追加生成不要。
   → 詳細：[ADR 0006: Pydantic SSoT + 境界別 2 伝送路](docs/adr/0006-json-schema-as-single-source-of-truth.md)

9. **AWS 単独 + IaC（Terraform）+ 観測性（OTel + Grafana 系（Loki / Tempo / Prometheus）+ Sentry）**
   コスト最適化（月 $10〜30）・無料枠活用・運用設計まで含めたエンドツーエンドの構成。3 系統（ログ / トレース / メトリクス）を Grafana 1 画面に統合。
   → 詳細：[ADR 0002: AWS 単独](docs/adr/0002-aws-single-cloud.md) / [ADR 0041: 観測性スタック](docs/adr/0041-observability-stack-grafana-and-sentry.md) / [04-observability.md](docs/requirements/2-foundation/04-observability.md)

---

## 📚 設計判断（ADR）索引

複数案を検討して 1 つを選んだ判断は、すべて [docs/adr/](docs/adr/) に **1 ファイル 1 決定**で記録しています。判断が変わった場合は ADR 本文を直接書き換えて最新状態に保ち、変更経緯は git log で辿ります。

### 🌐 戦略判断（Python pivot）

| ADR | タイトル | キーワード |
|---|---|---|
| [0033](docs/adr/0033-backend-language-pivot-to-python.md) | バックエンドを Python に pivot（NestJS → Python） | 言語切替 / 設計の言語非依存性 / 採用面接駆動 |

### 🏗️ アーキテクチャ判断

| ADR | タイトル | キーワード |
|---|---|---|
| [0004](docs/adr/0004-postgres-as-job-queue.md) | Postgres をジョブキューに採用 | SKIP LOCKED / LISTEN/NOTIFY / Outbox 不要 |
| [0005](docs/adr/0005-redis-not-for-job-queue.md) | Redis をジョブキューでは使わない | 役割の明確化 |
| [0009](docs/adr/0009-disposable-sandbox-container.md) | 使い捨てサンドボックスコンテナ | セキュリティ × スループット |
| [0008](docs/adr/0008-custom-llm-judge.md) | LLM-as-a-Judge を自前実装 | DeepEval / Ragas 不採用 |
| [0003](docs/adr/0003-phased-language-introduction.md) | レイヤ別ポリグロット構成（Python + Go + TypeScript） | ポリグロット戦略 / 役割別配置 |
| [0007](docs/adr/0007-llm-provider-abstraction.md) | LLM プロバイダ抽象化戦略 | ベンダーロックイン回避 |
| [0010](docs/adr/0010-w3c-trace-context-in-job-payload.md) | W3C Trace Context をジョブペイロードに埋め込む | プロセス境界トレース連携 |

### 🔧 技術スタック判断

| ADR | タイトル | キーワード |
|---|---|---|
| [0015](docs/adr/0015-codemirror-over-monaco.md) | CodeMirror 6 採用（Monaco 不採用） | バンドル軽量化 |
| [0034](docs/adr/0034-fastapi-for-backend.md) | バックエンド API に FastAPI 採用 | Python / 型ヒント駆動 / OpenAPI 自動生成 |
| [0014](docs/adr/0014-nestjs-for-backend.md) | バックエンドに NestJS 採用 *(Superseded by 0033, 0034)* | DI / Module / レイヤード設計（移行判断軌跡として保持） |
| [0016](docs/adr/0016-go-for-grading-worker.md) | 採点ワーカーを Go で実装 | シングルバイナリ / goroutine |
| [0011](docs/adr/0011-github-oauth-with-extensible-design.md) | GitHub OAuth + 拡張可能設計 | Strategy パターン |
| [0037](docs/adr/0037-sqlalchemy-alembic-for-database.md) | ORM / マイグレーションに SQLAlchemy 2.0 + Alembic | async / Pydantic 連携 / 標準ツール |
| [0017](docs/adr/0017-drizzle-orm-over-prisma.md) | ORM に Drizzle 採用（Prisma 不採用）*(Superseded by 0033, 0037)* | 型推論 / 生 SQL 親和性（移行判断軌跡として保持） |
| [0041](docs/adr/0041-observability-stack-grafana-and-sentry.md) | 観測性スタックに Grafana 系（Loki / Tempo / Prometheus / Grafana）+ Sentry を採用 | OSS / 3 系統 1 画面統合 / Grafana Cloud 無料枠 / OTLP ネイティブ |

### ☁️ インフラ判断

| ADR | タイトル | キーワード |
|---|---|---|
| [0002](docs/adr/0002-aws-single-cloud.md) | クラウドは AWS 単独 | マルチクラウド不採用 |
| [0012](docs/adr/0012-upstash-redis-over-elasticache.md) | Upstash Redis 採用 | サーバレス / 無料枠 |
| [0013](docs/adr/0013-vercel-for-frontend-hosting.md) | Frontend ホスティングに Vercel を採用 | Next.js ファーストパーティ統合 / 無料枠 |

### 📋 開発規律判断

| ADR | タイトル | キーワード |
|---|---|---|
| [0039](docs/adr/0039-mise-for-task-runner-and-tool-versions.md) | タスクランナー / tool 版数管理に mise を採用 | Turborepo 不採用 / 3 言語横断 |
| [0036](docs/adr/0036-frontend-monorepo-pnpm-only.md) | Frontend ツーリングを `apps/web/` 内に閉じる（Turborepo + pnpm workspaces 不採用） | root を orchestration 専用層に / Biome / Knip / syncpack も apps/web 内 |
| [0035](docs/adr/0035-uv-for-python-package-management.md) | Python パッケージ管理に uv を採用 | Astral 統合 / lockfile / workspace |
| [0020](docs/adr/0020-python-code-quality.md) | Python のコード品質ツール（ruff + pyright + pip-audit + deptry） | Astral 統合 / 可逆な判断の遅延 |
| [0023](docs/adr/0023-turborepo-pnpm-monorepo.md) | Turborepo + pnpm workspaces *(Superseded by 0033, 0036)* | モノレポ運用（軌跡として保持。Python 側は [ADR 0035](docs/adr/0035-uv-for-python-package-management.md)、タスクランナーは [ADR 0039](docs/adr/0039-mise-for-task-runner-and-tool-versions.md) で代替） |
| [0018](docs/adr/0018-biome-for-tooling.md) | TS のコード品質ツールに Biome を採用、設定は `apps/web/` 配下に直接配置 *(Accepted, Amended by 0033 / 0036)* | Rust 製 / 高速 / 単一設定（Frontend 用途として継続採用） |
| [0006](docs/adr/0006-json-schema-as-single-source-of-truth.md) | Pydantic を SSoT に、境界別 2 伝送路で各言語に展開 | Pydantic-first / FastAPI 自動 OpenAPI / Hey API + quicktype |
| [0021](docs/adr/0021-r0-tooling-discipline.md) | 補完ツールを R0 から導入 | lefthook / commitlint / Knip / syncpack / ruff / pyright / pip-audit / deptry |
| [0001](docs/adr/0001-requirements-as-5-buckets.md) | 要件定義書を 5 バケット時系列構造に再編 | ドキュメント設計 / SSoT / 読む順序 vs 書く順序 |
| [0019](docs/adr/0019-go-code-quality.md) | Go のコード品質ツール（gofmt + golangci-lint） | Go 標準 / メタリンター |
| [0040](docs/adr/0040-worker-grouping-and-llm-in-worker.md) | Worker を `apps/workers/<name>/` で系統別に分割、LLM 呼び出しは Worker 側に集約 | judge プロンプトは `apps/workers/grading/prompts/judge/`、generation プロンプトは `apps/workers/generation/prompts/generation/` に同居 |
| [0038](docs/adr/0038-test-frameworks.md) | テストフレームワーク（pytest / Vitest + Playwright / Go testing + testify） | 言語ごとに標準ツール |
| [0026](docs/adr/0026-github-actions-incremental-scope.md) | GitHub Actions のスコープを段階的に拡張（R0 は最小） | YAGNI / 段階拡張 / 無料枠節約 |
| [0025](docs/adr/0025-github-actions-as-ci-cd.md) | CI/CD ツールに GitHub Actions を採用 | コードホスト統合 / OIDC キーレス |
| [0028](docs/adr/0028-dependabot-auto-update-policy.md) | 依存関係の自動更新ポリシー（Dependabot） | 週次 / メジャー除外 / グループ化 |
| [0029](docs/adr/0029-commit-scope-convention.md) | コミット scope 規約（モノレポ領域 + 自動更新用 deps / deps-dev） | scope-enum / Dependabot 連携 |
| [0027](docs/adr/0027-github-actions-sha-pinning.md) | サードパーティアクションを SHA でピン止め | サプライチェーン攻撃耐性 |
| [0030](docs/adr/0030-commitlint-base-commit-fetch.md) | commitlint の base コミット取得を iterative deepen 方式で | shallow-exclude 不可 / `--deepen=20` |
| [0022](docs/adr/0022-config-file-format-priority.md) | 設定ファイル形式の選定方針（TS > JSONC > YAML） | ツール強制 / ecosystem 慣習 |
| [0024](docs/adr/0024-syncpack-package-json-consistency.md) | syncpack による `package.json` 整合性ゲート *(Accepted, Amended by 0033 / 0036)* | apps/web 配下に再配置 + 単一 package.json 用 3 ルールに縮小 |
| [0031](docs/adr/0031-ci-success-umbrella-job.md) | CI Required status checks を集約ジョブ `ci-success` で 1 本化 | umbrella job / `needs.*.result` |
| [0032](docs/adr/0032-github-repository-settings.md) | GitHub リポジトリ設定の方針（Ruleset / マージ動作 / Actions / Security） | デフォルト変更項目の棚卸し |

→ 索引一覧：[docs/adr/README.md](docs/adr/README.md)
→ ADR 運用ルール：1 決定 1 ファイル / 判断更新時は本文を直接書き換えて最新状態に保つ（履歴は git log）/ 代替案・トレードオフ・将来見直しトリガーを必ず記録
→ Status の読み方：***Amended by NNNN*** = 採用判断は維持しつつ前提（言語スタック・配置範囲等）が後続 ADR で更新された / ***Superseded by NNNN*** = 採用判断そのものが取り消され別 ADR に置き換えられた（詳細は [docs/adr/README.md: ステータス](docs/adr/README.md#ステータス)）

---

## 技術スタック概要

| レイヤ | 採用技術 |
|---|---|
| **言語ランタイム** | Python 3.14 / Node.js 22 / Go 1.23（mise で固定、[ADR 0039](docs/adr/0039-mise-for-task-runner-and-tool-versions.md)） |
| **フロントエンド** | Next.js 16+（App Router）+ Tailwind CSS + CodeMirror 6 + TanStack Query |
| **バックエンド API** | Python + **FastAPI**（[ADR 0034](docs/adr/0034-fastapi-for-backend.md)） |
| **ORM / マイグレーション** | SQLAlchemy 2.0（async）+ Alembic（[ADR 0037](docs/adr/0037-sqlalchemy-alembic-for-database.md)） |
| **Python パッケージ管理** | uv（lockfile / workspace、[ADR 0035](docs/adr/0035-uv-for-python-package-management.md)） |
| **Python Lint / Format** | ruff（[ADR 0020](docs/adr/0020-python-code-quality.md)） |
| **Python 型チェッカー** | pyright（[ADR 0020](docs/adr/0020-python-code-quality.md)） |
| **Python 依存衛生 / 脆弱性** | deptry / pip-audit（[ADR 0020](docs/adr/0020-python-code-quality.md)） |
| **採点ワーカー** | Go（`apps/workers/grading/`）+ Docker クライアント（公式）+ pgx（[ADR 0040](docs/adr/0040-worker-grouping-and-llm-in-worker.md)） |
| **問題生成ワーカー** | Go（`apps/workers/generation/`、将来追加、[ADR 0040](docs/adr/0040-worker-grouping-and-llm-in-worker.md)） |
| **データストア** | PostgreSQL 16（DB + ジョブキュー兼任）+ Upstash Redis（キャッシュ・セッション） |
| **LLM** | プロバイダ抽象化（Anthropic / Google / OpenAI / OpenRouter 差し替え可、[ADR 0007](docs/adr/0007-llm-provider-abstraction.md)） |
| **サンドボックス** | Docker（使い捨てコンテナ）→ R3 で gVisor → R9 で Firecracker |
| **タスクランナー / 版数管理** | mise（3 言語横断、Turborepo 不採用、[ADR 0039](docs/adr/0039-mise-for-task-runner-and-tool-versions.md)） |
| **モノレポ管理** | apps 配下で言語ごとに完結：pnpm（`apps/web/`）+ uv workspace（`apps/api/`）+ go modules（`apps/workers/<name>/` ごとに独立）（[ADR 0036](docs/adr/0036-frontend-monorepo-pnpm-only.md) / [ADR 0040](docs/adr/0040-worker-grouping-and-llm-in-worker.md)） |
| **テスト** | pytest（API）/ Vitest + Playwright（Web）/ Go testing + testify（Worker）（[ADR 0038](docs/adr/0038-test-frameworks.md)） |
| **TS コード品質** | Biome（[ADR 0018](docs/adr/0018-biome-for-tooling.md)） |
| **Go コード品質** | gofmt + golangci-lint（[ADR 0019](docs/adr/0019-go-code-quality.md)） |
| **インフラ** | AWS（ECS Fargate + EC2 + RDS + ECR + Route 53）+ Terraform |
| **観測性** | OpenTelemetry + Grafana + Loki + Tempo + Prometheus + Sentry（[ADR 0041](docs/adr/0041-observability-stack-grafana-and-sentry.md)） |
| **CI/CD** | GitHub Actions |

> Python スタックは [ADR 0033](docs/adr/0033-backend-language-pivot-to-python.md) で方針確定 → ADR 0034〜0040 で個別技術を順次起票し、現時点で全主要スタックを確定済み。

詳細は [2-foundation/05-runtime-stack.md](docs/requirements/2-foundation/05-runtime-stack.md) を参照。

---

## アーキテクチャ概要

```
[User Browser]
     ↓
[Next.js (Vercel)]
     ↓
[Python API (FastAPI, ECS Fargate)]
     ├── PostgreSQL (RDS)
     │     └── jobs テーブル（LISTEN/NOTIFY で Worker 群に通知、Backend は enqueue のみ）
     └── Upstash Redis（キャッシュ・セッション）

LLM 呼び出しは Worker 側に集約（ADR 0040）：
     ↓ jobs テーブル経由
[Go Worker 群 (apps/workers/<name>/, 独立 Go module 群)]
 ├─ apps/workers/grading/ (EC2)
 │   ├── Docker Engine + 使い捨て採点コンテナ（初期 TS = tsx + Vitest 実行、将来多言語対応）
 │   └── judge LLM 呼び出し（プロバイダ抽象化レイヤ経由）
 └─ apps/workers/generation/ (EC2、将来追加)
     └── 問題生成 LLM 呼び出し
```

詳細は [2-foundation/02-architecture.md](docs/requirements/2-foundation/02-architecture.md) を参照。

---

## リリース計画

| リリース | アウトカム | 状態 |
|---|---|---|
| R0 | 基盤立ち上げ（mise / uv / pnpm / Docker Compose / CI 雛形 / 補完ツール一式） | _設計完了・着手前_ |
| R1 | MVP（認証・問題生成・採点・最低限フロント・一気通貫動作） | _未着手_ |
| R2 | 品質保証パイプライン（Judge・ミューテーションテスト・非同期ジョブ完成） | _未着手_ |
| R3 | サンドボックス強化（gVisor + ベンチマーク） | _未着手_ |
| R4 | 観測性（OTel・Grafana 系（Loki / Tempo / Prometheus）・Sentry・管理ダッシュボード、[ADR 0041](docs/adr/0041-observability-stack-grafana-and-sentry.md)） | _未着手_ |
| R5 | 仕上げ（IaC・E2E・本番デプロイ・README 完成） | _未着手_ |
| R7 以降 | 任意（適応型出題・`apps/workers/generation/` 切り出し・多言語化・Firecracker 等） | _任意_ |

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
- **遅延の不可逆性が高い判断には YAGNI を適用しない**：プロセス境界トレース連携や補完ツールは R0 から導入（[ADR 0010](docs/adr/0010-w3c-trace-context-in-job-payload.md) / [ADR 0021](docs/adr/0021-r0-tooling-discipline.md)）
- **規模に応じた選定**：このプロジェクト規模（小〜中）に最適なツールを選ぶ。Bazel・Kafka・Nx 等の "本格派" は不採用
- **設計判断を ADR で記録**：「なぜそう決めたか」「他案は何だったか」を残す（判断更新時は ADR 本文を直接書き換え、変更経緯は git log で辿る）

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
