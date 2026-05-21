// LoginRequiredMessage: 認証が必要なページで未ログイン時に表示する案内ブロック。
//   - 「ログインしてください」見出し + 補足説明 + ログイン CTA
//   - 戻り先は呼び出し側で next prop に渡す（ログイン後にここへ戻したい URL）
//
// 使い方：
//   <LoginRequiredMessage next={`/problems/${id}`} />
//
// 共有部品（複数ページで使う想定）のため components/parts/ 配下に置く
// （frontend.md §parts/ の方針：ドメイン語彙を含む再利用ブロック）。

import Link from "next/link";

import { Button } from "@/components/ui/button/button";

type LoginRequiredMessageProps = {
  // next: ログイン後の戻り先（同一オリジン相対パスのみ受け付ける）。
  //   外部 URL 拒否は Backend 側 _safe_next_path / FE 側 safe-next-path で担保。
  next?: string;
};

export const LoginRequiredMessage = ({ next }: LoginRequiredMessageProps) => {
  // ログインリンク：next= を持って /login に飛ばす。
  //   既存 (authed) layout のリダイレクトと同じ規約で、ログイン完走後に
  //   呼び出し元のパスに戻す。
  const loginHref = next ? `/login?next=${encodeURIComponent(next)}` : "/login";

  return (
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col items-center justify-center px-6 py-24 text-center">
      <h1 className="text-2xl font-semibold">ログインが必要です</h1>
      <p className="mt-4 text-sm text-muted-foreground">
        このページはログインした場合のみ閲覧できます。GitHub
        アカウントでログインしてからお戻りください。
      </p>
      <div className="mt-8">
        <Button asChild size="lg">
          <Link href={loginHref}>GitHub でログイン</Link>
        </Button>
      </div>
    </main>
  );
};
