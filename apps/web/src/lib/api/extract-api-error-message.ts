// このファイルの役割：
//   API 応答（Hey API SDK の戻り値）からユーザー向けエラーメッセージを取り出す純粋関数。
//   FastAPI の例外ハンドラは `{ "detail": "..." }` 形式で返すので、それを優先的に拾う。
//   "interceptor"（リクエスト / レスポンスへの差し込み処理）ではなく、status と body から
//   文字列を組み立てるだけの formatter。リクエスト側の差し込みは ./api-client.ts 側にある。
//   詳細仕様: docs/requirements/3-cross-cutting/02-api-conventions.md

// ApiErrorShape: FastAPI が返す代表的なエラーボディ。
//   detail は文字列（HTTPException）か配列（バリデーション）になる。
type ApiErrorShape = {
  detail?: string | Array<{ msg?: string }>;
};

// extractApiErrorMessage: HTTP ステータス + ボディから日本語メッセージを組み立てる。
//   status が 0 / undefined ならネットワーク失敗扱いにする。
export function extractApiErrorMessage(status: number | undefined, body: unknown): string {
  if (!status) return "通信に失敗しました。しばらく経ってから再度お試しください。";

  const detail = (body as ApiErrorShape | undefined)?.detail;
  if (typeof detail === "string" && detail.length > 0) return detail;
  // バリデーションエラー（detail が配列）の時は先頭メッセージを表示。
  //   空配列 / msg 無し / msg が空文字 の場合は下の status 別フォールバックに流す。
  if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg;

  if (status === 401) return "ログインが必要です。";
  if (status === 403) return "この操作を実行する権限がありません。";
  if (status === 404) return "対象が見つかりません。";
  if (status >= 500) return "サーバーでエラーが発生しました。";
  return "エラーが発生しました。";
}
