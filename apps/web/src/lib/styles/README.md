# lib/styles/

## lib/styles/ とは何か

**Tailwind の `className` 文字列だけでは表現しきれない複雑なスタイル定数**の置き場。
ほとんどの装飾は Tailwind（と shadcn のテーマ変数）で済むので、ここに置くものは限定的です。

代表例（このプロジェクトで想定）：

- `codemirror-theme.ts`（CodeMirror 6 の色テーマ。`@codemirror/view` の `EditorView.theme()` に
  渡す JS オブジェクト）
- `print-stylesheet.ts`（印刷用 CSS をテンプレ文字列で持つ場合）

## 役目

- Tailwind / shadcn テーマ変数では表現しきれない構造化スタイル（外部ライブラリに JS オブジェクトで
  渡すもの）に **限定**する
- 通常のクラス文字列（条件付き class 含む）は `cn()` を使ってコンポーネント内で組み立てる
- `className` で済む装飾を **わざわざここに切り出さない**（YAGNI）

## やってはいけないこと

- ❌ クラス文字列（`"px-4 py-2 rounded-lg ..."`）を定数化してここに置く
  （Tailwind を直接書ける時はその方が読みやすい。条件付きは `cn()` で）
- ❌ Tailwind の `tailwind.config` をここに分割（テーマ設定の正本は `tailwind.config` 側）
- ❌ React のフックや JSX をここに置く
