# 0018. TypeScript のコード品質ツールに Biome を採用し、設定は apps/web/ 配下に直接配置する

- **Status**: Accepted（Frontend 用途、Amended by [0033](./0033-backend-language-pivot-to-python.md) / [0036](./0036-frontend-monorepo-pnpm-only.md)）
- **Date**: 2026-05-09 <!-- ADR 0036 拡張により設定配置を root → apps/web/ に移動。Frontend 用途として継続採用 -->
- **Decision-makers**: 神保 陽平

> **Note**：Python pivot（[ADR 0033](./0033-backend-language-pivot-to-python.md)）+ ADR 0036 拡張により、設定の物理配置が **root → `apps/web/`** に変更された：
>
> - 旧：`/biome.jsonc`（root スキャン、全 TS workspace を見る）
> - 新：`/apps/web/biome.jsonc`（apps/web 配下のみスキャン、Frontend 単一 app に閉じる）
>
> ツール選定（Biome 採用）は維持。本文中の「リポジトリルートに直接配置」記述は **`apps/web/` 配下に直接配置** と読み替える。詳細は [ADR 0036](./0036-frontend-monorepo-pnpm-only.md) を参照。

## Context（背景・課題）

TypeScript のリンタ・フォーマッタ選定と、モノレポにおける設定の物理配置を決める必要がある。

- TypeScript は本プロジェクトの主言語（フロント / バックエンドの 2 アプリ + 共有パッケージ群）
- ESLint + Prettier の組み合わせは設定ファイル乱立・実行速度・依存ツリーの肥大化が常態化している
- モノレポ規模：MVP で 5〜10 パッケージ、R7 で 8〜12 パッケージ
- CI 時間を抑えたい
- 「3 言語に等価な品質ゲートを設計した」と語れる構成にしたい（Go / Python の同様 ADR は別ファイル）

関連：

- Go の品質ツール → [ADR 0019](./0019-go-code-quality.md)
- Python の品質ツール → [ADR 0020](./0020-python-code-quality.md)

## Decision（決定内容）

