# 0026. GitHub Actions のスコープを段階的に拡張する

- **Status**: Accepted
- **Date**: 2026-05-09 <!-- Python pivot（ADR 0033）と mise 採用（ADR 0039）に追従して R0 範囲を拡張 -->
- **Decision-makers**: 神保 陽平

## Context（背景・課題）

R0（リポジトリ初期セットアップ）時点で GitHub Actions の構成を決める必要がある。
このとき、以下の二つの選択肢がある：

1. **最終形（test / build / e2e / security scan / deploy 等）を最初から構築する**
2. **R0 に必要な最小構成だけ作り、後続フェーズで段階拡張する**

リポジトリ規約 ([CLAUDE.md](../../.claude/CLAUDE.md)) の設計原則は「YAGNI：使うか分からない抽象化を先取りで作らない」「可逆な判断は遅延させる」を掲げている。
CI に組み込むべき項目（テストランナーの並列度、必須化する status checks、マトリクス対象、E2E のフレームワーク等）は **対象となる実装が存在しない時点では合理的に決められない** という性質を持つ。

一方で、[ADR 0021](./0021-r0-tooling-discipline.md) で導入済みの commitlint / Biome / 型チェックは、ローカルの lefthook と CI の両方で実行することにより初めて「PR レベルで規約違反を弾く」効果を持つ。これらは R0 時点で既に対象資産（コミット履歴・設定ファイル）が存在するため、CI 化の判断は今下せる。

つまり「R0 で意味があるもの」と「R0 では決められないもの」が混在している。

### Python pivot（2026-05-09）に伴う R0 範囲の拡張

[ADR 0033](./0033-backend-language-pivot-to-python.md) でバックエンドが Python に pivot し、Backend は **R7 分析パイプライン用ではなく R0 baseline の対象**となった。これに伴い：

- **Python 側のコード品質ツール**（ruff / pyright、→ [ADR 0020](./0020-python-code-quality.md)）は commitlint / Biome / typecheck と同列の R0 baseline に格上げ
- **Python パッケージ管理**（uv、→ [ADR 0035](./0035-uv-for-python-package-management.md)）は CI で pip-audit による脆弱性スキャンを R0 から走らせる前提
- **タスクランナー / tool 版数管理**（mise、→ [ADR 0039](./0039-mise-for-task-runner-and-tool-versions.md)）は CI 上のジョブを `mise run <task>` 形式で統一する前提
- **Go 側のコード品質ツール**（gofmt + golangci-lint、→ [ADR 0019](./0019-go-code-quality.md)）は Worker 実装着手時に skeleton として R0 ジョブ枠を先置きしておくと、有効化が低コストで済む

## Decision（決定内容）

**GitHub Actions は R0 では「コード品質を機械強制する最小構成（言語横断 commitlint + 各言語の lint+format / 型 / 脆弱性スキャン）」のみを実装し、それ以外のチェック（test / build / E2E / deploy 等）は対応する実装フェーズで段階的に追加する。**

R0 に含める（**実装済み or 実装直前**）：

| 状態 | 項目 | 言語 | 内容 |
|---|---|---|---|
| ✅ 実装済み | `commitlint` | 横断 | PR の base..head / push の before..after を範囲検証 |
| ✅ 実装済み | `Biome` | TS | `mise run web-lint` 経由で `biome check`（lint + format 検証、書き込みなし） |
| ✅ 実装済み | `typecheck` (TS) | TS | `mise run web-typecheck` 経由で `tsc --noEmit`（R0 時点では TS workspace 未追加のため no-op） |
| 🔧 R0 拡張 | `ruff` | Python | `mise run api-lint` 経由で `ruff check`（lint + format 検証） → [ADR 0020](./0020-python-code-quality.md) |
| 🔧 R0 拡張 | `pyright` | Python | `mise run api-typecheck` 経由で `pyright`（型検証、`typeCheckingMode = "basic"` から開始） → [ADR 0020](./0020-python-code-quality.md) |
| 🔧 R0 拡張 | `pip-audit` | Python | `mise run api-audit` 経由で `uv.lock` の脆弱性スキャン → [ADR 0035](./0035-uv-for-python-package-management.md) |
| 🔧 R0 skeleton | `golangci-lint` | Go | `mise run worker-lint`（Worker 実装着手前は no-op、実装後に有効化） → [ADR 0019](./0019-go-code-quality.md) |
| ✅ 実装済み | `syncpack` | TS | `mise run sync-packages` 経由（モノレポ依存整合性、Frontend 限定） |
| ✅ 実装済み | `knip` | TS | `mise run knip-check` 経由（未使用 export / file / dep 検出、Frontend 限定） |
| 🔧 R0 拡張 | mise セットアップ | 横断 | `jdx/mise-action` で `mise.toml` 記載の tool 版数（Python / Node / Go / uv / pnpm）を統一インストール → [ADR 0039](./0039-mise-for-task-runner-and-tool-versions.md) |
| ✅ 実装済み | アクション SHA ピン止め | 横断 | 全 third-party アクション（`actions/checkout` / `pnpm/action-setup` / `jdx/mise-action` 等）を 40 文字 SHA + バージョンコメント形式で固定 → [ADR 0027](./0027-github-actions-sha-pinning.md) |
| 🔧 R0 拡張 | Dependabot | 横断 | `.github/dependabot.yml` で github-actions / npm に加え **pip（uv 経由 / Python 依存）** の週次自動更新 PR → [ADR 0028](./0028-dependabot-auto-update-policy.md) |

