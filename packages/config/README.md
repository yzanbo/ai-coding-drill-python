# @ai-coding-drill/config

**多消費者前提の shared config（tsconfig / Vitest 等）を集約する場所**。各 workspace が同じ base を `extends` / `import` する形で参照する。

R0 現状はまだ消費者（`apps/*`）が存在しないため、本パッケージは `package.json` のみ・**設定ファイルは未投入**。R1 で apps を追加する際に `tsconfig/base.json` 等を投入する。

設計判断の根拠：[ADR 0018](../../docs/adr/0018-biome-for-tooling.md)「`packages/config/` の責務は**多消費者前提の shared config（tsconfig）専用**に絞る。Biome 等の単一インスタンスで完結するツールはルート直接配置とする」

- パッケージ名：`@ai-coding-drill/config`
- npm 公開しない（`"private": true`）
- 現状は依存ゼロ・設定ファイルなし（`package.json` のみが存在）

---

## 役割（2 層構造の Layer 2）

このプロジェクトは設定ファイルを **2 層構造** で管理する：

| 層 | 場所 | 性質 |
|---|---|---|
| **Layer 1（ルート直接配置）** | リポジトリルート | 単一インスタンスで完結する設定（全 workspace 一律のルール） |
| **Layer 2（`packages/config/`）** | 本パッケージ | **複数 workspace が同じ base を継承する**設定 |

各ツールの性質に応じて配置先が決まる。ツールごとの分類は次の通り：

### Layer 2（本パッケージ）の標準的な住人

性質上**多消費者前提**のツール。R1 以降で消費者（apps）が現れた時点で本パッケージに投入する：

| ツール | 投入時期 | 理由 |
|---|---|---|
| **tsconfig** | R1（apps 着手時） | 各 workspace が `jsx` / `module` / `paths` 等を個別設定する一方で `strict` / `target` / `lib` 等の base は共通。**構造上ほぼ確実に多消費者になる** |
| **Vitest** | R2 以降（テスト導入時） | 各 workspace が test path / env / setup を個別設定する一方で coverage / reporter / global setup は共通。**多消費者になることがほぼ確定** |

これらは「事象トリガーで切り出すか検討」ではなく、消費者が現れた瞬間に Layer 2 に入れるのがデフォルト。

### Layer 1（ルート直接配置）の住人

性質上**単一インスタンスで完結する**ツール。本パッケージには置かない：

| ファイル | ツール | ルート固定の理由 |
|---|---|---|
| `biome.jsonc` | Biome | monorepo native（v2 以降）で 1 root config + `overrides` で完結 → [ADR 0018](../../docs/adr/0018-biome-for-tooling.md) |
| `turbo.jsonc` | Turborepo | モノレポ全体のオーケストレータ、root 固定 |
| `lefthook.yml` | lefthook | Git フックは repo-global、1 つしか持てない |
| `commitlint.config.ts` | commitlint | commit 単位の検証、root 固定 |
| `.syncpackrc.ts` | syncpack | 全 `package.json` を再帰スキャンする横断ツール → [ADR 0024](../../docs/adr/0024-syncpack-package-json-consistency.md) |
| `tsconfig.json`（ルート） | TypeScript | `tsc --noEmit -p tsconfig.json` のエントリ（中身は将来 `packages/config/tsconfig/base.json` を `extends` する想定） |
| `pnpm-workspace.yaml` | pnpm | workspace 定義、root 固定 |

これらを本パッケージに移しても、消費者が 1 つしかいないため indirection の便益がなく、二重メンテのコストだけが発生する。

---

## 現状（R0）

`package.json` のみが存在する**ハコだけの状態**で、設定ファイルは 1 つも入っていない。これは設計通りの状態：

- 標準的な Layer 2 住人である **tsconfig は消費者（`apps/*`）が R0 時点で存在しない**ため、未投入
- **Vitest は R2 以降の導入予定**のため、未投入
- 「**ハコだけ先に置けば、消費者が現れた時に追加するだけで済む**」という設計（[ADR 0021](../../docs/adr/0021-r0-tooling-discipline.md) の系譜）

R1 で `apps/*` が追加されたタイミングで `tsconfig/base.json` を投入するのが第一歩。

---

## 投入タイミング

### tsconfig（R1）

`apps/web` / `apps/api` を最初に追加した時点で以下を一括投入する：

| ファイル | 用途 |
|---|---|
| `tsconfig/base.json` | 全 TS workspace 共通（`strict` / `target` / `lib` / `moduleResolution` 等） |
| `tsconfig/nextjs.json` | `apps/web` 用（base + `jsx` + Next 向け） |
| `tsconfig/nestjs.json` | `apps/api` 用（base + decorator + commonjs） |
| `tsconfig/library.json` | `packages/*` 用（base + `composite: true` + `declaration: true`） |

各 workspace の `tsconfig.json` は上記のいずれかを `extends` する薄いラッパーになる。ルート `tsconfig.json` も同様に `tsconfig/base.json` を `extends` する想定。

### Vitest（R2 以降）

テストフレームワーク導入時に以下を投入する：

| ファイル | 用途 |
|---|---|
| `vitest/base.ts` | 全 TS workspace 共通（coverage / reporter / global setup） |

各 workspace の `vitest.config.ts` は base を import して個別設定（test path / env 等）を上書きする。

### Biome 等の例外的な切り出し（通常は発生しない）

性質上ルート固定のツール（Biome / Turbo / lefthook / commitlint / syncpack 等）も、稀に Layer 2 への切り出しが必要になることがある。判断は事象トリガーで：

