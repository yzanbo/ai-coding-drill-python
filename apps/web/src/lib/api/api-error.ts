// ApiError: SDK 呼び出しの失敗を 1 つの型にまとめる。
//   Hey API の SDK は throwOnError=false の時 { error, response } を返すだけで
//   status を持たないオブジェクトになりうる。useQuery / useMutation 側で status を
//   見て分岐したいので、ここで status / body / message を束ねた Error 派生に詰め直す。
export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(status: number, body: unknown, message?: string) {
    super(message ?? `API error (status=${status})`);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

// throwIfError: SDK 呼び出しの戻り値を見て、エラーなら ApiError を投げる。
//   通常時は data を返す。useQuery の queryFn でラップして使う。
export async function throwIfError<T>(
  call: Promise<{ data?: T; error?: unknown; response?: Response }>,
): Promise<T> {
  const { data, error, response } = await call;
  // response が undefined になるのは fetch 自体が失敗した時（ネットワーク断・CORS 等）。
  //   status=0 として扱い、上位の extractApiErrorMessage で「通信失敗」メッセージに振り分ける。
  if (!response) throw new ApiError(0, error);
  if (!response.ok) throw new ApiError(response.status, error);
  return data as T;
}