R0 では決めない（対応フェーズで追加）：

| 状態 | 追加時期 | 項目 | 据え置く理由 |
|---|---|---|---|
| ⏳ 未実装 | Backend 実装着手時（R0〜R1） | Python テスト：`pytest` / `pytest-asyncio` / `httpx`（→ [ADR 0038](./0038-test-frameworks.md)） | テストが書かれ始めてから接続する |
| ⏳ 未実装 | Frontend 実装着手時（R1） | TS テスト：`Vitest` / `React Testing Library`（→ [ADR 0038](./0038-test-frameworks.md)） | テストが書かれ始めてから接続する |
| ⏳ 未実装 | Worker 実装着手時（R1〜R2） | Go テスト：`go test` / `testify`（→ [ADR 0038](./0038-test-frameworks.md)） | grading-worker の実装開始後 |
| ⏳ 未実装 | DB 実装着手時（R0〜R1） | DB マイグレーション drift 検証：`alembic check`（→ [ADR 0037](./0037-sqlalchemy-alembic-for-database.md)） | スキーマ確定後 |
| ⏳ 未実装 | R2 | Docker build 検証（API・Worker のイメージビルド） | Dockerfile 確定後 |
| ⏳ 未実装 | R2〜R3 | E2E（`Playwright`） | Web の主要画面が揃ってから |
| ⏳ 未実装 | R3 | JSON Schema → 各言語型 の drift チェック | `packages/shared-types` の運用開始後 |
| ⏳ 未実装 | R3〜 | Terraform `fmt` / `validate` / `plan` | `infra/` 着手後 |
| ⏳ 未実装 | 本番直前 | 追加セキュリティスキャン（`pnpm audit` / `govulncheck` / Trivy / CodeQL）/ カバレッジ閾値 | 価値が出るのは資産が揃ってから（pip-audit は R0 で先行採用） |
| ⏳ 未実装 | 本番運用 | デプロイワークフロー / リリースタグ自動化 | デプロイ先確定後 |

R0 で同時に決めておく構造的事項：

- ワークフローは `.github/workflows/ci.yml` 単一ファイルに集約し、ジョブを目的別（`commitlint` / 言語別 `lint` / `typecheck` / `audit` 等）に分割しておく。後続フェーズの追加はジョブ追加だけで済むようにする
- **全ジョブは `jdx/mise-action` で `mise install` した後、`mise run <task>` で起動する**（→ [ADR 0039](./0039-mise-for-task-runner-and-tool-versions.md)）。ローカルと CI の起動コマンドが同一になり再現性が保証される
- `concurrency: ci-${{ github.ref }}` で同一ブランチの古い実行をキャンセル（分数節約）
- `permissions: contents: read` の最小権限から開始し、必要な権限はジョブ単位で追加
- tool 版数（Python / Node / Go / uv / pnpm）の SSoT は **`mise.toml` 一本に集約**し、`volta` / `packageManager` 等の重複定義は持たない
- 必須化する status checks（branch protection）は `ci-success` umbrella 1 本に集約（→ [ADR 0031](./0031-ci-success-umbrella-job.md)）。新規ジョブ追加は `ci-success.needs` への 1 行追加で済む

## Why（採用理由）

### 段階拡張を選ぶ理由

- **対象が存在しないチェックは設計できない**：テストの並列度・E2E のフレームワーク・Docker のレイヤキャッシュ戦略は、対象実装が存在しないと最適解が決められない。先取りで作ると後で書き直すコストが発生する
- **無料枠の浪費を避ける**：意味のないジョブが回ると、Public/Private を問わず PR 体験が遅くなる（キューイング・ログノイズ）
- **必須化の段階制御**：CI ジョブを必須化（branch protection の required checks）するタイミングを誤ると、不安定なジョブで開発が止まる。実装と並行して安定させてから必須化する

### R0 に最小構成だけ入れる理由

- **commitlint / Biome / typecheck / ruff / pyright は ADR 0021 で R0 採用済み**：ローカル（lefthook）でしか動いていない状態だと、フックを bypass された PR を受け入れてしまう。CI 化して初めて規約遵守が保証される
- **commitlint は遡及修正不可**：R0 で CI 化しないと、規約違反コミットが PR で混入したときに main に入る。後から検出しても直せない（ADR 0021 と同じ非対称性）
- **ruff / pyright も同じ非対称性**：lint 違反 / 型ドリフトが Python ファイル蓄積後に検出されると、整地コストが線形〜超線形に膨張する（[ADR 0021](./0021-r0-tooling-discipline.md) の核論理が Python 側にもそのまま適用される）
- **pip-audit は脆弱性混入の即時検知**：Dependabot は更新 PR を提案するが、混入の瞬間に PR を fail-closed する第二層が無いと、Dependabot 待ち時間中に脆弱性が main に入る（→ [ADR 0035](./0035-uv-for-python-package-management.md) の二重ゲート方針）
- **golangci-lint skeleton は no-op だが構造を先に置く**：Worker 実装が始まる R1〜R2 の時点でジョブ追加コストをゼロにする
- **typecheck (TS) は R0 時点では no-op だが構造を先に置く**：ジョブ枠を作っておけば、最初の TS workspace が追加された時点で自動的に有効化される

