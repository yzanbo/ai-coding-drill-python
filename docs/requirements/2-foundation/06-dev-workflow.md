# 06. 開発フロー・品質保証

> **このドキュメントの守備範囲**：開発者の生産性と品質保証に関わる技術選定（モノレポ構成・コード品質ツール・共有型生成パイプライン・CI/CD・テストフレームワーク）。**「サービスを動かす実装技術」ではなく「開発体験を支える技術」**を扱う。
> **サービス実装技術（フロントエンド / バックエンド / 採点ワーカー / DB / LLM / サンドボックス / インフラ）**は [05-runtime-stack.md](./05-runtime-stack.md) を参照。
> **コンポーネントの責務・データフロー**は [02-architecture.md](./02-architecture.md) を参照。

---

## リポジトリ・モノレポ構成

3 言語ポリグロット構成（[ADR 0003](../../adr/0003-phased-language-introduction.md)）に対し、各言語の標準ツール 1 本でモノレポ管理する。

- **Frontend（Next.js / TS）**：**`apps/web/` 内に閉じる**（→ [ADR 0036](../../adr/0036-frontend-monorepo-pnpm-only.md) 拡張）。pnpm / Biome / Knip / syncpack / tsconfig は全て `apps/web/` 配下に配置。**Turborepo は不採用**（並列ビルド・依存グラフ・リモートキャッシュ等の価値ドライバが単一 app 構成では効かないため）、**pnpm workspaces は `apps/web/` 内のみ採用**（apps/web 配下の package.json 群を 1 つの workspace として扱う）
- **Backend（Python / FastAPI）**：`apps/api/` 内で **`uv`** を採用（→ [ADR 0035](../../adr/0035-uv-for-python-package-management.md)）。パッケージ管理 / 仮想環境 / Python バージョン / lockfile / workspace を 1 ツールで統合。lockfile が依存整合性を保証するため syncpack 相当の追加ツールは不要
- **Workers（Go）**：`apps/workers/<name>/` 配下で **独立 Go module**（`go mod`、Go 標準）。grading + generation の各 Worker が独立 module（→ [ADR 0040](../../adr/0040-worker-grouping-and-llm-in-worker.md)）
- **root**：orchestration 専用層（`mise.toml` / `lefthook.yml` / `commitlint.config.mjs` のみ）。`packages/` は全て廃止済み（shared-types は不採用、config と prompts は移動 / 廃止、→ [ADR 0006](../../adr/0006-json-schema-as-single-source-of-truth.md) / [ADR 0036](../../adr/0036-frontend-monorepo-pnpm-only.md) / [ADR 0040](../../adr/0040-worker-grouping-and-llm-in-worker.md)）

## タスクランナー兼 tool 版数管理

3 言語横断のタスク実行と tool 版数管理に **`mise`** を採用（→ [ADR 0039](../../adr/0039-mise-for-task-runner-and-tool-versions.md)）。

- **役割 1：タスクランナー**：`mise run <task>` でリポジトリルートから各レイヤのタスク（`api:test` / `web:dev` / `worker:test` / `api:db-migrate` 等の `<scope>:<sub>:<verb>` 階層コロン形式、scope-first）を起動。`cd` 不要
- **役割 2：tool 版数管理**：Python / Node / Go / uv / pnpm 等のバージョンを `mise.toml` 1 ファイルに集約。`pyenv` / `nvm` / `goenv` は採用しない（mise に集約）
- **役割 3：環境変数管理**：`.env` / `[env]` セクションをディレクトリ移動時に自動ロード（`direnv` 相当）
- **設定 SSoT**：`mise.toml`（リポジトリルート）+ 必要に応じて各 app 配下の `.mise.toml`（Monorepo Tasks 機能で `mise run //api:test` 形式の呼び出しが可能）
- **CI 統合**：GitHub Actions の `jdx/mise-action` で `mise install` → `mise run <task>` の流れ。[ADR 0031](../../adr/0031-ci-success-umbrella-job.md) の `ci-success` umbrella ジョブの各 needs を `mise run <task>` で統一呼び出しする
- **Turborepo の orchestration 空席を埋める位置づけ**（→ [ADR 0036](../../adr/0036-frontend-monorepo-pnpm-only.md) と対の判断）

---

## コード品質ツール

3 言語に **「lint + format 1 本 / 型チェック 1 本」の二層構造**を揃える。

### Python（バックエンド本体、→ [ADR 0020](../../adr/0020-python-code-quality.md)）

