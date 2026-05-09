# 06. 開発フロー・品質保証

> **このドキュメントの守備範囲**：開発者の生産性と品質保証に関わる技術選定（モノレポ構成・コード品質ツール・共有型生成パイプライン・CI/CD・テストフレームワーク）。**「サービスを動かす実装技術」ではなく「開発体験を支える技術」**を扱う。
> **サービス実装技術（フロントエンド / バックエンド / 採点ワーカー / DB / LLM / サンドボックス / インフラ）**は [05-runtime-stack.md](./05-runtime-stack.md) を参照。
> **コンポーネントの責務・データフロー**は [02-architecture.md](./02-architecture.md) を参照。

---

## リポジトリ・モノレポ構成

- **Turborepo + pnpm workspaces** を採用（→ [ADR 0023](../../adr/0023-turborepo-pnpm-monorepo.md)）
  - pnpm workspaces：JS/TS パッケージの依存解決・リンク（土台）
  - Turborepo：ビルド順序・並列実行・キャッシュ・Vercel リモートキャッシュ（上層）
  - Go は `go mod`、Python（R7）は `uv` を使い、Turborepo は `package.json` script から薄く統合
- ディレクトリ構成の最終版は [ADR 0023](../../adr/0023-turborepo-pnpm-monorepo.md) を参照

---

## コード品質ツール

- **Biome**（lint + format、Rust 製で高速）を TS で書かれた全アプリ・全パッケージで統一使用（→ [ADR 0018](../../adr/0018-biome-for-tooling.md)）
  - ESLint + Prettier の組み合わせは不採用
