// /problems/:id: 問題詳細・解答画面（R1-4、R1-6 で認証必須化）。
//   要件: docs/requirements/4-features/problem-display-and-answer.md §問題詳細・解答画面
//
// 設計：
//   - 本ページは Server Component。問題本文・入出力例は RSC で fetch する
//     （ADR 0042 §Decision「問題詳細の単純取得は Server Component の fetch」）。
//   - 解答入力 + 「実行」ボタンは Client Component（AnswerWorkspace）に閉じ込め、
//     props で problemId だけ渡す。
//   - **認証必須**：未ログイン時は server-side で /login?next=/problems/:id に
//     redirect する。問題一覧と同じガード方式で揃える
//     （3-cross-cutting/03-page-routing.md §2）。
//   - 存在しない / ソフトデリート済みの問題は API が 404 を返し、本ページは
//     notFound() で Next.js の 404 画面に倒す。

import { notFound, redirect } from "next/navigation";

import { getProblemDetailApiProblemsProblemIdGet } from "@/__generated__/api/sdk.gen";
import { ApiError, throwIfError } from "@/lib/api/api-error";
import { serverApiClient } from "@/lib/api/server-api-client";
import { hasSessionCookie } from "@/lib/auth/session-cookie";
import { PROBLEM_CATEGORY_OPTIONS } from "@/lib/constants/problem-categories";
import { PROBLEM_DIFFICULTY_OPTIONS } from "@/lib/constants/problem-difficulties";

import { AnswerWorkspace } from "./_components/answer-workspace/answer-workspace";

type ProblemDetailPageProps = {
  // Next.js 16 で page に渡る params は Promise。
  params: Promise<{ id: string }>;
};

export default async function ProblemDetailPage({ params }: ProblemDetailPageProps) {
  const { id } = await params;

  // 認証ガード：session_id Cookie が無ければ /login?next=/problems/:id に飛ばす。
  //   Cookie 検証は Backend が SSoT のため、ここでは presence チェックに留める。
  //   問題一覧と同じ server-side redirect 方式で揃える
  //   （3-cross-cutting/03-page-routing.md §2）。
  if (!(await hasSessionCookie())) {
    redirect(`/login?next=${encodeURIComponent(`/problems/${id}`)}`);
  }

  // 不正な UUID は API 側で 422 が返るが、UI 上は単に「見つかりません」で
  // 統一した方が情報量が少なくて UX が安定するため、ここで 404 に倒す。
  // UUID 形式の簡易チェック（厳密でなくてよい、Backend が SSoT）。
  const looksLikeUuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id);
  if (!looksLikeUuid) {
    notFound();
  }

  let problem: Awaited<ReturnType<typeof getProblemDetailApiProblemsProblemIdGet<true>>>["data"];
  try {
    problem = await throwIfError(
      getProblemDetailApiProblemsProblemIdGet({
        client: serverApiClient,
        path: { problem_id: id },
      }),
    );
  } catch (e) {
    // 404 は notFound() で Next.js デフォルト 404 画面に倒す。
    // それ以外（500 / 通信障害）は再 throw して Next.js の error boundary に任せる。
    if (e instanceof ApiError && e.status === 404) {
      notFound();
    }
    throw e;
  }

  const categoryLabel =
    PROBLEM_CATEGORY_OPTIONS.find((o) => o.value === problem.category)?.label ?? problem.category;
  const difficultyLabel =
    PROBLEM_DIFFICULTY_OPTIONS.find((o) => o.value === problem.difficulty)?.label ??
    problem.difficulty;

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-8 px-4 py-12">
      <header className="flex flex-col gap-3">
        <h1 className="text-2xl font-semibold">{problem.title}</h1>
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <span className="rounded-md border border-border px-2 py-0.5">{categoryLabel}</span>
          <span className="rounded-md border border-border px-2 py-0.5">{difficultyLabel}</span>
        </div>
      </header>

      <section
        aria-label="問題文"
        className="rounded-xl border border-border bg-card p-6 text-sm leading-relaxed whitespace-pre-wrap"
      >
        {problem.description}
      </section>

      <section aria-label="入出力例" className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold">入出力例</h2>
        <ul className="flex flex-col gap-3">
          {problem.examples.map((ex, i) => (
            // examples は順序付きの公開サンプル。配列順を index で識別して問題ない
            // （並び替え・追加削除が起きない静的データ）。
            // biome-ignore lint/suspicious/noArrayIndexKey: 静的な入出力例で並び替えが起きない
            <li key={i} className="rounded-lg border border-border bg-card p-4">
              <div className="grid grid-cols-1 gap-3 text-xs md:grid-cols-2">
                <div>
                  <p className="font-semibold text-muted-foreground">入力</p>
                  <pre className="mt-1 rounded-md bg-muted/40 p-2 font-mono">{ex.input}</pre>
                </div>
                <div>
                  <p className="font-semibold text-muted-foreground">出力</p>
                  <pre className="mt-1 rounded-md bg-muted/40 p-2 font-mono">{ex.output}</pre>
                </div>
              </div>
            </li>
          ))}
        </ul>
      </section>

      <AnswerWorkspace problemId={problem.id} />
    </main>
  );
}
