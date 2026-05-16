# components/parts/

## parts/ とは何か

**ドメイン文脈を含む再利用ブロック**を置くフォルダ。サイト固有の語彙（問題・採点・提出・ユーザー等）
を持ち、複数画面から呼ばれる部品。`components/ui/` の素材を組み合わせて作ります。

代表例（このプロジェクトで想定）：

- `problem-card/`（問題一覧で使う問題カード、難易度バッジ込み）
- `grading-result-badge/`（採点結果バッジ、状態に応じた色分け）
- `submission-list/`（提出履歴の表）
- `error-alert-dialog/`（API エラー時の共通ダイアログ）
- `compact-pagination/`（ページ送り）

## 役目

- ドメイン語彙を反映した名前で部品を作る（`ProblemCard`、`SubmissionList` 等）
- 内側で `components/ui/` を組み合わせて表示を作る
- 受け取った props を表示するのが基本。API 通信が要るときは **`hooks/use-*` を内側で呼ぶ**
- ページ固有のレイアウト・1 画面でしか使わない部品はここに置かず、`app/.../_components/` に置く

## ファイル配置

**全コンポーネントを同名フォルダで包む**ルール（[frontend-component.md](../../../../../.claude/rules/frontend-component.md)）：

- `problem-card/problem-card.tsx`（本体）
- `problem-card/problem-card.test.tsx`（テスト）
- `problem-card/problem-card.stories.tsx`（Storybook、R2 以降）
- `problem-card/_components/difficulty-badge/difficulty-badge.tsx`（内部部品も同じフォルダ規約が再帰適用）
- `problem-card/_hooks/use-mark-solved/use-mark-solved.ts`（内部フック）

単一ファイル配置（`section-header.tsx` を直接置く）は禁止。`section-header/section-header.tsx` の形で書く。
**`index.ts` は作らない**（バレル禁止）。

## やってはいけないこと

- ❌ 1 画面でしか使わない部品をここに置く（`app/.../page-dir/_components/` を使う）
- ❌ `parts/` 内で **別の `parts/` を介した循環参照**を作る（A → B → A）
- ❌ `__generated__/api/` を直接 import（API は `hooks/use-*` 経由で呼ぶ）
- ❌ `app/` を import（逆流）
