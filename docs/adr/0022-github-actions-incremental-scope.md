# 0022. GitHub Actions のスコープを段階的に拡張する

- **Status**: Accepted
- **Date**: 2026-05-05
- **Decision-makers**: 神保 陽平

## Context（背景・課題）

R0（リポジトリ初期セットアップ）時点で GitHub Actions の構成を決める必要がある。
このとき、以下の二つの選択肢がある：

1. **最終形（test / build / e2e / security scan / deploy 等）を最初から構築する**
2. **R0 に必要な最小構成だけ作り、後続フェーズで段階拡張する**

リポジトリ規約 ([CLAUDE.md](../../.claude/CLAUDE.md)) の設計原則は「YAGNI：使うか分からない抽象化を先取りで作らない」「可逆な判断は遅延させる」を掲げている。
CI に組み込むべき項目（テストランナーの並列度、必須化する status checks、マトリクス対象、E2E のフレームワーク等）は **対象となる実装が存在しない時点では合理的に決められない** という性質を持つ。

一方で、[ADR 0018](./0018-phase-0-tooling-discipline.md) で導入済みの commitlint / Biome / 型チェックは、ローカルの lefthook と CI の両方で実行することにより初めて「PR レベルで規約違反を弾く」効果を持つ。これらは R0 時点で既に対象資産（コミット履歴・設定ファイル）が存在するため、CI 化の判断は今下せる。

つまり「R0 で意味があるもの」と「R0 では決められないもの」が混在している。

## Decision（決定内容）

**GitHub Actions は R0 では最小構成（commitlint + Biome + typecheck）のみを実装し、それ以外のチェックは対応する実装フェーズで段階的に追加する。**

R0 に含める（**実装済み**）：

| 状態 | 項目 | 内容 |
|---|---|---|
| ✅ 実装済み | `commitlint` | PR の base..head / push の before..after を範囲検証 |
| ✅ 実装済み | `Biome` | `pnpm lint`（lint + format 検証、書き込みなし） |
| ✅ 実装済み | `typecheck` | `pnpm typecheck`（Turborepo 経由で各 workspace の `tsc --noEmit`、R0 時点では TS workspace 未追加のため no-op） |
| ✅ 実装済み | Composite Action | `.github/actions/setup-node-pnpm` に環境セットアップ（pnpm + Node + install）を集約 |

R0 では決めない（対応フェーズで追加）：

| 状態 | 追加時期 | 項目 | 据え置く理由 |
|---|---|---|---|
| ⏳ 未実装 | R1（API/Web 実装着手後） | `pnpm test`（Vitest 等）/ Drizzle schema 検証 | テストが書かれ始めてから接続する |
| ⏳ 未実装 | R1〜R2 | Go の `gofmt` / `golangci-lint` / `go test` | grading-worker の実装開始後 |
| ⏳ 未実装 | R2 | Docker build 検証（API・Worker のイメージビルド） | Dockerfile 確定後 |
| ⏳ 未実装 | R2〜R3 | E2E（Playwright 等） | Web の主要画面が揃ってから |
| ⏳ 未実装 | R3 | JSON Schema 生成物の drift チェック | `packages/shared-types` の運用開始後 |
| ⏳ 未実装 | R3〜 | Terraform `fmt` / `validate` / `plan` | `infra/` 着手後 |
| ⏳ 未実装 | 本番直前 | セキュリティスキャン（`pnpm audit` / Trivy / CodeQL）/ カバレッジ閾値 | 価値が出るのは資産が揃ってから |
| ⏳ 未実装 | 本番運用 | デプロイワークフロー / リリースタグ自動化 | デプロイ先確定後 |

R0 で同時に決めておく構造的事項：

- ワークフローは `.github/workflows/ci.yml` 単一ファイルに集約し、ジョブを目的別（`commitlint` / `lint` / `typecheck`）に分割しておく。後続フェーズの追加はジョブ追加だけで済むようにする
- `concurrency: ci-${{ github.ref }}` で同一ブランチの古い実行をキャンセル（分数節約）
- `permissions: contents: read` の最小権限から開始し、必要な権限はジョブ単位で追加
- Node / pnpm のバージョンはルートの `volta` / `packageManager` と一致させる
- 必須化する status checks（branch protection）は CI が安定してから設定する（不安定なものを必須にすると開発が止まるため）

## Why（採用理由）

### 段階拡張を選ぶ理由

- **対象が存在しないチェックは設計できない**：テストの並列度・E2E のフレームワーク・Docker のレイヤキャッシュ戦略は、対象実装が存在しないと最適解が決められない。先取りで作ると後で書き直すコストが発生する
- **無料枠の浪費を避ける**：意味のないジョブが回ると、Public/Private を問わず PR 体験が遅くなる（キューイング・ログノイズ）
- **必須化の段階制御**：CI ジョブを必須化（branch protection の required checks）するタイミングを誤ると、不安定なジョブで開発が止まる。実装と並行して安定させてから必須化する

### R0 に最小構成だけ入れる理由

- **commitlint / Biome / typecheck は ADR 0018 で既に Phase 0 採用済み**：ローカル（lefthook）でしか動いていない状態だと、フックを bypass された PR を受け入れてしまう。CI 化して初めて規約遵守が保証される
- **commitlint は遡及修正不可**：R0 で CI 化しないと、規約違反コミットが PR で混入したときに main に入る。後から検出しても直せない（ADR 0018 と同じ非対称性）
- **typecheck は R0 時点では no-op だが構造を先に置く**：ジョブ枠を作っておけば、最初の TS workspace が追加された時点で自動的に有効化される

## Alternatives Considered（検討した代替案）

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| A. 最終形を R0 で全構築 | test / build / e2e / security scan を最初から | 対応する実装が無い段階では設計が空回りし、後で書き直す。YAGNI 違反 |
| B. R0 では CI を作らない | 必要になってから着手 | commitlint の遡及修正不可問題を放置することになる（ADR 0018 と矛盾） |
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

- R1 着手時：`pnpm test` ジョブを追加
- 採点ワーカー実装着手時：Go の lint / test ジョブを追加
- Docker 化着手時：イメージビルド検証ジョブを追加
- 本番デプロイ準備時：セキュリティスキャン・カバレッジ閾値・デプロイワークフローを追加
- いずれかの CI ジョブが安定した時点で：branch protection の required checks に追加

## References

- [ADR 0013](./0013-biome-for-tooling.md)：Biome を採用
- [ADR 0018](./0018-phase-0-tooling-discipline.md)：補完ツールを Phase 0 から導入
- [ADR 0019](./0019-requirements-as-5-buckets.md)：要件定義書のバケット構成（フェーズ R0〜R5）
- [ADR 0023](./0023-github-actions-as-ci-cd.md)：CI/CD ツール選定（GitHub Actions 採用）
- [.github/workflows/ci.yml](../../.github/workflows/ci.yml)：本 ADR の実装
