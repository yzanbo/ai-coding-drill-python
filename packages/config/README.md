# @ai-coding-drill/config

**ルート直接配置の設定が `extends` で 2 層化を必要とした時のための切り出し先**。
現状はすべての設定がリポジトリルートで管理されており、本パッケージは**予約状態で空**。

設計判断の根拠：[ADR 0013](../../docs/adr/0013-biome-for-tooling.md) 「設定はリポジトリルートに直接配置、per-workspace 上書きが必要になった時のみ各 workspace に追加して extends する **2 層構造**」

- パッケージ名：`@ai-coding-drill/config`
- npm 公開しない（`"private": true`）
- 現状は依存ゼロ・設定ファイルなし（`package.json` のみが存在）

---

## 役割（2 層構造の Layer 2）

このプロジェクトは設定ファイルを **2 層構造** で管理する：

| 層 | 場所 | 状態 | 適用範囲 |
|---|---|---|---|
| **Layer 1（プライマリ）** | リポジトリルート直接配置 | **現状すべての設定がここ** | 全 workspace 一律 |
| **Layer 2（エスケープハッチ）** | **本パッケージ `packages/config/`** | **現状空（予約状態）** | per-workspace 上書きが必要になった時のみ |

### 現状の Layer 1（参考）

ルート直接配置で運用されている設定群（本パッケージとは別の場所）：

| ファイル | ツール |
|---|---|
| `biome.jsonc` | Biome（lint + format） |
| `commitlint.config.ts` | commitlint（コミットメッセージ規約） |
| `lefthook.yml` | lefthook（Git フック管理） |
| `tsconfig.json` | TypeScript（root TS 設定型チェック専用） |
| `turbo.jsonc` | Turborepo（タスク並列実行・キャッシュ） |
| `.syncpackrc.ts` | syncpack（package.json 整合性） |
| `pnpm-workspace.yaml` | pnpm Workspaces |

これらは現状ルート 1 ファイルで全 workspace 共通のルールを表現できているため、Layer 2 への切り出しは未発生。

---

## 現状（R0）

`package.json` のみが存在する**ハコだけの状態**で、設定ファイルは 1 つも入っていない。これは設計通りの状態：

- すべての設定が Layer 1（ルート直接配置）で管理されている
- per-workspace 上書きが必要になっていないため、本パッケージへの切り出しは未発生
- 「**ハコだけ先に置けば、必要になった時に追加するだけで済む**」という設計（[ADR 0018](../../docs/adr/0018-phase-0-tooling-discipline.md) の系譜）

`apps/*` が R1 で追加されても、それだけでは本パッケージに何も入らない。**「ルート 1 ファイルで表現しきれない workspace 別上書きが必要」になった瞬間**が切り出しのトリガー。

---

## 切り出しトリガー（タイミングではなく事象で判断）

以下の事象が発生した時に、Layer 1 → Layer 2 の切り出しを検討する：

| トリガー事象 | 切り出す候補 |
|---|---|
| `apps/web` と `apps/api` で **`compilerOptions` が大きく異なる** tsconfig が必要になった | `tsconfig/base.json` + `tsconfig/nextjs.json` + `tsconfig/nestjs.json` |
| **`packages/*` 配下のライブラリ向け** tsconfig が必要になった（例：`composite: true`、`declaration: true` 等） | `tsconfig/library.json` |
| **特定 workspace だけ Biome ルール上書き**が必要になった（例：`apps/web` だけ React 系ルールを緩和） | `biome/base.jsonc`（ルートから共通部分を切り出し） |
| Vitest を導入し、**複数 workspace で共有テスト設定**が必要になった（R2 以降） | `vitest/base.ts` |

**採用しないトリガー**：

- ❌ 「R1 になったら切り出す」のような時間ベース
- ❌ 「実装着手したら切り出す」のような実装依存
- ❌ 「将来必要になりそうだから先に切り出す」のような先取り

ルート 1 ファイルで表現できる限りは Layer 1 に留め置き、**事象が発生してから**切り出す。

---

## 切り出し時の規約（実際に追加することになった時のガイド）

### 命名・配置

- ツールごとにサブディレクトリを切る（`tsconfig/` / `biome/` / `vitest/` 等）
- ファイル名はケバブケース（→ [プロジェクトルート CLAUDE.md「言語・ツール非依存の規約」](../../.claude/CLAUDE.md)）
- 用途別の派生（例：`tsconfig/nextjs.json` / `tsconfig/nestjs.json`）はサブディレクトリ内で展開

### 設定ファイル形式

[ADR 0028: 設定ファイル形式の選定方針](../../docs/adr/0028-config-file-format-priority.md) に従い、自由選択時は **TS > JSONC > YAML** の優先順位：

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

`workspace:*` プロトコルでローカル参照を強制（→ [ADR 0029](../../docs/adr/0029-syncpack-package-json-consistency.md)、syncpack で機械検証）。

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

- [ADR 0013: Biome を採用](../../docs/adr/0013-biome-for-tooling.md)：「ルート直接配置 / 必要時 packages/config に切り出す **2 層構造**」を定めた本パッケージの根拠
- [ADR 0012: Turborepo + pnpm workspaces](../../docs/adr/0012-turborepo-pnpm-monorepo.md)：モノレポ構造（本パッケージの位置づけの基盤）
- [ADR 0018: 補完ツールを R0 から導入](../../docs/adr/0018-phase-0-tooling-discipline.md)：「ハコだけ先に置く」設計の系譜
- [ADR 0028: 設定ファイル形式の選定方針](../../docs/adr/0028-config-file-format-priority.md)：TS > JSONC > YAML の優先順位（切り出し時の選定基準）
- [ADR 0029: syncpack で package.json 整合性を機械強制](../../docs/adr/0029-syncpack-package-json-consistency.md)：`workspace:*` プロトコル強制
- [docs/requirements/2-foundation/06-dev-workflow.md](../../docs/requirements/2-foundation/06-dev-workflow.md)：開発フロー全体での本パッケージの位置づけ
- [プロジェクトルート CLAUDE.md](../../.claude/CLAUDE.md)：プロジェクト全体のガイダンス
