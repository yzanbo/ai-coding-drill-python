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

import { useGetAuthMe } from "@/hooks/use-get-auth-me/use-get-auth-me";

type AuthedLayoutProps = {
  children: React.ReactNode;
};

export default function AuthedLayout({ children }: AuthedLayoutProps) {
  const router = useRouter();
  const pathname = usePathname();
  const { isAuthenticated, isUnauthenticated, isLoading } = useGetAuthMe();

  useEffect(() => {
    if (isUnauthenticated) {
      const next = pathname ? `?next=${encodeURIComponent(pathname)}` : "";
      router.replace(`/login${next}`);
    }
  }, [isUnauthenticated, pathname, router]);

  // 判定中 or 未認証（リダイレクト待ち）はチラ見せを防いで空表示にする。
  if (isLoading || !isAuthenticated) {
    return null;
  }

  return <>{children}</>;
}