- **`ruff`**：lint + format 統合（Astral 製、Rust 製で高速）。`flake8` / `black` / `isort` / `pyupgrade` 等を 1 ツールに置換
- **`pyright`**：型チェック（Microsoft 製、VS Code では Pylance として動作、型仕様準拠率 98%）
  - `typeCheckingMode = "basic"` で開始 → 安定後に `"strict"` への段階的引き上げを検討
  - 設定は `pyproject.toml` の `[tool.pyright]` に集約
- **将来の乗り換え候補**：Pyrefly（Meta）/ ty（Astral）。GA + 型仕様準拠率 95% 超で再評価（→ [ADR 0020 §見直しトリガー](../../adr/0020-python-code-quality.md)）
- **`pip-audit`**：依存パッケージの脆弱性スキャン（PyPA 公式、`uv.lock` を入力源、PyPI Advisory + OSV.dev を照会、→ [ADR 0035](../../adr/0035-uv-for-python-package-management.md)）

### TypeScript（フロントエンド、→ [ADR 0018](../../adr/0018-biome-for-tooling.md) — Accepted, Amended by 0033 / 0036、Frontend 用途として継続採用）

- **Biome**：lint + format（Rust 製で高速）。ESLint + Prettier は不採用
- **`tsc --noEmit`**：型チェック（Biome は型チェックを行わないため必須）

### Go（採点ワーカー、→ [ADR 0019](../../adr/0019-go-code-quality.md)）

- **`gofmt`** + **`golangci-lint`**（型チェックは `go build` 内蔵）

### 言語横断の補完ツール（**R0 / リポジトリ初期セットアップ時から導入**、→ [ADR 0021](../../adr/0021-r0-tooling-discipline.md)）

