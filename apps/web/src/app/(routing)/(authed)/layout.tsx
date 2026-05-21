"use client";

// (authed) ルートグループ共通の layout。
//   役割：「Cookie はあるが Redis セッションが失効している」ケースを補完する
//   client-side ガード。`useGetAuthMe` が `/auth/me` 401 を見て
//   `/login?next=<現在のpath>` に倒す。
//   要件: docs/requirements/4-features/authentication.md §1.1 ビジネスルール
//
//   middleware との二段構え：
//     - 1 段目（src/middleware.ts、Edge）：Cookie が完全に無いリクエストを RSC
//       レンダリング前に弾く。`/me/*` `/problems/new` `/problems/generate/:requestId`
//       はここで先に 307 を返すため、Cookie 無しは本 layout に到達しない。
//     - 2 段目（本 layout）：Cookie はあるが失効しているケースを API 401 から
//       拾う。middleware の presence チェックでは検知できない。
//     - 詳細：docs/requirements/3-cross-cutting/03-page-routing.md §2
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { Button } from "@/components/ui/button/button";
import { useGetAuthMe } from "@/hooks/use-get-auth-me/use-get-auth-me";

type AuthedLayoutProps = {
  children: React.ReactNode;
};

export default function AuthedLayout({ children }: AuthedLayoutProps) {
  const router = useRouter();
  const pathname = usePathname();
  const { isAuthenticated, isUnauthenticated, isLoading, error } = useGetAuthMe();

  useEffect(() => {
    if (isUnauthenticated) {
      const next = pathname ? `?next=${encodeURIComponent(pathname)}` : "";
      router.replace(`/login${next}`);
    }
  }, [isUnauthenticated, pathname, router]);

  // 判定中 or 未認証（リダイレクト待ち）はチラ見せを防いで空表示にする。
  if (isLoading || isUnauthenticated) {
    return null;
  }

  // 認証 API が 500 / ネットワーク断で失敗し、かつ前回成功キャッシュも無い時の保険。
  //   useGetAuthMe はキャッシュがある場合「isAuthenticated を維持する」設計だが、
  //   初回訪問時の障害ではキャッシュが無いため isAuthenticated=false / isUnauthenticated=false の
  //   どちらにも倒れず、children を出さないと永遠に白画面になる。
  //   ここでユーザーに障害を見せて再試行できるようにする（要件: authentication.md §1.1）。
  if (error && !isAuthenticated) {
    return (
      <main className="flex flex-1 items-center justify-center px-4 py-16">
        <div className="flex max-w-sm flex-col items-center gap-3 text-center">
          <p className="text-base font-semibold">ログイン状態を確認できませんでした</p>
          <p className="text-sm text-muted-foreground">
            サーバーとの通信に失敗しました。少し時間を置いて再度お試しください。
          </p>
          <Button variant="outline" size="sm" onClick={() => router.refresh()}>
            再試行
          </Button>
        </div>
      </main>
    );
  }

  if (!isAuthenticated) {
    return null;
  }

  return <>{children}</>;
}
