# components/ui/

## ui/ とは何か

**見た目だけの汎用部品**を置くフォルダ。shadcn/ui（`pnpm dlx shadcn@latest add ...`）で生成された
ボタン・入力欄・ダイアログ・カード等の素材と、その薄い拡張（社内拡張カラーピッカー等）。

ドメイン語彙（問題・採点・ユーザー等）は **含めません**。例えば「問題カード」のような名前は
ここではなく `components/parts/` に置きます。

代表例：

- `button/button.tsx` / `input/input.tsx` / `dialog/dialog.tsx` / `card/card.tsx`（shadcn/ui の素を **同名フォルダで包む**）
- `birthdate-picker/birthdate-picker.tsx` / `combobox/combobox.tsx`（shadcn の組み合わせ拡張）

## ルール

- **lint / format は切る**：`pnpm dlx shadcn@latest add` で再生成される時に手書きスタイルが
  飛ばないようにするため。設定の正本は [biome.jsonc](../../../biome.jsonc) と
  [knip.config.ts](../../../knip.config.ts) の `components/ui/**` 除外
- **`cn()` ヘルパー**は [lib/utils.ts](../../lib/) から import する（shadcn 規約）
- **テスト・ストーリーはここには書かない**（生成物前提のため）。ドメイン側で使う時に
  `parts/` 側でテストを書く

## ファイル配置

- **全部品は同名フォルダで包む**：`button/button.tsx`、`birthdate-picker/birthdate-picker.tsx`（テスト・Storybook 同居前提、詳細は [frontend-component.md](../../../../../.claude/rules/frontend-component.md)）
- **shadcn 生成直後のリネーム**：`pnpm dlx shadcn add button` の出力は `ui/button.tsx`（単一ファイル）になるため、生成直後に `ui/button/button.tsx` へリネームする
- **`index.ts` は作らない**：import は常に具体的なファイルパス（バレル禁止、→ [frontend.md](../../../../../.claude/rules/frontend.md)）

## やってはいけないこと

- ❌ ドメイン語彙の入った部品をここに置く（`ProblemCard.tsx` 等 → `parts/` へ）
- ❌ ここに置いた部品から `lib/api/` や `hooks/use-get-*` を呼ぶ
  （見た目専用に保つため、データ取得は受け取った props で表示するだけ）
- ❌ shadcn/ui 生成ファイルを書き換えて構造を変える（次の `shadcn add` で衝突する。
  拡張したい時は新しいファイル・新しいフォルダで包む）
