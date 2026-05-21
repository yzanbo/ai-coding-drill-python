"use client";

// SiteHeader: 全画面共通の上部ヘッダー。
//   要件: authentication.md §1.5 共通画面コンポーネント
//   - 未認証時: 「ログイン」リンク（/login へ）
//   - 認証時:   グローバルリンク（問題一覧 / 解答履歴 / 学習統計 / 弱点）
//               + ユーザー名 + ログアウト
//   /login ページでは未認証時の「ログイン」CTA を出さない（同ページに既にメインの
//   「GitHub でログイン」ボタンがあるため、ヘッダー側に重ねると動線が二重になる）。
//   要件「ヘッダーは全画面共通」は枠の存在を指しており、内部 CTA の表示まで縛らない。

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { Button } from "@/components/ui/button/button";
import { useGetAuthMe } from "@/hooks/use-get-auth-me/use-get-auth-me";
import { usePostAuthLogout } from "@/hooks/use-post-auth-logout/use-post-auth-logout";
import { cn } from "@/lib/utils";

// GLOBAL_NAV_LINKS: ログイン時にヘッダーへ並べる主動線。
//   ここを 1 箇所で管理することで、ナビ項目の増減が起きてもヘッダー実装側を
//   触らずに済む。SSoT は本配列。
const GLOBAL_NAV_LINKS: { href: string; label: string }[] = [
  { href: "/problems", label: "問題一覧" },
  { href: "/me/history", label: "解答履歴" },
  { href: "/me/stats", label: "学習統計" },
  { href: "/me/weakness", label: "弱点" },
  // 生成履歴は問題一覧ページの右上に動線を集約（生成 → 履歴の流れがそこで完結するため）。
];

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
      {/* グローバルリンク: ログイン時のみ表示。現在ページは aria-current で印を付け、
          見た目も text-foreground で強調する。未ログイン時 / 初期ローディング中は
          領域ごと出さない（チラ見せ防止 + 動線の混乱回避）。 */}
      {isAuthenticated && user ? (
        <nav aria-label="グローバルナビ" className="ml-8 hidden items-center gap-4 sm:flex">
          {GLOBAL_NAV_LINKS.map((link) => {
            const isCurrent = pathname === link.href;
            return (
              <Link
                key={link.href}
                href={link.href}
                aria-current={isCurrent ? "page" : undefined}
                className={cn(
                  "text-sm transition-colors duration-200 hover:text-foreground",
                  isCurrent ? "font-semibold text-foreground" : "text-muted-foreground",
                )}
              >
                {link.label}
              </Link>
            );
          })}
        </nav>
      ) : null}
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
