// /problems: 問題一覧画面（ゲスト閲覧可、R1-4）。
//   要件: docs/requirements/4-features/problem-display-and-answer.md §問題一覧画面
//
// 設計：
//   - 本ページは Server Component（RSC）として fetch を直接呼ぶ
//     （ADR 0042 §Decision の「問題一覧・問題詳細の単純取得は Server Component
//     の fetch で行う」方針）。
//   - フィルタ UI のみ Client Component（URL クエリを書き換えるためにナビゲートが必要）。
//     リンク遷移で本ページが再 render され、再 fetch される。
//   - 認証不要（ゲストでも 401 にならず一覧が返る、Backend 側で /api/problems を
//     CurrentUser に依存させていない）。
//
// route group：
//   (public) 配下に置く。(authed)/problems/new と (authed)/problems/generate/:requestId は
//   既存だが、URL は /problems/new / /problems/generate/:requestId で literal segment
//   先勝ちのため、本ページの /problems/[id] とは衝突しない（Next.js のルーティング
//   優先度：static > dynamic）。

import Link from "next/link";
import { listProblemsApiProblemsGet } from "@/__generated__/api/sdk.gen";
import type { ProblemCategory, ProblemDifficulty } from "@/__generated__/api/types.gen";
import { Button } from "@/components/ui/button/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card/card";
import { throwIfError } from "@/lib/api/api-error";
import { serverApiClient } from "@/lib/api/server-api-client";
import { PROBLEM_CATEGORY_OPTIONS } from "@/lib/constants/problem-categories";
import { PROBLEM_DIFFICULTY_OPTIONS } from "@/lib/constants/problem-difficulties";

import { ProblemsFilterForm } from "./_components/problems-filter-form/problems-filter-form";

// SearchParams: Next.js 16 で page に渡る searchParams は Promise 型。
//   問題一覧で扱うのは category / difficulty / page の 3 種類のみ。
type SearchParams = Promise<{
  category?: string;
  difficulty?: string;
  page?: string;
}>;

type ProblemsPageProps = {
  searchParams: SearchParams;
};

// 許可値の機械チェック：API 側 Enum と表示用 OPTIONS を照合する。
//   不正な値が URL に書かれていたら無視（フィルタ未指定として扱う）。
const VALID_CATEGORIES = new Set<ProblemCategory>(PROBLEM_CATEGORY_OPTIONS.map((o) => o.value));
const VALID_DIFFICULTIES = new Set<ProblemDifficulty>(
  PROBLEM_DIFFICULTY_OPTIONS.map((o) => o.value),
);

function parseCategory(raw: string | undefined): ProblemCategory | undefined {
  if (raw && (VALID_CATEGORIES as Set<string>).has(raw)) {
    return raw as ProblemCategory;
  }
  return undefined;
}

function parseDifficulty(raw: string | undefined): ProblemDifficulty | undefined {
  if (raw && (VALID_DIFFICULTIES as Set<string>).has(raw)) {
    return raw as ProblemDifficulty;
  }
  return undefined;
}

function parsePage(raw: string | undefined): number {
  const n = Number(raw);
  // 数値以外 / 0 以下 / 小数は 1 にフォールバック（Backend に 422 を投げない）。
  if (!Number.isFinite(n) || n < 1 || !Number.isInteger(n)) return 1;
  return n;
}

// buildHref: フィルタ + ページ番号から URL クエリ文字列を組み立てる。
//   ページネーションのリンク（前 / 次）で使う。
function buildHref(
  category: ProblemCategory | undefined,
  difficulty: ProblemDifficulty | undefined,
  page: number,
): string {
  const params = new URLSearchParams();
  if (category) params.set("category", category);
  if (difficulty) params.set("difficulty", difficulty);
  if (page !== 1) params.set("page", String(page));
  const qs = params.toString();
  return qs ? `/problems?${qs}` : "/problems";
}

export default async function ProblemsListPage({ searchParams }: ProblemsPageProps) {
  const sp = await searchParams;
  const category = parseCategory(sp.category);
  const difficulty = parseDifficulty(sp.difficulty);
  const page = parsePage(sp.page);

  // Backend を直接 fetch（serverApiClient は絶対 URL ベース）。
  //   throwIfError は ApiError を投げるが、本ページは error boundary で拾う想定
  //   （MVP では error.tsx を置かないので Next.js デフォルト error 画面に倒れる）。
  const data = await throwIfError(
    listProblemsApiProblemsGet({
      client: serverApiClient,
      query: { category, difficulty, page },
    }),
  );

  const hasPrev = page > 1;
  const hasNext = page < data.totalPages;

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-8 px-4 py-12">
      <header className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold">問題一覧</h1>
        <p className="text-sm text-muted-foreground">
          解いてみたい問題をカテゴリ・難易度で絞り込めます。ゲストでも閲覧できますが、
          解答送信にはログインが必要です。
        </p>
      </header>

      <ProblemsFilterForm category={category} difficulty={difficulty} />

      {data.items.length === 0 ? (
        <p className="rounded-lg border border-border bg-card p-6 text-sm text-muted-foreground">
          条件に合う問題が見つかりませんでした。フィルタを外すか、別のカテゴリを試してください。
        </p>
      ) : (
        <ul className="flex flex-col gap-4">
          {data.items.map((problem) => (
            <li key={problem.id}>
              <Link
                href={`/problems/${problem.id}`}
                className="block transition-all duration-200 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-xl"
              >
                <Card>
                  <CardHeader>
                    <CardTitle className="text-base font-semibold">{problem.title}</CardTitle>
                  </CardHeader>
                  <CardContent className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                    <span className="rounded-md border border-border px-2 py-0.5">
                      {PROBLEM_CATEGORY_OPTIONS.find((o) => o.value === problem.category)?.label ??
                        problem.category}
                    </span>
                    <span className="rounded-md border border-border px-2 py-0.5">
                      {PROBLEM_DIFFICULTY_OPTIONS.find((o) => o.value === problem.difficulty)
                        ?.label ?? problem.difficulty}
                    </span>
                  </CardContent>
                </Card>
              </Link>
            </li>
          ))}
        </ul>
      )}

      {data.totalPages > 1 ? (
        <nav className="flex items-center justify-between gap-4" aria-label="ページネーション">
          <Button asChild variant="outline" size="sm" disabled={!hasPrev}>
            {hasPrev ? (
              <Link href={buildHref(category, difficulty, page - 1)}>前のページ</Link>
            ) : (
              <span aria-disabled="true">前のページ</span>
            )}
          </Button>
          <span className="text-xs text-muted-foreground">
            {page} / {data.totalPages}
          </span>
          <Button asChild variant="outline" size="sm" disabled={!hasNext}>
            {hasNext ? (
              <Link href={buildHref(category, difficulty, page + 1)}>次のページ</Link>
            ) : (
              <span aria-disabled="true">次のページ</span>
            )}
          </Button>
        </nav>
      ) : null}
    </main>
  );
}
