# lib/validation/

## lib/validation/ とは何か

**Zod スキーマ**（入力データの形を宣言する仕組み）の置き場。フォーム入力・URL クエリ等、
**ブラウザ側で検証したい値**の形を定義します。React Hook Form と `@hookform/resolvers/zod` で
組み合わせると、入力欄ごとのエラー表示も自動で配線できます。

代表例（このプロジェクトで想定）：

- `login-form-schema.ts`（GitHub OAuth ボタン以外に独自ログインがある場合）
- `problem-filter-schema.ts`（問題一覧のフィルタフォーム：難易度・カテゴリ）
- `answer-submit-schema.ts`（解答送信フォーム：コード文字列の長さ上限等）

## 役目

- 入力 1 つに対して 1 ファイル：`<name>-schema.ts` でスキーマを `export`、`<Name>FormValues`
  型を `export type` で同時に出す
- API レスポンスの検証も必要なら、生成物の Zod スキーマ（`__generated__/api/` 配下）を流用する。
  ここでは **画面入力の正規化** に集中する
- HTTP リクエスト本体（`fetch` の引数組み立て等）は書かない。それは `__generated__/api/` 側

## 命名規則

```ts
// login-form-schema.ts
import { z } from "zod";

export const loginFormSchema = z.object({
  email: z.string().email("メールアドレスの形式が正しくありません"),
});

export type LoginFormValues = z.infer<typeof loginFormSchema>;
```

- ファイル名：`<form-name>-schema.ts`
- スキーマ変数：`<formName>Schema`（camelCase）
- 型：`<FormName>FormValues`（[frontend.md](../../../../../.claude/rules/frontend.md) §命名規則（実装契約））

## やってはいけないこと

- ❌ API レスポンスの型をここで手書きする（生成物（`__generated__/api/`）の Zod を使う）
- ❌ React のフックや JSX をここに置く（純粋なスキーマだけに保つ）
- ❌ `index.ts` で再エクスポート（バレル禁止）
