"use client";

// LoginForm: /login ページの「クライアント側でしかできないこと」だけを担う部品。
//   - GitHub OAuth 開始リンクの描画（href は親から受け取った next を埋める）
//   - ?auth_error= が URL に付いていればトーストで通知し、auth_error だけ URL から除去
//
// 認証済みかどうかの判定とリダイレクトは親（page.tsx）の Server Component が
// server-side cookie + redirect() で済ませる。本コンポーネントが mount された
// 時点で「未認証ユーザー」が確定している前提。

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card/card";

// AUTH_ERROR_MESSAGES: API が ?auth_error=<kind> で返してくる種別ごとの文言。
//   未知の種別は汎用メッセージにフォールバックする。
const AUTH_ERROR_MESSAGES: Record<string, string> = {
  state_invalid: "認証セッションが無効でした。お手数ですがもう一度ログインしてください。",
  oauth_canceled: "ログインをキャンセルしました。もう一度お試しください。",
  oauth_failed: "GitHub との通信に失敗しました。少し時間を置いて再度お試しください。",
};

type LoginFormProps = {
  // nextPath: ?next= をサーバ側で safeNextPath にかけた後の安全な相対パス。
  //   GitHub OAuth 開始 URL の ?next= にそのまま流す。
  nextPath: string;
};

export const LoginForm = ({ nextPath }: LoginFormProps) => {
  const router = useRouter();
  const search = useSearchParams();
  const pathname = usePathname();
  const toastedKey = useRef<string | null>(null);

  // ?auth_error= が付いていたらトーストで通知（1 度だけ）。
  //   通知後は router.replace で URL から auth_error を取り除く。理由：
  //     - リロードや「戻る」で同じトーストが再表示されるのを防ぐ
  //     - 残った ?next= は保持したいので、search からキー単位で削るのではなく
  //       URLSearchParams を作り直して auth_error だけを除外する
  useEffect(() => {
    const kind = search.get("auth_error");
    if (!kind || toastedKey.current === kind) return;
    toastedKey.current = kind;
    toast.error(AUTH_ERROR_MESSAGES[kind] ?? "ログインに失敗しました。もう一度お試しください。");
    const cleaned = new URLSearchParams(search.toString());
    cleaned.delete("auth_error");
    const qs = cleaned.toString();
    // usePathname の戻り値は型上 null になりうる（Next.js の App Router 仕様）。
    //   本ページは /login 上で動くので null は事実上来ないが、null と
    //   テンプレ文字列を組み合わせて "null?foo=..." を作る事故を防ぐためのフォールバック。
    const base = pathname ?? "/login";
    router.replace(qs ? `${base}?${qs}` : base);
  }, [search, pathname, router]);

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
