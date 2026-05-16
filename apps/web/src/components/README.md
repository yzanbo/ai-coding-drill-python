# components/

## components/ とは何か

複数のページで使い回す **画面部品**（ボタン・カード・モーダル等）の置き場です。
ページ 1 つでしか使わない部品はここに置きません（それは `app/.../page-dir/_components/` に置く、
コロケーション、→ [frontend.md](../../../../.claude/rules/frontend.md)）。

中身は役割で 3 つに分けます：

| サブフォルダ | これは何か（役目） |
|---|---|
| `ui/` | **見た目だけの汎用部品**。shadcn/ui で生成した素のボタン・入力欄・ダイアログ・カード等と、その薄い拡張。ドメイン語彙（問題・採点・ユーザー等）は含めない。**lint は切る**（[biome.jsonc](../../biome.jsonc) / [knip.config.ts](../../knip.config.ts) で `ui/` を除外。再生成で書き戻されるため） |
| `parts/` | **ドメイン文脈を含む再利用ブロック**。問題カード（`problem-card/`）・採点結果バッジ（`grading-badge/`）等、サイト固有の語彙を持ち、複数画面から使うもの。`ui/` の素材を組み合わせて作る |
| `providers/` | **React の Provider 群**。TanStack Query / テーマ / 認証セッション等、アプリ全体のコンテキストを供給する。`app/layout.tsx` から `<RootProviders>{children}</RootProviders>` のように使う |

## 役目

- ページ間で共有する画面部品を、役割（汎用 / ドメイン / Provider）で分けて置く
- 表示と最小限の操作を担う。データ取得・グローバル状態の更新は **`hooks/` 経由**で行う
- ページ固有の部品は置かない（コロケーションで `app/` 側に置く）

## ファイル配置

**全てのコンポーネントは同名フォルダで包む**（`button/button.tsx`、`problem-card/problem-card.tsx`）。
単一ファイル配置（`button.tsx` をそのまま置く）は禁止。テスト・Storybook を同フォルダにコロケーション
させるためのルール。詳細は [.claude/rules/frontend-component.md](../../../../.claude/rules/frontend-component.md)。

- **本体**：`<name>/<name>.tsx`
- **テスト**：`<name>/<name>.test.tsx`（Vitest + Testing Library）
- **Storybook**：`<name>/<name>.stories.tsx`（R2 以降の Storybook 導入後）
- **内部部品・フック**：`<name>/_components/` `<name>/_hooks/`（再帰的に同じフォルダ規約）
- **`index.ts` は作らない**：import は常に具体的なファイルパスを指定する（バレル禁止）

shadcn/ui の例外処理（`pnpm dlx shadcn add <name>` の出力は単一ファイルのため、生成直後に同名フォルダへ
リネームする）は [frontend-component.md §1](../../../../.claude/rules/frontend-component.md) を参照。

## やってはいけないこと

- ❌ `parts/` 内で別の `parts/` を循環参照する（A → B → A）
- ❌ `ui/` にドメイン語彙（`ProblemCard` 等）を入れる（汎用性が壊れる）
- ❌ `components/` から `app/` を import（逆流。ページが部品を使うのであって、部品はページを知らない）
- ❌ ページ 1 つでしか使わない部品をここに置く（`app/.../_components/` を使う）

詳しい配置・命名・import 方向は [.claude/rules/frontend.md](../../../../.claude/rules/frontend.md) の **§ディレクトリ構成**・**§コロケーション原則**。
