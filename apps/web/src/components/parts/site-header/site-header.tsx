"use client";

// SiteHeader: 全画面共通の上部ヘッダー。
//   要件: authentication.md §1.5 共通画面コンポーネント
//   - 未認証時: 「ログイン」リンク（/login へ）
//   - 認証時:   ユーザー名 + 「ログアウト」ボタン（POST /auth/logout 後にホームへ）
//   /login ページでは未認証時の「ログイン」CTA を出さない（同ページに既にメインの
//   「GitHub でログイン」ボタンがあるため、ヘッダー側に重ねると動線が二重になる）。
//   要件「ヘッダーは全画面共通」は枠の存在を指しており、内部 CTA の表示まで縛らない。

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { Button } from "@/components/ui/button/button";
import { useGetAuthMe } from "@/hooks/use-get-auth-me/use-get-auth-me";
import { usePostAuthLogout } from "@/hooks/use-post-auth-logout/use-post-auth-logout";

export const SiteHeader = () => {
  const { user, isAuthenticated, isLoading } = useGetAuthMe();
  const router = useRouter();
  const pathname = usePathname();
  const { logout, isPending } = usePostAuthLogout({
    onSuccess: () => router.push("/"),
  });

  // next: ログイン後の戻り先。現在の path を ?next= に入れて /login へ送る。
  //   /login 自身に居る時に /login?next=/login を作らないよう除外する。
  const nextParam =
    pathname && pathname !== "/login" ? `?next=${encodeURIComponent(pathname)}` : "";

  // isOnLoginPage: /login ページ上では未認証 CTA を出さない（動線重複の回避）。
  const isOnLoginPage = pathname === "/login";

  return (
    <header className="sticky top-0 z-40 flex h-14 items-center border-b border-border bg-background/80 px-4 backdrop-blur sm:px-6">
      <Link href="/" className="text-base font-semibold tracking-tight">
        AI Coding Drill
      </Link>
      <div className="ml-auto flex items-center gap-3">
        {isLoading ? (
          // 初回フェッチ中は何も出さない（ログイン状態を確定させてから出す）。
          <span className="text-sm text-muted-foreground" aria-hidden>
            &nbsp;
          </span>
        ) : isAuthenticated && user ? (
          <>
            <span className="text-sm text-muted-foreground">{user.displayName}</span>
            <Button variant="outline" size="sm" onClick={() => logout()} disabled={isPending}>
              ログアウト
            </Button>
          </>
        ) : isOnLoginPage ? null : (
          <Button asChild size="sm">
            <Link href={`/login${nextParam}`}>ログイン</Link>
          </Button>
        )}
      </div>
    </header>
  );
};
