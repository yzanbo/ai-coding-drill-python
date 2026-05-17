"use client";

// /login: GitHub OAuth フローの入口画面。
//   要件: docs/requirements/4-features/authentication.md §2.2 ログイン画面
//   - 「GitHub でログイン」ボタン → /auth/github?next=... へ遷移（API への rewrite 経由）
//   - 認証済みなら自動的にホーム（または ?next=）へリダイレクト（二重ログイン動線を消す）
//   - URL の ?auth_error= をトーストで通知（state_invalid / oauth_canceled / oauth_failed）
//   - ?next= は同一オリジン相対パスのみ許容（safeNextPath が外部 URL を弾く）
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useRef } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card/card";
import { useGetAuthMe } from "@/hooks/use-get-auth-me/use-get-auth-me";
import { safeNextPath } from "@/lib/utils/safe-next-path";

// AUTH_ERROR_MESSAGES: API が ?auth_error=<kind> で返してくる種別ごとの文言。
//   未知の種別は汎用メッセージにフォールバックする。
const AUTH_ERROR_MESSAGES: Record<string, string> = {
  state_invalid: "認証セッションが無効でした。お手数ですがもう一度ログインしてください。",
  oauth_canceled: "ログインをキャンセルしました。もう一度お試しください。",
  oauth_failed: "GitHub との通信に失敗しました。少し時間を置いて再度お試しください。",
};

// LoginPageInner: useSearchParams を使う本体。Next.js は static prerender の時
//   この hook が解決するまで Suspense でフォールバックさせる必要があるため、
//   default export 側で Suspense にラップする。
const LoginPageInner = () => {
  const router = useRouter();
  const search = useSearchParams();
  const { isAuthenticated, isLoading } = useGetAuthMe();

  // next: 戻り先。外部 URL 等は safeNextPath で弾いて "/" にフォールバック。
  const nextPath = useMemo(() => safeNextPath(search.get("next")), [search]);

  // ?auth_error= が付いていたらトーストで通知（1 度だけ）。
  const toastedKey = useRef<string | null>(null);
  useEffect(() => {
    const kind = search.get("auth_error");
    if (!kind || toastedKey.current === kind) return;
    toastedKey.current = kind;
    toast.error(AUTH_ERROR_MESSAGES[kind] ?? "ログインに失敗しました。もう一度お試しください。");
  }, [search]);

  // 認証済みなら /login に居座らせない → next（既定 "/"）に飛ばす。
  useEffect(() => {
    if (!isLoading && isAuthenticated) {
      router.replace(nextPath);
    }
  }, [isAuthenticated, isLoading, nextPath, router]);

  // OAuth 開始 URL。next を ?next= で渡すと、callback 後にそこへ戻る。
  const startUrl = `/auth/github?next=${encodeURIComponent(nextPath)}`;

  return (
    <main className="flex flex-1 items-center justify-center px-4 py-16">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>ログイン</CardTitle>
          <CardDescription>GitHub アカウントでログインしてください。</CardDescription>
        </CardHeader>
        <CardContent>
          <Button asChild size="lg" className="w-full">
            <a href={startUrl}>GitHub でログイン</a>
          </Button>
        </CardContent>
      </Card>
    </main>
  );
};

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginPageInner />
    </Suspense>
  );
}
