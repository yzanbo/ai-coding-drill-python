// not-found: 全 404 を共通でハンドリングする App Router の規約ファイル。
//   挙動：
//     - ログイン済み → /problems にリダイレクト
//     - 未ログイン   → / にリダイレクト（/ 側で未ログインならランディング表示）
//   理由：
//     - 主動線が /problems に集約されているため、不存在パスから無関係な
//       Next.js 既定 404 を出すより、機能ページに引き戻す方が UX が良い
//     - 認証判定は session_id Cookie の有無を Server Component で見る軽量ガード
//       に揃える（/ や /login と同じ経路）。`useGetAuthMe` の client-side 判定
//       より早く確定し、初回フェッチ中の白画面が消える
//     - 横断要件 docs/requirements/3-cross-cutting/03-page-routing.md §2 で
//       「ガード方法は server-side cookie + redirect() に揃える」と書いており、
//       not-found もこれに揃える

import { redirect } from "next/navigation";

import { hasSessionCookie } from "@/lib/auth/session-cookie";

export default async function NotFound() {
  if (await hasSessionCookie()) {
    redirect("/problems");
  }
  redirect("/");
}
