// このファイルの役割：
//   Hey API が自動生成した HTTP クライアント（__generated__/api/client.gen.ts）に
//   横断的な設定を 1 回だけ被せる。生成物を直接いじらず、ここから setConfig や
//   interceptors.use で振る舞いを足す（生成物は再生成のたびに上書きされるため、
//   手書きの修正はこちら側に寄せる）。
//
//   セットしている内容：
//     - credentials: "include"   : セッション Cookie をリクエストに同梱
//     - headers: X-CSRF-Token    : 状態変更系（POST/PUT/PATCH/DELETE）の時だけ
//                                  非 HttpOnly Cookie `csrf_token` を読んで付ける
//     - baseUrl: ""              : Next.js rewrites 経由で同一オリジン扱いにする
//
//   この設定は副作用で 1 回走らせる。components/providers から import すれば、
//   ブラウザ初回のレンダリング時に必ず通る。

import { client } from "@/__generated__/api/client.gen";

// 状態変更系メソッド: CSRF ヘッダーを付ける対象。
//   GET / HEAD / OPTIONS は副作用がない前提で API 側でも CSRF を要求しない。
const MUTATING_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

// CSRF_COOKIE_NAME: API 側 apps/api/app/core/config.py の `csrf_cookie_name` 既定値と
//   ハードコードで一致させる前提。API 側で名前を変えたらここも揃えて更新する
//   （drift すると POST/PUT/DELETE が全部 403 で落ちる経路になる）。
//   env で動的に上書きする必要が出てきたら NEXT_PUBLIC_CSRF_COOKIE_NAME を導入する。
//   この定数は api-client.test.ts で API 側の既定値と一致しているかを機械検証するため export している。
export const CSRF_COOKIE_NAME = "csrf_token";

// readCookie: document.cookie から指定の Cookie 値を取り出す。
//   見つからない / SSR で document が無い場合は undefined。
//   decodeURIComponent は不正なエスケープ列が来ると URIError を投げるので、防御として
//   try/catch で受け止め、デコードできない値は undefined 扱いにする（CSRF Cookie が
//   壊れている状態で X-CSRF-Token を付けて送るとサーバ側で 403 になり、再ログインで
//   復旧する経路に倒す）。
function readCookie(name: string): string | undefined {
  if (typeof document === "undefined") return undefined;
  for (const part of document.cookie.split(";")) {
    const [k, ...rest] = part.trim().split("=");
    if (k !== name) continue;
    try {
      return decodeURIComponent(rest.join("="));
    } catch {
      return undefined;
    }
  }
  return undefined;
}

let initialized = false;

// configureApiClient: 1 回だけ走る初期化。Provider のレンダー前に呼ぶ想定。
//   多重呼び出しは無視（HMR で再評価されても interceptor を二重登録しない）。
export function configureApiClient(): void {
  if (initialized) return;
  initialized = true;

  client.setConfig({
    // baseUrl: "" にして相対パスで叩く。Next.js の rewrites（next.config.ts）が
    //   /auth, /health, /healthz を FastAPI に転送するため、ブラウザから見ると
    //   同一オリジンの API として扱える。
    baseUrl: "",
    // credentials: "include" で Cookie を毎回送る。セッション Cookie（HttpOnly）と
    //   CSRF Cookie（JS 可読）の両方を運ぶために必須。
    credentials: "include",
  });

  // request interceptor: 送信直前に Request を書き換える。
  //   状態変更メソッドの時だけ X-CSRF-Token を付ける（GET には付けない）。
  client.interceptors.request.use((request) => {
    if (!MUTATING_METHODS.has(request.method.toUpperCase())) {
      return request;
    }
    const token = readCookie(CSRF_COOKIE_NAME);
    if (!token) return request;
    // Request は immutable なヘッダーを持つので、ヘッダー付与は clone してから行う。
    const headers = new Headers(request.headers);
    headers.set("X-CSRF-Token", token);
    return new Request(request, { headers });
  });
}