| トリガー事象 | 切り出し候補 |
|---|---|
| Biome の `overrides` で per-workspace ルール差を表現できなくなった（[ADR 0018](../../docs/adr/0018-biome-for-tooling.md) L99 の「workspace 固有上書きが 3 つ以上」相当） | `biome/base.jsonc`（ルートから base 部分を切り出し、workspace 側は extends） |

**採用しないトリガー**：

- ❌ 「R1 / R2 になったから切り出す」のような時間ベース（tsconfig / Vitest 以外には適用しない）
- ❌ 「将来必要になりそうだから先に切り出す」のような先取り
- ❌ 「他のツールと統一したいから」のような対称性追求

ルート 1 ファイルで表現できる限りは Layer 1 に留め置く。

---

## 切り出し時の規約（実際に追加することになった時のガイド）

### 命名・配置

- ツールごとにサブディレクトリを切る（`tsconfig/` / `biome/` / `vitest/` 等）
- ファイル名はケバブケース（→ [プロジェクトルート CLAUDE.md「言語・ツール非依存の規約」](../../.claude/CLAUDE.md)）
- 用途別の派生（例：`tsconfig/nextjs.json` / `tsconfig/nestjs.json`）はサブディレクトリ内で展開

### 設定ファイル形式

[ADR 0022: 設定ファイル形式の選定方針](../../docs/adr/0022-config-file-format-priority.md) に従い、自由選択時は **TS > JSONC > YAML** の優先順位：

- 型 export があるツール（Vitest 等）→ `.ts` でフィールド typo を保存時に弾く
- 純データ設定（tsconfig 等）→ JSONC（コメント可）
- ツール強制 / 慣習がある場合（`tsconfig.json` / `biome.jsonc` 等）→ それに従う

### `package.json` の `exports` フィールド

設定ファイルを追加したら、`package.json` の `exports` で**外から参照可能なエントリポイント**を明示する：

```jsonc
// 例：tsconfig を切り出した時
{
  "name": "@ai-coding-drill/config",
  "exports": {
    "./tsconfig/base": "./tsconfig/base.json",
    "./tsconfig/nextjs": "./tsconfig/nextjs.json"
  }
}
```

`exports` で公開していないファイルは**外から参照されない前提**として扱う。

### 切り出し作業のセット

切り出し時は以下を**同時に**行う（Layer 1 と Layer 2 の二重管理を避けるため）：

1. ルートの該当ファイルから共通部分を本パッケージに移動
2. ルートのファイルは「workspace 共通参照」または削除し、各 workspace で `extends` する形に
3. 該当 workspace の `package.json` に `"@ai-coding-drill/config": "workspace:*"` を追加
4. 動作確認後、ADR で切り出し判断を記録（例：`ADR 00XX: tsconfig を packages/config に切り出し`）

---

## 切り出し後の参照例（将来の想定）

### apps から借りる宣言

```jsonc
// apps/web/package.json（将来、tsconfig を切り出した場合）
{
  "devDependencies": {
    "@ai-coding-drill/config": "workspace:*"
  }
}
```

`workspace:*` プロトコルでローカル参照を強制（→ [ADR 0024](../../docs/adr/0024-syncpack-package-json-consistency.md)、syncpack で機械検証）。

### tsconfig の extends

```jsonc
// apps/web/tsconfig.json（将来）
{
  "extends": "@ai-coding-drill/config/tsconfig/nextjs",
  "compilerOptions": {
    // 個別 workspace 固有の上書きはここに最小限だけ書く
  },
  "include": ["src/**/*"]
}
```

### Biome の extends

```jsonc
// 別 workspace で per-workspace 上書きが必要になった場合
{
  "extends": ["@ai-coding-drill/config/biome/base"]
}
```

---

## やってはいけないこと

- **同じ設定をルート（Layer 1）と本パッケージ（Layer 2）に二重管理しない**：切り出し時はルート側を必ず更新し、SSoT を分裂させない
- **per-workspace 上書きが必要ない設定を「念のため」切り出さない**：YAGNI 違反。Layer 1 で済むものは Layer 1 に置き続ける
- **コードロジック（実行時に動く汎用ヘルパー）を置かない**：本パッケージは「**設定ファイルの切り出し先**」が役割。汎用ヘルパーは別パッケージ（例：将来の `packages/utils/`）として作る
- **外部 npm に公開しない**：`"private": true` を必ず維持。internal-only スコープ
- **設計判断の根拠を ADR に書く前に切り出さない**：「**なぜ切り出したか / 何を切り出したか**」が説明できない状態で全体に影響する変更を加えない

---

## 関連ドキュメント

- [ADR 0018: Biome を採用](../../docs/adr/0018-biome-for-tooling.md)：「ルート直接配置 / 必要時 packages/config に切り出す **2 層構造**」を定めた本パッケージの根拠
- [ADR 0023: Turborepo + pnpm workspaces](../../docs/adr/0023-turborepo-pnpm-monorepo.md)：モノレポ構造（本パッケージの位置づけの基盤）
- [ADR 0021: 補完ツールを R0 から導入](../../docs/adr/0021-r0-tooling-discipline.md)：「ハコだけ先に置く」設計の系譜
- [ADR 0022: 設定ファイル形式の選定方針](../../docs/adr/0022-config-file-format-priority.md)：TS > JSONC > YAML の優先順位（切り出し時の選定基準）
- [ADR 0024: syncpack で package.json 整合性を機械強制](../../docs/adr/0024-syncpack-package-json-consistency.md)：`workspace:*` プロトコル強制
- [docs/requirements/2-foundation/06-dev-workflow.md](../../docs/requirements/2-foundation/06-dev-workflow.md)：開発フロー全体での本パッケージの位置づけ
- [プロジェクトルート CLAUDE.md](../../.claude/CLAUDE.md)：プロジェクト全体のガイダンス
