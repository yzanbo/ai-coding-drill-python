// / : ログイン済みなら /problems に redirect、未ログインならランディング画面を表示。
//   - ログイン済みの主動線は問題一覧なので、トップに留まらせず即遷移する。
//   - 未ログインユーザーは / に留まり、サイト概要 + ログイン CTA を見る。
//   - 認証判定は server-side で session_id Cookie の有無のみを見る軽量ガード。
//     セッションの実有効性は Backend の Depends(get_current_user) が SSoT で、
//     ここはあくまで UX 用の早期分岐。

import Link from "next/link";
import { redirect } from "next/navigation";

import { Button } from "@/components/ui/button/button";
import { hasSessionCookie } from "@/lib/auth/session-cookie";

export default async function RootPage() {
  if (await hasSessionCookie()) {
    redirect("/problems");
  }

  // 未ログイン：サイト概要 + ログイン誘導のシンプルなランディング画面。
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col items-center justify-center px-6 py-24 text-center">
      <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl">AI Coding Drill</h1>
      <p className="mt-6 max-w-xl text-base text-muted-foreground">
        LLM が自動生成した TypeScript
        の練習問題を、サンドボックスで採点しながら無限に解ける学習サイト。
      </p>
      <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
        <Button asChild size="lg">
          <Link href="/login">GitHub でログイン</Link>
        </Button>
        <Button asChild size="lg" variant="outline">
          <Link href="/problems">問題を見る</Link>
        </Button>
      </div>
    </main>
  );
}