### mise 経由でジョブを統一する理由

- **ローカル / CI / 新規参画者の「起動コマンド一致」**：`mise run api-test` が手元・CI・新規 PC で同じ tool 版数 + env で動く（→ [ADR 0039](./0039-mise-for-task-runner-and-tool-versions.md)）
- **CI yaml の見通し改善**：各 job の本体が `mise run <task>` 1 行になり、設定の重複（pnpm install / Python setup / Go setup の各種 setup-action 連鎖）が消える
- **ci-success umbrella との相性**：`needs` リストの拡張がローカルタスク追加と一対一対応する（→ [ADR 0031](./0031-ci-success-umbrella-job.md)）

## Alternatives Considered（検討した代替案）

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| A. 最終形を R0 で全構築 | test / build / e2e / security scan を最初から | 対応する実装が無い段階では設計が空回りし、後で書き直す。YAGNI 違反 |
| B. R0 では CI を作らない | 必要になってから着手 | commitlint の遡及修正不可問題を放置することになる（ADR 0021 と矛盾） |
| C. R0 は段階拡張（採用） | 最小構成だけ作り、フェーズごとに追加 | 「決められるもの」と「決められないもの」を分離できる |

## Consequences（結果・トレードオフ）

### 得られるもの

- R0 から PR レベルで規約違反（コミットメッセージ・lint・型）を弾ける
- 後続フェーズでの CI 拡張がジョブ追加だけで済む（基盤は据え置き）
- 無料枠の消費が小さく、PR 体験が速い（最小構成は 2〜3 分で完了）

### 失うもの・受容するリスク

- フェーズの境界で CI を更新するメンテナンス作業が発生する（ただし要件 .md と連動するので忘れにくい）
- R0 段階では test / build の自動検証がない（ローカル動作と PR レビューに依存）

### 将来の見直しトリガー

- Backend / Frontend / Worker 各実装着手時：`mise run <api/web/worker>-test` ジョブを `ci-success.needs` に追加
- DB スキーマ確定時：`alembic check` で migration drift 検証ジョブを追加
- Docker 化着手時：イメージビルド検証ジョブを追加
- 本番デプロイ準備時：追加セキュリティスキャン（Trivy / CodeQL）・カバレッジ閾値・デプロイワークフローを追加
- いずれかの CI ジョブが安定した時点で：branch protection の required checks に追加（→ [ADR 0031](./0031-ci-success-umbrella-job.md) の `ci-success` umbrella 経由）

## References

- [ADR 0033: バックエンドを Python に pivot](./0033-backend-language-pivot-to-python.md)（R0 範囲拡張の契機）
- [ADR 0021: 補完ツールを R0 から導入](./0021-r0-tooling-discipline.md)（言語横断の R0 機械強制方針）
- [ADR 0018: TypeScript のコード品質ツールに Biome](./0018-biome-for-tooling.md)（Superseded by 0033、Frontend 用途として継続採用）
- [ADR 0019: Go のコード品質ツール](./0019-go-code-quality.md)（Worker R0 skeleton の根拠）
- [ADR 0020: Python のコード品質ツールに ruff + pyright を採用](./0020-python-code-quality.md)（Backend R0 baseline）
- [ADR 0035: Python のパッケージ管理に uv を採用](./0035-uv-for-python-package-management.md)（pip-audit を R0 で組み込む根拠）
- [ADR 0038: テストフレームワーク確定](./0038-test-frameworks.md)（テスト追加時の前提）
- [ADR 0039: タスクランナー兼 tool 版数管理に mise を採用](./0039-mise-for-task-runner-and-tool-versions.md)（CI ジョブを mise run で統一する前提）
- [ADR 0031: ci-success umbrella ジョブ](./0031-ci-success-umbrella-job.md)（必須化の集約点）
- [ADR 0027: GitHub Actions のサードパーティアクション SHA ピン止め](./0027-github-actions-sha-pinning.md)（jdx/mise-action 等の追加分も対象）
- [ADR 0028: Dependabot 自動更新ポリシー](./0028-dependabot-auto-update-policy.md)（pip 対象の追加根拠）
- [ADR 0001: 要件定義書の 5 バケット時系列構造](./0001-requirements-as-5-buckets.md)
- [ADR 0025: CI/CD ツールに GitHub Actions を採用](./0025-github-actions-as-ci-cd.md)
- [.github/workflows/ci.yml](../../.github/workflows/ci.yml)：本 ADR の実装
