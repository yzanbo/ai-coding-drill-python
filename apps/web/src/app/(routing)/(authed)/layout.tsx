"use client";

// (authed) ルートグループ共通の layout。
//   配下の全ページに「未認証なら /login?next=<現在のpath> へリダイレクト」のガードを掛ける。
//   要件: docs/requirements/4-features/authentication.md §1.1 ビジネスルール
//
//   サーバ側ガード（middleware）にしない理由:
//     - Cookie は本機能 MVP では署名検証付きの SID で、ガード本体は API の Depends(get_current_user)
//       が握っている。FE 側は UX 用の早期リダイレクトで十分（最終判定は API の 401 が SSoT）。
//     - middleware にすると静的最適化が崩れる範囲が広がり、ルートグループ単位の細かな出し分けが
//       書きにくくなる。
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
