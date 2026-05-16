# lib/utils/

## lib/utils/ とは何か

**汎用関数**（日付フォーマット・文字列整形・配列処理・タイムゾーン変換等）の置き場。
React にも Next.js にも依らない、**入力に対して出力が一意に決まる**純粋な関数だけを集めます。

shadcn/ui が要求する `cn()` ヘルパーのような **1 行小物**は、フォルダではなく [lib/utils.ts](../)
（lib 直下の単発ファイル）に直接置きます。`utils/` フォルダは中身が育つ関数群が対象です。

代表例（このプロジェクトで想定）：

- `format-date/format-date.ts`（`date-fns` で日本語ロケールの「2026/05/16 21:30」表示）
- `format-duration/format-duration.ts`（ジョブの実行秒数を「3秒 / 1分20秒」表示）
- `truncate-code/truncate-code.ts`（解答コードを n 行で省略表示）

## 役目

- 1 関数 1 ファイル（or 1 フォルダ）でテストしやすく分割する
- 副作用を含まない（ファイル I/O / `console.log` / Date.now のキャッシュ等は避ける）
- 単体テスト（Vitest）をコロケーションで隣に置く（`format-date.test.ts`）

## ファイル配置

- **1 ファイル関数**：`debounce.ts` のようにそのまま置く
- **フォルダ化する関数**：`format-date/format-date.ts` + `format-date.test.ts`
- 関数名・ファイル名はケバブケース（`format-date.ts`）、関数識別子は camelCase（`formatDate`）

## やってはいけないこと

- ❌ React のフックを使う関数をここに置く（それは [hooks/](../../hooks/) へ）
- ❌ 副作用を含む関数（Date.now のキャッシュ・グローバル変数の書き換え等）を置く
  （テスト容易性が下がる）
- ❌ `__generated__/api/` を import（utils は素のロジックに保つ）