- **共通の根拠**：これらのツールは**途中導入のコストが線形的に膨張**する（蓄積したコードが規約違反だらけになり、後追いで全件修正する作業が発生する）。R0 で入れれば修正対象がほぼゼロ、後期に放置すると数百ファイル規模の整地 PR が必要になりレビュー不能。**初期導入が圧倒的に低コスト**
- **lefthook**：Git フック管理（言語横断）。フック × チェック × CI の対応は [#フック × チェック × CI 対応表](#フック--チェック--ci-対応表) を参照。設定 SSoT は [lefthook.yml](../../../lefthook.yml)
- **commitlint**（Conventional Commits、言語横断）：コミットメッセージ規約の機械的検証。**過去のコミット履歴は遡及修正できない**ため、最初から規約を効かせる必要がある
- **Knip**（TS / Frontend 限定）：未使用 export / 依存 / ファイルの検出。蓄積後の一斉検出は削除可否の個別判断で時間を消費する
- **syncpack**（TS / Frontend 限定、→ [ADR 0024](../../adr/0024-syncpack-package-json-consistency.md) — Accepted, Amended by 0033 / 0036、Frontend 用途として継続採用）：モノレポ内 `package.json` のバージョン整合性を強制。Python 側は uv の単一 lockfile（`uv.lock`）が同等機能を内蔵するため追加ツール不要（→ [ADR 0035](../../adr/0035-uv-for-python-package-management.md)）

### 設定ファイルの物理配置

ADR 0036 拡張により root には orchestration 層のみ（`mise.toml` / `lefthook.yml` / `commitlint.config.mjs`）を置き、各言語固有の設定は対応 app 配下に閉じる：

| 配置先 | 例 |
|---|---|
| **root** | `mise.toml` / `lefthook.yml` / `commitlint.config.mjs` |
| **`apps/web/`** | `package.json` / `tsconfig.json` / `biome.jsonc` / `knip.config.ts` / `.syncpackrc.ts` / `pnpm-lock.yaml` |
| **`apps/api/`** | `pyproject.toml`（`[tool.ruff]` / `[tool.pyright]` / `[tool.deptry]` を集約）/ `uv.lock` |
| **`apps/workers/<name>/`** | `go.mod` / `go.sum` / `.golangci.yml` |

`packages/config/`（multi-consumer 前提の共有 TS 設定パッケージ）は**廃止**（→ [ADR 0036](../../adr/0036-frontend-monorepo-pnpm-only.md)）。

---

## フック × チェック × CI 対応表

各補完ツール（Biome / `tsc --noEmit` / commitlint / syncpack / Knip）が **lefthook のどのフックで動くか** と **CI（GitHub Actions）のどのジョブで動くか** の SSoT。

設定実体：[lefthook.yml](../../../lefthook.yml) / [.github/workflows/ci.yml](../../../.github/workflows/ci.yml) / `apps/web/knip.config.ts` / `apps/web/.syncpackrc.ts` / `apps/web/biome.jsonc` / [commitlint.config.mjs](../../../commitlint.config.mjs)（apps/web/ 配下のツール設定は実装着手時に投入、→ [ADR 0036](../../adr/0036-frontend-monorepo-pnpm-only.md)）。

対象範囲：**Frontend（TS）/ Backend（Python）/ Worker（Go）に対し、それぞれ lint+format / 型チェックを揃える**。Python / Go の lefthook 統合詳細はバックエンド・ワーカー実装着手時に確定。

| チェック | 対象言語 | lefthook フック | glob トリガー | CI ジョブ | 備考 |
|---|---|---|---|---|---|
| **Biome**（lint + format） | TS（Frontend） | pre-commit | `*.{ts,tsx,js,jsx,mjs,cjs,json,jsonc}` | `biome` | pre-commit は `--write` で自動修正 + `stage_fixed: true` で再ステージ。CI は検証のみ |
| **`tsc --noEmit`**（型チェック） | TS（Frontend） | pre-commit | `{*.ts,.*.ts}`（ルート直下のみ） | `typecheck` | ファイル単位起動できないため staged に `.ts` が 1 つでもあれば全体検証 |
| **`ruff check` / `ruff format`** | Python（Backend） | pre-commit（着手時に組込） | `*.py` | `ruff` | format は自動修正、lint は検証のみ。設定 SSoT は `pyproject.toml` の `[tool.ruff]` |
| **`pyright`**（型チェック） | Python（Backend） | pre-commit（着手時に組込） | `*.py` | `pyright` | `typeCheckingMode = "basic"` 開始、設定 SSoT は `pyproject.toml` の `[tool.pyright]` |
| **`gofmt` / `golangci-lint`** | Go（Worker） | pre-commit（実装時に組込） | `*.go` | `golangci-lint` | `go build` 内蔵の型チェックで型ゲートも兼ねる |
| **`pip-audit`**（脆弱性スキャン） | Python（Backend） | （pre-commit には組込まない、CI のみ） | `uv.lock` 変更時 | `pip-audit` | `uv.lock` を入力源、PyPI Advisory + OSV.dev を照会。Dependabot との二重ゲート（→ [ADR 0035](../../adr/0035-uv-for-python-package-management.md)） |
| **commitlint** | 言語横断 | commit-msg | （glob なし、毎回） | `commitlint`（PR は base..head、push は before..after） | 過去履歴は遡及修正不可のため hook と CI の両方で常時起動 |
| **syncpack** | TS（Frontend 限定） | pre-commit | `package.json` | `syncpack` | pre-commit は `lint` のみ。自動修正は `mise run web:syncpack` を手動実行（→ [ADR 0024](../../adr/0024-syncpack-package-json-consistency.md)） |
| **Knip** | TS（Frontend 限定） | pre-commit | `*.{ts,tsx,js,jsx,mjs,cjs,json}` | `knip` | ファイル単位起動できないため glob トリガー時に全プロジェクト解析。自動修正は `mise run web:knip-fix` を手動実行 |

### 多層防御の構造

- **lefthook（pre-commit / commit-msg）**：ローカルでの即時 gate。CI 待ち（30〜60 秒）→ commit 直後（1〜数秒）にフィードバック
- **GitHub Actions CI**：`--no-verify` で lefthook を skip された場合・他マシンから push された場合の最終 gate（[ADR 0031](../../adr/0031-ci-success-umbrella-job.md) の `ci-success` umbrella job が全ジョブの集約点）

### 自動修正の運用方針

- **pre-commit で自動修正するもの**：Biome のフォーマット差分のみ（`stage_fixed: true` で再ステージ）。安全に書き戻せるため
- **pre-commit で自動修正しないもの**：syncpack（他 workspace の `package.json` を書き換えうる）/ Knip（削除可否は人間レビューが必要、未公開機能の足跡 vs dead code の判別）
- **手動実行コマンド**：`mise run web:syncpack` / `mise run web:knip-fix`

採用根拠（なぜこれらのツールを R0 から入れるか）は [ADR 0021](../../adr/0021-r0-tooling-discipline.md) を参照。

---

## 設定ファイル形式の優先順位

ツールの設定ファイルをどの形式（`.ts` / `.jsonc` / `.mjs` / `.yaml` / `.json` 等）で書くかの SSoT。新規ツール導入時 / 既存ツールの形式見直し時に本セクションを参照する。採用根拠は [ADR 0022](../../adr/0022-config-file-format-priority.md) を参照。

### 前提原則：設定ファイルには「なぜ」をインラインコメントで残す

設定ファイルは**規約の SSoT**であり、ルールごとに「なぜこのルールがあるか」をインラインコメントで残すことを基本姿勢とする：

- 「`policy: "sameRange"` を選んだ理由」「`semver` 範囲指定子を `^` 統一する根拠」「特定パッケージを除外する経緯」等を、設定値の隣に書く
- この情報を別ドキュメントに切り出すと SSoT が分裂し、設定変更時にドキュメント側が陳腐化する事故が発生する
- 機械（CI / lint）と人間（レビュアー・LLM）の両方が同じファイルから「設定値」と「設定意図」を読み取れる状態を保つ

この前提から、**コメントを書ける形式を、書けない形式より常に優先する**。純 JSON は他形式が受容される限り採用しない。

### 優先順位

| Tier | 条件 | 形式 |
|---|---|---|
| **1. ツール強制** | 該当ツールが特定形式しか受け付けない | その形式（GitHub Actions / Dependabot → YAML） |
| **2. ecosystem 慣習** | ツールが複数形式を受容しても、公式 / 大多数のユーザが特定形式を使っている | その形式（Biome → `biome.jsonc` / TypeScript → `tsconfig.json` / mise → `mise.toml` / Python ecosystem → `pyproject.toml`） |
| **3-1. 自由選択：TS** | ツールが型を公式 export している（`RcFile` / `UserConfig` / `defineConfig` 等） | `.ts`（typo を保存時に IDE / `tsc` が即時に弾く） |
| **3-2. 自由選択：JSONC** | 設定がほぼ純データ、`$schema` で IDE 補完が効く | `.jsonc`（VS Code が native 認識） |
| **3-3. 自由選択：JS 系** | TS が使えず JSONC も合わない（条件分岐 / 環境変数参照などが必要） | `.mjs` ＞ `.cjs` ＞ `.js`（曖昧さ回避のため明示拡張子を優先） |
| **3-4. 自由選択：YAML** | ツール強制 / 慣習以外で選ぶ理由は無い | `.yaml`（インデント事故 / クォート要否が直感に反するため非推奨） |
| **3-5. 純 JSON** | ツールが純 JSON しか受け付けない | `.json`（コメント不可、最終手段。意図は別途 README / ADR で補完） |

### 拡張子と実態が一致しない例外ファイル

「拡張子は `.json` だが、対応ツールが JSONC として解釈する」ファイルが ecosystem 慣習として存在する。**「`.json` だからコメント書けない」と誤認しない**ようリストで把握する：

| ファイル | 解釈 | 読むツール | 改名可能性 |
|---|---|---|---|
| `tsconfig.json` | **JSONC**（コメント可） | TypeScript コンパイラ | ❌ 不可（tsc の自動探索が固定名を要求） |
| `.vscode/settings.json` | **JSONC**（コメント可） | VSCode | ❌ 不可（VSCode が固定名を要求） |
| `.vscode/launch.json` | **JSONC**（コメント可） | VSCode | ❌ 不可 |
| `.vscode/tasks.json` | **JSONC**（コメント可） | VSCode | ❌ 不可 |
| `package.json` | **strict JSON**（コメント不可） | npm / pnpm / Node.js | ❌ 不可（標準 `JSON.parse()` で解釈） |
| `package-lock.json` | **strict JSON**（コメント不可） | npm | ❌ 不可（自動生成） |

**運用ルール**：

- `tsconfig.json` 等の「JSONC として解釈される `.json` ファイル」を編集する際は、**ファイル冒頭に「このファイルは JSONC として扱われる」旨のコメント**を残し、混乱を防ぐ
- 上記ファイルは ecosystem 慣習でファイル名が固定されており、**改名すると周辺ツールが壊れる**ため `.jsonc` 拡張子に変更しない

### 適用フローチャート

```
新しいツールを導入する／既存ツールの形式を見直す
  │
  ├─ ツールが特定形式を強制？ → その形式を使う（終了）
  │
  ├─ ツール ecosystem 慣習が確立？ → それに従う（終了）
  │
  └─ 自由選択（複数形式を等しく受容）
        │
        ├─ ツールが TS 型を export＆設定値に typo しやすいリテラルあり？ → TS（.ts）
        │
        ├─ 純データ＆JSONC を native 受容＆$schema あり？ → JSONC（.jsonc）
        │
        ├─ ロジック必要 or JSONC 受容なし？ → JS 系（.mjs ＞ .cjs ＞ .js）
        │
        ├─ ツール強制で YAML？ → YAML（.yaml）
        │
        └─ どれも該当しない（純 JSON しか受けない）？ → JSON（妥協、README で意図補完）
```

---

## モノレポ依存整合性（syncpack ルールセット）

> **適用範囲**：Frontend（TS / pnpm workspaces）限定。Python バックエンドは uv の単一 lockfile（`uv.lock`）が同等機能を提供するため syncpack 相当の追加ツールは不要（→ [ADR 0035](../../adr/0035-uv-for-python-package-management.md)）。

モノレポ内 `package.json` の整合性（バージョン揃え / `^` 統一 / `workspace:*` 強制 / dep 重複検知）の機械強制ルールセット。採用根拠は [ADR 0024](../../adr/0024-syncpack-package-json-consistency.md) を参照（Accepted, Amended by 0033 / 0036、Frontend 用途として継続採用）。

**真の SSoT は `apps/web/.syncpackrc.ts`**（apps/web 着手時に投入予定、ADR 0036 拡張で root から移動。`syncpack` の `RcFile` 型を import して型安全を確保、コメントで規約の「なぜ」をインライン化）。本セクションは概観・人間向け解説。

### 機械強制ポリシー（R0 の最小限ルールセット）

| ルール | 内容 |
|---|---|
| 内部 workspace パッケージは `workspace:*` 固定 | `@ai-coding-drill/**` への参照は `pinVersion: "workspace:*"` |
| 外部依存は全 workspace で同一バージョン | `policy: "sameRange"` |
| semver 範囲指定子は `^` に統一 | `range: "^"`（`workspace:*` は対象外で自動除外） |
| `dependencies` / `devDependencies` の重複検知 | syncpack デフォルト挙動 |
| `package.json` キー順整形 | syncpack デフォルト挙動（`syncpack format`） |

### 運用

- **lefthook pre-commit / CI**：[#フック × チェック × CI 対応表](#フック--チェック--ci-対応表) を参照
- **自動修正**：pre-commit / CI には接続せず、`mise run web:syncpack`（mismatches 修正）/ `mise run web:syncpack-format`（キー順）を開発者が手動実行する半自動運用
- **設定ファイル形式**：`.ts`（→ [#設定ファイル形式の優先順位](#設定ファイル形式の優先順位) の Tier 3-1：型 export ありで typo を保存時に弾ける）
- **設定の物理配置**：`apps/web/.syncpackrc.ts`（apps/web 内の multi-package 対象、ADR 0036 拡張で root から移動）

### ルールを追加・変更する時

新しいルールを `.syncpackrc.ts` に足す場合：

1. `.syncpackrc.ts` を更新（**設定値の隣に「なぜ」のインラインコメントを残す** → [#設定ファイル形式の優先順位](#設定ファイル形式の優先順位) の前提原則）
2. 上記「機械強制ポリシー」表に行を追加
3. ルール変更が ADR レベルの判断（例：`^` 統一を `~` に変える）なら、新規 ADR か [ADR 0024](../../adr/0024-syncpack-package-json-consistency.md) の本文書き換えを検討

---

## コミットメッセージ規約

コミットメッセージは **Conventional Commits** に従い、commitlint で機械強制する。採用根拠と scope の付与方針は [ADR 0029](../../adr/0029-commit-scope-convention.md) を参照。

**真の SSoT は [`commitlint.config.mjs`](../../../commitlint.config.mjs) の `type-enum` / `scope-enum`**（CI と lefthook commit-msg フックで違反を弾く）。本セクションは人間向け解説。なお commitlint が比較する base コミットの取得方式（shallow clone 環境で `--shallow-exclude` が使えない件への対処として `--deepen=20` の iterative deepen 方式）は [ADR 0030](../../adr/0030-commitlint-base-commit-fetch.md) を参照。

### 形式

```
<type>(<scope>): <subject>
```

- 言語：日本語で記載（subject は英語でも可、一貫していれば良い）
- ヘッダー全体：100 文字以内
- 本文：1 行 200 文字以内
- 複数領域に跨る変更：scope をカンマ区切り（例：`feat(api,worker): ...`）。ブランチ名には詰めず commit 側で表現する

### type（Conventional Commits 標準、下記から 1 つ選ぶ）

`feat` / `fix` / `docs` / `refactor` / `test` / `chore` / `ci` / `build` / `perf` / `style` / `revert`

### 領域 scope（人間が手動コミット時に選ぶ、8 種）

| scope | 対応領域 |
|---|---|
| `web` | `apps/web`（フロントエンド / Next.js） |
| `api` | `apps/api`（FastAPI / Python バックエンド） |
| `worker` | `apps/workers/*`（grading / generation 等の Go Worker 群、→ [ADR 0040](../../adr/0040-worker-grouping-and-llm-in-worker.md)） |
| `shared` | OpenAPI / JSON Schema artifact など複数 app から参照される共有 artifact（`apps/api/openapi.json` / `apps/api/job-schemas/` 等）。`packages/shared-types` は ADR 0006、`packages/config` は ADR 0036、`packages/prompts` は ADR 0040 で全廃済み |
| `config` | root 直接配置の tooling 設定ファイル群（`mise.toml` / `lefthook.yml` / `commitlint.config.mjs` 等。`packages/config/` は廃止、→ [ADR 0036](../../adr/0036-frontend-monorepo-pnpm-only.md)） |
| `infra` | `infra/`（Terraform） |
| `docs` | `docs/`（要件定義 / ADR） |
| `db` | DB スキーマ・マイグレーション（SQLAlchemy 2.0 モデル + Alembic マイグレーション、→ [ADR 0037](../../adr/0037-sqlalchemy-alembic-for-database.md)） |

### 自動更新 scope（Dependabot が自動付与、2 種）

| scope | 用途 | 付与経路 |
|---|---|---|
| `deps` | production 依存 / github-actions / grouped PR | Dependabot の `include: scope`（人間が手で書くこともあり、その場合は production 依存更新） |
| `deps-dev` | devDependencies 単発更新 | Dependabot の `prefix-development` + `include: scope` |

### scope の `scope-empty` 許容

`scope-empty` は許容する（リポジトリ横断の変更で scope 不要なケースのため）。リポジトリ全体に跨る変更（例：ルート tsconfig 全体改訂）は scope を省略可。

### scope を追加・変更する時

1. `commitlint.config.mjs` の `scope-enum` を更新（**SSoT、ここを更新しないと CI で弾かれない**）
2. 上記「領域 scope」表に行を追加
3. CLAUDE.md / CONTRIBUTING.md 等の補助ドキュメントは本セクションへのリンクで足りるため、原則更新不要（リンクが正しく追従していれば自動同期する）

---

## 共有型・スキーマ（Pydantic を SSoT、境界別の 2 伝送路で各言語へ展開）

Backend の Pydantic モデル（`apps/api/app/schemas/`）を Single Source of Truth とし、**境界が 2 つあるから伝送路も 2 つ**用意する（→ [ADR 0006](../../adr/0006-json-schema-as-single-source-of-truth.md)）：

- **HTTP API 境界（API ⇄ Web）**：FastAPI 自動 OpenAPI 3.1（`apps/api/openapi.json`）→ Hey API で TS 型 + Zod + HTTP クライアント生成
- **Job キュー境界（API → DB → Worker）**：Pydantic `model.model_json_schema()` で個別 JSON Schema を `apps/api/job-schemas/` 配下に出力 → quicktype `--src-lang schema` で Go struct 生成

| 境界 | 入力源 | 生成ツール | 出力 | コミット |
|---|---|---|---|---|
| Python（Backend、SSoT 自身） | — | — | Pydantic v2 モデル | ソースとしてコミット |
| HTTP API（Frontend 向け） | `apps/api/openapi.json`（OpenAPI 3.1 全要素） | **Hey API**（`@hey-api/openapi-ts` + Zod プラグイン） | TS 型 + Zod + 型付き HTTP クライアント | 生成物コミット |
| Job キュー（Worker 向け） | `apps/api/job-schemas/<job-name>.schema.json`（個別 JSON Schema） | **quicktype `--src-lang schema`** | Go struct + JSON タグ | gitignore（`go generate` で生成） |

生成パイプラインは mise タスクで集約（タスク命名は `<scope>:<sub>:<verb>` 階層コロン形式）：

- `mise run api:openapi-export`：FastAPI から OpenAPI 3.1 を `apps/api/openapi.json` に書き出し
- `mise run api:job-schemas-export`：Pydantic Job payload から個別 JSON Schema を `apps/api/job-schemas/` に書き出し
- `mise run web:types-gen`：Hey API で OpenAPI から TS / Zod / HTTP クライアント生成
- `mise run worker:types-gen`：quicktype で `apps/api/job-schemas/` から Go struct 生成（横断、対象 Worker 全てに配布）

配置・生成ツール候補・コミット方針・選定理由・代替検討の詳細 SSoT は [ADR 0006](../../adr/0006-json-schema-as-single-source-of-truth.md) を参照。

### drift 検出（lefthook + CI 二軸）

「Pydantic schema を変更したのに `apps/api/openapi.json` / `apps/api/job-schemas/` / `apps/web/src/__generated__/api/` の再エクスポートを忘れた PR」を構造的に防ぐため、**ローカル早期検出（lefthook）と最終ゲート（CI）の二軸**で守る。両者の役割は補完関係であり、片方だけでは不足する：

| 軸 | 走る場所 | 役割 | 強制力 | 速度 |
|---|---|---|---|---|
| **lefthook** | 開発者ローカル（pre-commit / pre-push） | 早期 feedback、CI 待ち時間ゼロ | `--no-verify` で迂回可能 | 数秒（差分ファイル limited） |
| **GitHub Actions CI** | PR / push | 迂回不可の最終ゲート、Required status checks に組込 | 強制（Ruleset で保護） | 数十秒〜分 |

#### 起動条件と動作

- **lefthook**：`apps/api/app/schemas/` 配下の `.py` がステージング差分に含まれるときだけ `mise run api:openapi-export && mise run api:job-schemas-export` を実行し、出力 artifact が未ステージなら abort（`git diff --exit-code` 相当）。glob フィルタで「無関係な commit に余計なコストを乗せない」設計
- **CI**：PR / main push で `mise run api:openapi-export && mise run api:job-schemas-export && mise run web:types-gen && git diff --exit-code apps/api/openapi.json apps/api/job-schemas/ apps/web/src/__generated__/api/` を実行。`worker:types-gen` の出力は gitignore（→ ADR 0006）のため drift 検出対象外（CI 内で都度生成して使う）

#### 配線タイミング

- 本仕組みは **`apps/api/` 実装着手時**に lefthook（→ [#フック × チェック × CI 対応表](#フック--チェック--ci-対応表)）と CI workflow（→ [#ci-集約ジョブ-ci-success-umbrellaパターン](#ci-集約ジョブci-success-umbrellaパターン)）に同時配線する。実装前は `apps/api/openapi.json` 自体が存在せず空回りするため、配線を前倒ししない（→ [ADR 0026](../../adr/0026-github-actions-incremental-scope.md) 段階拡張原則と整合）
- 採用根拠の SSoT は [ADR 0006](../../adr/0006-json-schema-as-single-source-of-truth.md) を参照

---

## CI/CD

- **GitHub Actions**
- pre-commit（lefthook 経由で Biome / typecheck / syncpack / Knip。詳細は [#フック × チェック × CI 対応表](#フック--チェック--ci-対応表)）
- Dependabot
- PR 時：commitlint / Biome / typecheck / syncpack / Knip（pre-commit を skip された場合の最終 gate、詳細は [#フック × チェック × CI 対応表](#フック--チェック--ci-対応表)）
- main マージ時：Docker build → ECR push → デプロイ
- Terraform plan/apply もワークフロー化

---

## CI 集約ジョブ（ci-success umbrella）パターン

GitHub ブランチ保護（Ruleset）の Required status checks には集約ジョブ `ci-success` 1 つだけを登録し、新規 CI ジョブは `ci-success.needs` に追加するだけで Required の網に組み込む。採用根拠は [ADR 0031](../../adr/0031-ci-success-umbrella-job.md) を参照。

**真の SSoT は [`.github/workflows/ci.yml`](../../../.github/workflows/ci.yml) の `ci-success` ジョブ + GitHub Ruleset `protect-main`**。本セクションはパターンの設計と運用ルール。

### ci-success ジョブの構造

```yaml
ci-success:
  name: ci-success
  if: always()
  needs: [commitlint, lint, typecheck, syncpack, knip]
  runs-on: ubuntu-latest
  steps:
    - run: |
        if [[ "${{ contains(needs.*.result, 'failure') }}" == "true" ]] \
           || [[ "${{ contains(needs.*.result, 'cancelled') }}" == "true" ]] \
           || [[ "${{ contains(needs.*.result, 'skipped') }}" == "true" ]]; then
          echo "::error::One or more required jobs did not succeed"
          exit 1
        fi
```

要点：

- `if: always()`：いずれかの needs が失敗した瞬間に集約ジョブが「skipped」になる事故を回避
- `needs.*.result` を `success` 以外で fail：`failure` / `cancelled` / `skipped` を全て失敗扱いにする
- `name: ci-success`：Ruleset の status check 名と一致させる（リネームしない）

### protect-main Ruleset の構造（main のみ強制）

```
target: ~DEFAULT_BRANCH（main のみ）
enforcement: active
bypass_actors: なし
rules:
  - deletion              ：ブランチ削除禁止
  - non_fast_forward      ：force-push 禁止
  - pull_request          ：PR 経由必須（approvals: 0、stale dismiss: on）
  - required_status_checks：ci-success 緑必須
      strict_required_status_checks_policy: false
      required_status_checks: [{ context: "ci-success" }]
```

### CI ジョブを追加する時

1. `ci.yml` に新ジョブを追加
2. `ci-success.needs` に追加したジョブ名を 1 行追加
3. Ruleset 側は変更不要（status check 名は `ci-success` のまま不変）

これにより、新規 CI ジョブの追加と Required status checks の網の追従が**機械的に同期**する。Ruleset を毎回 GitHub UI で編集する手間が消える。

### ルールセットを別ファイルに分離しない方針

`protect-main`（main 固有縛り）と `require-ci-pass`（全ブランチ CI 強制）の 2 ルールセットに分離する案は採らない。target がいずれも `~DEFAULT_BRANCH` に収束するため、分離の根拠が消失する。1 つのルールセットに集約し、main 保護に関する全ルールが 1 箇所で読めるようにする。

---

## テスト

レイヤごとに各エコシステムのデファクトを採用（→ [ADR 0038](../../adr/0038-test-frameworks.md)）。

- **Backend（Python / FastAPI）**：`pytest` + `pytest-asyncio` + `httpx.AsyncClient` + `pytest-cov`。FastAPI の `app.dependency_overrides` で DB / 外部 API をモック差し替え
- **Frontend（TS / Next.js）**：`Vitest`（ユニット）+ `@testing-library/react`（コンポーネント）+ `Playwright`（E2E、クロスブラウザ）+ `@vitest/coverage-v8`
- **Worker（Go）**：Go 標準 `testing` + `testify` + `go test -cover`（`-race` で goroutine レース検出）
- **ミューテーションテスト**：MVP では採用しない。R2 以降に必要性を再判断（Python なら `mutmut`、TS なら `stryker-js` 等が候補）
- テストカバレッジ：Codecov に各言語のレポートを集約

---

## 関連

- [05-runtime-stack.md](./05-runtime-stack.md) — サービスを動かす実装技術スタック
- [02-architecture.md](./02-architecture.md) — コンポーネントの責務・データフロー
- [ADR 0033: バックエンドを Python に pivot](../../adr/0033-backend-language-pivot-to-python.md)
- [ADR 0034: バックエンド API に FastAPI を採用](../../adr/0034-fastapi-for-backend.md)
- [ADR 0035: Python のパッケージ管理・モノレポ管理に uv を採用](../../adr/0035-uv-for-python-package-management.md)
- [ADR 0036: Frontend モノレポ管理を pnpm workspaces のみに縮小（Turborepo 不採用）](../../adr/0036-frontend-monorepo-pnpm-only.md)
- [ADR 0039: タスクランナー兼 tool 版数管理に mise を採用](../../adr/0039-mise-for-task-runner-and-tool-versions.md)
- [ADR 0037: DB ORM・マイグレーションに SQLAlchemy 2.0 + Alembic を採用](../../adr/0037-sqlalchemy-alembic-for-database.md)
- [ADR 0038: テストフレームワーク確定（pytest / Vitest / Playwright / Go testing）](../../adr/0038-test-frameworks.md)
- [ADR 0020: Python のコード品質ツールに ruff + pyright を採用](../../adr/0020-python-code-quality.md)
- [ADR 0019: Go のコード品質ツール（gofmt + golangci-lint）](../../adr/0019-go-code-quality.md)
- [ADR 0018: TypeScript のコード品質ツールに Biome](../../adr/0018-biome-for-tooling.md)（Accepted, Amended by 0033 / 0036、Frontend 用途として継続採用）
- [ADR 0023: Turborepo + pnpm workspaces](../../adr/0023-turborepo-pnpm-monorepo.md)（Superseded by 0033 / 0036、Turborepo / pnpm workspaces とも不採用。Python 側パッケージ管理は ADR 0035、Frontend は単一 `apps/web/` で pnpm 単独運用、タスクランナーは ADR 0039）
- [ADR 0024: syncpack による package.json 整合性](../../adr/0024-syncpack-package-json-consistency.md)（Accepted, Amended by 0033 / 0036、Frontend 用途として継続採用）
- [ADR 0006: JSON Schema を SSoT に](../../adr/0006-json-schema-as-single-source-of-truth.md)
- [ADR 0021: 補完ツールを R0 から導入](../../adr/0021-r0-tooling-discipline.md)
