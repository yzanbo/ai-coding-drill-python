// /problems/generate/:requestId: 生成ステータス画面（ポーリング）。
//   - 認証必須（(authed) layout が担保）
//   - ページ本体は params から requestId を取り出して GenerationStatusView に渡すだけ
//   - 実際のポーリングと表示分岐は子の Client Component 側で行う
//   要件: docs/requirements/4-features/problem-generation.md §生成ステータス画面
//
//   Next.js 16 (App Router) の dynamic segment params は async（Promise）。await で同期化してから渡す。

import { GenerationStatusView } from "./_components/generation-status-view/generation-status-view";

type GenerationStatusPageProps = {
  params: Promise<{ requestId: string }>;
};

export default async function GenerationStatusPage({ params }: GenerationStatusPageProps) {
  const { requestId } = await params;

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-8 px-4 py-12">
      <header className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold">問題生成リクエスト</h1>
        <p className="text-sm text-muted-foreground">
          リクエスト ID: <span className="font-mono">{requestId}</span>
        </p>
      </header>
      <GenerationStatusView requestId={requestId} />
    </main>
  );
}
