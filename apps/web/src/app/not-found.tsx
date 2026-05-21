"use client";

// not-found: 全 404 を共通でハンドリングする App Router の規約ファイル。
//   挙動：
//     - ログイン済み → /problems にリダイレクト
//     - 未ログイン   → / にリダイレクト（/ も /problems に最終的に飛ぶが、
//                     未認証導線（/）を経由しておくと、将来 / で認証チェック /
//                     ランディング表示等を再導入した時に整合が取れる）
//   理由：
//     - 主動線が /problems に集約されているため、不存在パスから無関係な
//       Next.js 既定 404 を出すより、機能ページに引き戻す方が UX が良い
//     - 認証状態の判定は useGetAuthMe（既存 (authed) layout と同じ）に揃え、
//       初回フェッチが完了するまで何も出さない（チラ見せ回避）

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useGetAuthMe } from "@/hooks/use-get-auth-me/use-get-auth-me";

export default function NotFound() {
  const router = useRouter();
  const { isAuthenticated, isUnauthenticated, isLoading } = useGetAuthMe();

  useEffect(() => {
    // 判定中はリダイレクトしない（古い状態で誤誘導しない）。
    if (isLoading) return;
    if (isAuthenticated) {
      router.replace("/problems");
    } else if (isUnauthenticated) {
      router.replace("/");
    }
    // isAuthenticated / isUnauthenticated のどちらにも倒れない（5xx + キャッシュ無し）
    // ケースは、useGetAuthMe の仕様上稀。次の再評価で再度ここに来た時に処理される。
  }, [isAuthenticated, isUnauthenticated, isLoading, router]);

  // リダイレクトが走るまでの間は空表示（チラ見せ回避）。
  return null;
}
