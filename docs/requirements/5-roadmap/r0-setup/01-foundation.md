# 01. 初期慣行の構築（全 ✅ 完了済）

> **守備範囲**：言語非依存の最低限の開発慣行を全 ✅ 完了済として記録する。本フェーズが終わると、commit 規約・フック・mise 経由のツール起動・CI 雛形・Dependabot 雛形が揃う。
> **進行状態**：全項目達成済（git log と既存ファイルが正本）。
> **次フェーズ**：[02-backend.md](./02-backend.md)
>
> **本ファイル共通の最新版調査ポリシー**：
> [.claude/CLAUDE.md: バージョン方針](../../../../.claude/CLAUDE.md#バージョン方針) に従い、各ステップで **(1) 対象ツールの最新安定版を毎回 Web で調査** し、**(2) 採用前に依存関係（peer dep / 必須最小版数 / breaking changes）をリリースノートで確認** してから書き換える。SSoT（`mise.toml` / `pyproject.toml` / `package.json` / `docker-compose.yml` 等）に書かれた既存版数には追従しない（陳腐化のため）。RC / beta / nightly は採用しない。本フェーズの対象は `commitlint` / `lefthook` / `mise` / `uv` / `pnpm` / `npm:@commitlint/cli` および GitHub Actions のサードパーティ Action（SHA pin 形式で版数明示）。
>
> **本フェーズ共通の設計原則**：hook 役割分担（pre-commit / pre-push / CI）は [README.md](./README.md) を参照。本フェーズで導入する lefthook / GitHub Actions の役割設計が、以降の役割別フェーズの「環境構築 + 品質ゲート 5 ステップ」パターンの土台となる。

---

## 1. commitlint 導入 + scope/type 規約整備 ✅

**目的**：コミット履歴を機械強制で清浄に保つ（履歴は遡及修正不可なため、最初に固める）。

**成果物**：
- [commitlint.config.mjs](../../../../commitlint.config.mjs) — type / scope 列挙の SSoT
- [docs/requirements/2-foundation/06-dev-workflow.md: コミットメッセージ規約](../../2-foundation/06-dev-workflow.md#コミットメッセージ規約)

**完了基準**：規約外のコミットメッセージを `commitlint --edit <file>` が拒否する。

**根拠**：[ADR 0029](../../../adr/0029-commit-scope-convention.md) / [ADR 0030](../../../adr/0030-commitlint-base-commit-fetch.md)

---

## 2. lefthook + commit-msg フック ✅

**目的**：commitlint をローカル commit 時に自動実行し、規約逸脱を hook で弾く。

**成果物**：
- [lefthook.yml](../../../../lefthook.yml) — `commit-msg` フックで `mise exec -- commitlint --edit {1}` を起動

**完了基準**：規約外メッセージで commit すると `lefthook` が exit 1 を返してコミットがブロックされる。

**根拠**：[ADR 0021](../../../adr/0021-r0-tooling-discipline.md)

---

## 3. mise 導入 ✅

**目的**：3 言語ランタイム + 全ツールの版数を 1 ファイルで固定し、`mise install` 一発で全環境を再現可能にする。タスク命名規約も同時確立する。

**成果物**：
- [mise.toml](../../../../mise.toml) — `[tools]` で版数固定、`[tasks.*]` でタスク命名規則を確立

**確定済の固定版数**：具体版数の SSoT は [mise.toml](../../../../mise.toml)（Python / Node.js / Go、更新時はそこ 1 箇所を変える）。
- uv（latest）
- pnpm（latest）
- lefthook（latest）
- `npm:@commitlint/cli`（latest）

**確定済のタスク命名規約**：`<scope>:<sub>:<verb>` 階層コロン形式（例：`api:db-migrate`、`worker:grading:dev`、`web:types-gen`）

**確定済の横断タスク雛形**：`lint` / `test` / `typecheck` / `types-gen`（実体は後続フェーズで埋める）

**完了基準**：`mise install` で全ランタイム + 全ツールが取得され、`mise tasks` でタスク一覧が表示される。

**根拠**：[ADR 0039](../../../adr/0039-mise-for-task-runner-and-tool-versions.md)

---

## 4. GitHub Actions ワークフロー雛形 ✅

**目的**：言語非依存の CI 基盤を先に整備する。各言語ジョブは Python / Frontend 縦スライスで段階的に追加する（`ci-success` の `needs:` を増やす）。

**成果物**：
- [.github/workflows/ci.yml](../../../../.github/workflows/ci.yml)
  - `commitlint` ジョブ（PR / push 両モードで base コミット取得 + 検証）
  - `ci-success` umbrella ジョブ（必須チェックを 1 本化、`needs:` で各言語ジョブを束ねる）
- サードパーティ Action の SHA ピン止め規約（`@<40 文字 SHA> # vX.Y.Z` の形式）

**完了基準**：PR を作ると `commitlint` ジョブが走り、規約逸脱を弾く。Branch protection rule の Required check は `ci-success` 1 本だけに設定する。

**根拠**：[ADR 0025](../../../adr/0025-github-actions-as-ci-cd.md) / [ADR 0026](../../../adr/0026-github-actions-incremental-scope.md) / [ADR 0027](../../../adr/0027-github-actions-sha-pinning.md) / [ADR 0031](../../../adr/0031-ci-success-umbrella-job.md)

---

## 5. Dependabot 雛形 ✅

**目的**：Dependabot を有効化し、各言語着手時にコメントアウト解除するだけで監視対象が拡張される設計にする。SHA ピン止め（本ファイル「4. GitHub Actions ワークフロー雛形」）と組み合わせることで、メンテナが手で 40 文字 SHA を追従する負担を排除する。

**成果物**：
- [.github/dependabot.yml](../../../../.github/dependabot.yml)
  - `github-actions`：有効化済
  - `pip`：コメントアウトで待機（[02-backend.md: 8. dependabot.yml の `pip` コメントアウト解除](./02-backend.md#8-dependabotyml-の-pip-コメントアウト解除) で解除）
  - `npm`：コメントアウトで待機（[03-frontend.md: 7. dependabot.yml の `npm` コメントアウト解除](./03-frontend.md#7-dependabotyml-の-npm-コメントアウト解除) で解除）
  - `gomod`：コメントアウトで待機（[04-worker.md: 8. dependabot.yml の `gomod` コメントアウト解除](./04-worker.md#8-dependabotyml-の-gomod-コメントアウト解除) で解除）

**完了基準**：`.github/dependabot.yml` が存在し、`github-actions` の週次自動 PR が生成される設定が有効になっている。

**根拠**：[ADR 0028](../../../adr/0028-dependabot-auto-update-policy.md)

---

## 6. 進捗トラッカーへの反映の最終状態

**目的**：本フェーズが終わったことを、プロジェクトの進捗管理仕組み（ロードマップ / プロジェクト管理ツール / README 等）に反映する。

**最終状態**：

- **プロジェクトの進捗トラッカー**（このプロジェクトでは [docs/requirements/5-roadmap/01-roadmap.md](../01-roadmap.md)。別プロジェクトでは GitHub Project / Notion / README 等、各プロジェクトの慣習に従う）で、本フェーズに該当する項目が**完了状態**として記録されている
- 進捗トラッカー上の該当エントリから、**本ファイル**（または同等の手順詳細）への**リンク**が辿れる
- 本ファイル冒頭のステータスマーク（`# 01. 初期慣行の構築（全 ✅ 完了済）` の `✅`）が完了状態を示している

> **このプロジェクトでの具体例**：[01-roadmap.md](../01-roadmap.md) の R0-1 行が、状態列 `✅ 完了` + 詳細手順列が本ファイルへのリンク `[r0-setup/01-foundation.md](./r0-setup/01-foundation.md)` になっている状態。古い表現（`🔴 未着手` / 未着手プレースホルダ / 旧リンク等）が残っていれば最終状態に合わせる。

**完了基準**：

- 進捗トラッカー上で本フェーズが完了になっている
- 本ファイルへのリンクが進捗トラッカーから辿れる
- 本ファイル冒頭のステータスマークが完了状態（`✅`）になっている

---

## このフェーズ完了時点で揃うもの

- ✅ コミット履歴の機械強制（規約外コミット不可）
- ✅ ローカル commit 時の hook ゲート
- ✅ 3 言語ランタイム（Python / Node / Go）+ 全ツールの版数固定 + `mise install` 一発再現
- ✅ タスク命名規約の確立
- ✅ CI 雛形（commitlint + ci-success umbrella + SHA ピン規約）
- ✅ Dependabot 雛形（github-actions のみ有効、各言語は待機）

次は [02-backend.md](./02-backend.md) で apps/api 環境を構築する。