- **lint + format に [Biome](https://biomejs.dev/)** を採用する（Rust 製、lint と format を統合）
- **型チェックには `tsc --noEmit`** を併用する（Biome は型チェックをカバーしないため）
- **ESLint + Prettier は採用しない**
- **設定ファイルは `apps/web/biome.jsonc` に直接配置**する（Frontend 単一 app 化（→ [ADR 0036](./0036-frontend-monorepo-pnpm-only.md)）に伴い、root 直接配置から apps/web 配下へ移動）。`packages/config/` 配下に共有 base ファイルを置く 2 段構成は採用しない
- 将来 apps/web 内の sub-package 固有の上書きが必要になった場合のみ、追加の `biome.jsonc` を作成し apps/web/biome.jsonc を `extends` で継承する

## Why（採用理由）

### なぜ Biome か（ESLint + Prettier ではなく）

1. **lint + format の統合で設定ファイル乱立を回避**
   - `.eslintrc` / `.prettierrc` / プラグイン群を 1 ファイル（`biome.jsonc`）に統合
   - 共有設定の物理ファイル数が最小化される
2. **CI 高速化（ESLint 比 25〜100 倍）**
   - Rust 製で並列実行が高速、CI 時間とローカル feedback ループの両方で効く
3. **`tsc --noEmit` との明確な役割分担**
   - Biome は構文・スタイル、`tsc` は型という分離で責務が混乱しない
4. **dprint より統合的**
   - dprint はフォーマット専業で linter 機能なし、Biome の方が用途を 1 ツールに集約できる

### なぜ apps/web 直接配置か（`packages/config/biome-config/` を経由しない）

1. **Biome は単一設定で全体を再帰スキャンする設計**
   - ESLint / Prettier のような「各 package 配下の `.eslintrc` を辿る」モデルとは前提が違う
   - 消費者は apps/web 単一に集中するため、共有 base を別ディレクトリに切り出す indirection の便益がない
2. **YAGNI**
   - `packages/config` を別 npm パッケージとして公開する未来は想定されない（個人ポートフォリオ）
   - 「将来別プロジェクトで再利用するかも」という抽象化を先取りしない
3. **役割が見えやすい**
   - 実際の規則が `apps/web/biome.jsonc` に直接書かれていれば、新規参画者が 1 ファイルを読むだけで全体像を把握できる
4. **業界実例**
   - Vercel turborepo 公式テンプレートの Biome 版・Astro モノレポ・Bluesky social-app 等、主要モノレポは Biome を単一場所に直接配置している
5. **tsconfig との非対称は問題にならない**（旧理由）
   - 旧設計では tsconfig が `packages/config/tsconfig/` の多消費者前提であり Biome は単一消費者前提という対比が成立していたが、ADR 0036 で `packages/config/` 自体が廃止され apps/web 単一 app に集約された結果、Biome / tsconfig はいずれも `apps/web/` 直下に並ぶ対称構造となり、この論点自体が解消された

## Alternatives Considered（検討した代替案）

### TypeScript のコード品質ツール

| 候補 | 採用しなかった理由 |
|---|---|
| ESLint + Prettier | 設定ファイル乱立、CI が遅い（Biome 比 25〜100 倍）、依存ツリー肥大 |
| dprint | linter 機能なし、Biome の方が統合的 |
| Rome（Biome の前身） | 開発停止 |

### Biome 設定の物理配置

| 候補 | 採用しなかった理由 |
|---|---|
| `apps/web/biome.jsonc` 直接配置（採用） | — |
| `packages/config/biome-config/biome.base.jsonc` ← `biome.jsonc`（extends 1 行）| indirection の便益が現状ゼロ。役割が見えづらく、共有 base と extends 元の二重メンテが発生（さらに ADR 0036 で `packages/config/` 自体が廃止） |
| 各 workspace に `biome.jsonc` を必須化し `turbo run lint` で集約 | Biome は単一設定で全体スキャンする設計のため、workspace 増加でボイラープレートが嵩む。Turborepo 自体も ADR 0036 で不採用 |

## Consequences（結果・トレードオフ）

### 得られるもの

- 設定統合（`biome.jsonc` 1 ファイル）で TS の lint / format / import 整理が完結
- CI 高速化（ESLint + Prettier 比で大幅短縮見込み）
- 新規参画者が Biome 設定の場所を探さなくて済む（`apps/web/` 直下にある）
- 型チェック（`tsc`）と構文・スタイル（Biome）の責務が明確
- Frontend ツーリング（Biome / Knip / syncpack / tsconfig）が `apps/web/` 配下に閉じることで、root と apps/web の責務分離が明確になる（→ [ADR 0036](./0036-frontend-monorepo-pnpm-only.md)）

### 失うもの・受容するリスク

- ESLint プラグインエコシステム（特定ライブラリ向けの lint ルール）を使えない
- Biome の rule set はまだ ESLint 比で薄い領域がある（typescript-eslint の高度な型ベースルール等）
- 将来「Biome 共有設定を別プロジェクトに切り出して再利用したい」というニーズが発生した場合、別 npm パッケージ（独立リポジトリ または Frontend monorepo 拡張時の共有 workspace）への再構成が必要

### 将来の見直しトリガー

- 特定 ESLint プラグインが必須となるルールが必要になった場合 → ESLint 併用または部分移行を検討
- Biome 共有設定を別 npm パッケージとして公開し他プロジェクトで利用するニーズが発生した場合 → 独立リポジトリへの切り出しを検討
- apps/web 内の sub-package 固有の Biome 上書きが 3 つ以上発生し、共通の中間レイヤを抽出する価値が出てきた場合 → apps/web 内の共有 workspace（例：`apps/web/packages/biome-config/`）に中間 base を新設して各 workspace から extends する構造を再評価

## References

- [06-dev-workflow.md: コード品質ツール](../requirements/2-foundation/06-dev-workflow.md#コード品質ツール)
- [ADR 0019: Go のコード品質ツール](./0019-go-code-quality.md)
- [ADR 0020: Python のコード品質ツール](./0020-python-code-quality.md)
- [ADR 0021: R0 ツール導入規律](./0021-r0-tooling-discipline.md)
- `apps/web/biome.jsonc` — 統合後の設定本体（apps/web/ 配下に閉じる、→ [ADR 0036](./0036-frontend-monorepo-pnpm-only.md)）
- [Biome 公式](https://biomejs.dev/)
