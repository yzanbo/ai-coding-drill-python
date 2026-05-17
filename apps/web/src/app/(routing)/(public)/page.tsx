// ランディングページ（/）。
//   認証不要。MVP の段階ではサービス概要を 1 画面で示すだけ。
//   要件: docs/requirements/1-vision/01-overview.md
import Link from "next/link";

import { Button } from "@/components/ui/button/button";

export default function LandingPage() {
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
