// /login: GitHub OAuth フローの入口画面。
//   要件: docs/requirements/4-features/authentication.md §2.2 ログイン画面
//
//   役割分担：
//     - 本ファイル（Server Component）：
//       認証済みかどうかを server-side で cookie 判定し、ログイン済みなら
//       safeNextPath を通した遷移先に redirect() する。/ の挙動と同じく
//       「ネットワーク層で 307 が返り、JS 起動前に遷移が確定する」経路に
//       揃える（cross-cutting/03-page-routing.md §2 のガード方法統一）。
//     - _components/login-form（Client Component）：
//       GitHub OAuth 開始リンク + ?auth_error= のトースト + 表示。
//       認証判定は親が済ませているので、未認証ユーザー前提で動く。
//
//   ?next= は同一オリジン相対パスのみ許容（safeNextPath が外部 URL を弾く）。
//   ?auth_error= の扱いは Client 側（state を持つ必要があるため）。

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { safeNextPath } from "@/lib/utils/safe-next-path";

import { LoginForm } from "./_components/login-form/login-form";

// SESSION_COOKIE_NAME: Backend の core/config.py の session_cookie_name と一致。
const SESSION_COOKIE_NAME = "session_id";

type LoginPageProps = {
  // Next.js 16 で page に渡る searchParams は Promise。
  //   string | string[] | undefined のうち、本ページで使うのは string のみ。
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

export default async function LoginPage({ searchParams }: LoginPageProps) {
  const sp = await searchParams;
  // nextRaw: ?next= の生値。配列で来ることはまず無いが型上は string[] もあり得るので
  //   string 型に絞る。複数値が来た時は最初の 1 件だけ採用する。
  const nextRaw = Array.isArray(sp.next) ? sp.next[0] : sp.next;
  const nextPath = safeNextPath(nextRaw);

  // 認証ガード：session_id Cookie があればログイン済みとみなして遷移先に redirect。
  //   Cookie 有効性の最終判定は Backend の Depends(get_current_user) が SSoT で、
  //   ここは UX 用の早期分岐（チラ見せ防止）。失効した Cookie が残っている場合は
  //   遷移先で API 401 が出てログアウト相当に倒れる。
  const sessionCookie = (await cookies()).get(SESSION_COOKIE_NAME);
  if (sessionCookie) {
    redirect(nextPath);
  }

  return <LoginForm nextPath={nextPath} />;
}
