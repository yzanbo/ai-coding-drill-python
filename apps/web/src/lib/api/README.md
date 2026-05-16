# lib/api/

## lib/api/ とは何か

**手書きの API ラッパ**を置くフォルダ。Hey API が `apps/api/openapi.json` から作る生のクライアント
（[__generated__/api/](../../__generated__/api/)）に被せる薄い補強層です。

「生成物そのもの」は __generated__ 側、「生成物を呼びやすくする手書きコード」が lib/api/。
分けることで、API 仕様（OpenAPI）が変わって生成物が書き換わっても、エラー解釈や認証等の
**手書き部分は無傷で残ります**。

代表例（このプロジェクトで想定）：

- `api-error-interceptor.ts`（401 を捉えて `/login` にリダイレクト、レート制限のリトライ等）
- `extract-error-message.ts`（FastAPI のエラー JSON から表示用メッセージを取り出す）
- `hey-api-config.ts`（生成物のクライアントに `baseURL` / `credentials: "include"` を仕込む）

## 役目

- 生成物のクライアントに **横断的な前処理・後処理**（認証 Cookie 同梱・エラー解釈等）を被せる
- ドメインフックからは「ここを呼べば認証込みで叩ける」状態にする
- 生成物そのものを **書き換えない**。手書き層で吸収する

## やってはいけないこと

- ❌ ここに型定義や HTTP クライアントを **手書きする**（型は OpenAPI から生成する一択、→ [ADR 0006](../../../../../docs/adr/0006-json-schema-as-single-source-of-truth.md)）
- ❌ React のフック（`useState` 等）を含む実装をここに置く（それは [hooks/](../../hooks/) へ）
- ❌ [components/](../../components/) を import（逆流）