- **TypeScript（`tsc --noEmit`）** で型チェック（Biome は型チェックを行わないため必須）
- 補完ツール（**R0 / リポジトリ初期セットアップ時から導入**、→ [ADR 0021](../../adr/0021-r0-tooling-discipline.md)）：
  - **共通の根拠**：これらのツールは**途中導入のコストが線形的に膨張**する（蓄積したコードが規約違反だらけになり、後追いで全件修正する作業が発生する）。R0 で入れれば修正対象がほぼゼロ、R4 まで放置すると数百ファイル規模の整地 PR が必要になりレビュー不能。**初期導入が圧倒的に低コスト**
  - **lefthook**：Git フック管理。フック × チェック × CI の対応は [#フック × チェック × CI 対応表](#フック--チェック--ci-対応表) を参照。設定 SSoT は [lefthook.yml](../../../lefthook.yml)
  - **commitlint**（Conventional Commits）：コミットメッセージ規約の機械的検証。**過去のコミット履歴は遡及修正できない**ため、最初から規約を効かせる必要がある
  - **Knip**：未使用 export / 依存 / ファイルの検出。蓄積後の一斉検出は削除可否の個別判断で時間を消費する
  - **syncpack**：モノレポ内 `package.json` のバージョン整合性を強制（→ [ADR 0024](../../adr/0024-syncpack-package-json-consistency.md)）。Turborepo + pnpm workspaces 構成で必須レベル。**バージョンずれは積もると一括修正に動作リスクが伴う**
- **Go**：`gofmt` + `golangci-lint`（→ [ADR 0019](../../adr/0019-go-code-quality.md)）
- **Python（R7）**：`ruff`（Linter + Formatter 統合）。型チェッカーは R7 着手時に決定（→ [ADR 0020](../../adr/0020-python-code-quality.md)）
- **設定ファイルの物理配置**：Layer 1（ルート直接配置）/ Layer 2（`packages/config/` 経由）の住人・判断基準・投入タイミングは [packages/config/README.md](../../../packages/config/README.md) に集約

---

## フック × チェック × CI 対応表

各補完ツール（Biome / `tsc --noEmit` / commitlint / syncpack / Knip）が **lefthook のどのフックで動くか** と **CI（GitHub Actions）のどのジョブで動くか** の SSoT。

設定実体：[lefthook.yml](../../../lefthook.yml) / [.github/workflows/ci.yml](../../../.github/workflows/ci.yml) / [knip.config.ts](../../../knip.config.ts) / [.syncpackrc.ts](../../../.syncpackrc.ts) / [biome.jsonc](../../../biome.jsonc) / [commitlint.config.ts](../../../commitlint.config.ts)。

| チェック | lefthook フック | glob トリガー | CI ジョブ | 備考 |
|---|---|---|---|---|
| **Biome**（lint + format） | pre-commit | `*.{ts,tsx,js,jsx,mjs,cjs,json,jsonc}` | `Biome` | pre-commit は `--write` で自動修正 + `stage_fixed: true` で再ステージ。CI は検証のみ |
| **`tsc --noEmit`**（型チェック） | pre-commit | `{*.ts,.*.ts}`（ルート直下のみ） | `typecheck`（root configs + workspaces 経由 Turborepo） | ファイル単位起動できないため staged に `.ts` が 1 つでもあれば全体検証 |
| **commitlint** | commit-msg | （glob なし、毎回） | `commitlint`（PR は base..head、push は before..after） | 過去履歴は遡及修正不可のため hook と CI の両方で常時起動 |
| **syncpack** | pre-commit | `package.json` | `syncpack` | pre-commit は `lint` のみ。自動修正は `pnpm syncpack:fix` を手動実行（→ [ADR 0024](../../adr/0024-syncpack-package-json-consistency.md)） |
| **Knip** | pre-commit | `*.{ts,tsx,js,jsx,mjs,cjs,json}` | `knip` | ファイル単位起動できないため glob トリガー時に全プロジェクト解析。自動修正は `pnpm knip:fix` を手動実行 |

### 多層防御の構造

- **lefthook（pre-commit / commit-msg）**：ローカルでの即時 gate。CI 待ち（30〜60 秒）→ commit 直後（1〜数秒）にフィードバック
- **GitHub Actions CI**：`--no-verify` で lefthook を skip された場合・他マシンから push された場合の最終 gate（[ADR 0031](../../adr/0031-ci-success-umbrella-job.md) の `ci-success` umbrella job が全ジョブの集約点）

### 自動修正の運用方針

- **pre-commit で自動修正するもの**：Biome のフォーマット差分のみ（`stage_fixed: true` で再ステージ）。安全に書き戻せるため
- **pre-commit で自動修正しないもの**：syncpack（他 workspace の `package.json` を書き換えうる）/ Knip（削除可否は人間レビューが必要、未公開機能の足跡 vs dead code の判別）
- **手動実行コマンド**：`pnpm syncpack:fix` / `pnpm knip:fix`

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
| **1. ツール強制** | 該当ツールが特定形式しか受け付けない | その形式（GitHub Actions / Dependabot / pnpm workspace → YAML） |
| **2. ecosystem 慣習** | ツールが複数形式を受容しても、公式 / 大多数のユーザが特定形式を使っている | その形式（Biome → `biome.jsonc` / Turborepo → `turbo.jsonc` / TypeScript → `tsconfig.json`） |
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

モノレポ内 `package.json` の整合性（バージョン揃え / `^` 統一 / `workspace:*` 強制 / dep 重複検知）の機械強制ルールセット。採用根拠は [ADR 0024](../../adr/0024-syncpack-package-json-consistency.md) を参照。

**真の SSoT は [`.syncpackrc.ts`](../../../.syncpackrc.ts)**（`syncpack` の `RcFile` 型を import して型安全を確保、コメントで規約の「なぜ」をインライン化）。本セクションは概観・人間向け解説。

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
- **自動修正**：pre-commit / CI には接続せず、`pnpm syncpack:fix`（mismatches 修正）/ `pnpm syncpack:format`（キー順）を開発者が手動実行する半自動運用
- **設定ファイル形式**：`.ts`（→ [#設定ファイル形式の優先順位](#設定ファイル形式の優先順位) の Tier 3-1：型 export ありで typo を保存時に弾ける）
- **設定の物理配置**：ルート直接配置（横断ツールのため Layer 1。配置方針は [packages/config/README.md](../../../packages/config/README.md)）

### ルールを追加・変更する時

新しいルールを `.syncpackrc.ts` に足す場合：

1. `.syncpackrc.ts` を更新（**設定値の隣に「なぜ」のインラインコメントを残す** → [#設定ファイル形式の優先順位](#設定ファイル形式の優先順位) の前提原則）
2. 上記「機械強制ポリシー」表に行を追加
3. ルール変更が ADR レベルの判断（例：`^` 統一を `~` に変える）なら、新規 ADR か [ADR 0024](../../adr/0024-syncpack-package-json-consistency.md) の本文書き換えを検討

---

## コミットメッセージ規約

コミットメッセージは **Conventional Commits** に従い、commitlint で機械強制する。採用根拠と scope の付与方針は [ADR 0029](../../adr/0029-commit-scope-convention.md) を参照。

**真の SSoT は [`commitlint.config.ts`](../../../commitlint.config.ts) の `type-enum` / `scope-enum`**（CI と lefthook commit-msg フックで違反を弾く）。本セクションは人間向け解説。

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
| `api` | `apps/api`（NestJS API） |
| `worker` | `apps/grading-worker`（Go 採点ワーカー） |
| `shared` | `packages/shared-types`、`packages/prompts` 等の共有パッケージ |
| `config` | tooling 設定ファイル群（ルート直接配置 + `packages/config/` の両方を含む、→ [packages/config/README.md](../../../packages/config/README.md)） |
| `infra` | `infra/`（Terraform） |
| `docs` | `docs/`（要件定義 / ADR） |
| `db` | Drizzle スキーマ・マイグレーション |

### 自動更新 scope（Dependabot が自動付与、2 種）

| scope | 用途 | 付与経路 |
|---|---|---|
| `deps` | production 依存 / github-actions / grouped PR | Dependabot の `include: scope`（人間が手で書くこともあり、その場合は production 依存更新） |
| `deps-dev` | devDependencies 単発更新 | Dependabot の `prefix-development` + `include: scope` |

### scope の `scope-empty` 許容

`scope-empty` は許容する（リポジトリ横断の変更で scope 不要なケースのため）。リポジトリ全体に跨る変更（例：ルート tsconfig 全体改訂）は scope を省略可。

### scope を追加・変更する時

1. `commitlint.config.ts` の `scope-enum` を更新（**SSoT、ここを更新しないと CI で弾かれない**）
2. 上記「領域 scope」表に行を追加
3. CLAUDE.md / CONTRIBUTING.md 等の補助ドキュメントは本セクションへのリンクで足りるため、原則更新不要（リンクが正しく追従していれば自動同期する）

---

## 共有型・スキーマ（JSON Schema を SSoT）

- **JSON Schema を Single Source of Truth とし、各言語向けの型を自動生成**する設計
- 配置・生成ツール候補・コミット方針（言語別）・選定理由の SSoT は [ADR 0006](../../adr/0006-json-schema-as-single-source-of-truth.md) を参照

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

- **Jest**（NestJS 標準。API・LLM パイプライン・ユニット・E2E スペック）
- Go 標準 `testing` + `testify`（採点ワーカー）
- **Playwright**（E2E）
- **ミューテーションテスト**：`stryker-js`（TS 向け、R2 以降）
- テストカバレッジ：Codecov

---

## 関連

- [05-runtime-stack.md](./05-runtime-stack.md) — サービスを動かす実装技術スタック
- [02-architecture.md](./02-architecture.md) — コンポーネントの責務・データフロー
- [ADR 0023: Turborepo + pnpm workspaces](../../adr/0023-turborepo-pnpm-monorepo.md)
- [ADR 0018: TypeScript のコード品質ツールに Biome](../../adr/0018-biome-for-tooling.md)
- [ADR 0019: Go のコード品質ツール](../../adr/0019-go-code-quality.md)
- [ADR 0020: Python のコード品質ツール](../../adr/0020-python-code-quality.md)
- [ADR 0006: JSON Schema を SSoT に](../../adr/0006-json-schema-as-single-source-of-truth.md)
- [ADR 0021: 補完ツールを R0 から導入](../../adr/0021-r0-tooling-discipline.md)
