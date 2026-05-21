// /problems: 問題一覧画面（R1-4、R1-6 で認証必須化）。
//   要件: docs/requirements/4-features/problem-display-and-answer.md §問題一覧画面
//
// 設計：
//   - 本ページは Server Component（RSC）として fetch を直接呼ぶ
//     （ADR 0042 §Decision の「問題一覧・問題詳細の単純取得は Server Component
//     の fetch で行う」方針）。
//   - フィルタ UI のみ Client Component（URL クエリを書き換えるためにナビゲートが必要）。
//     リンク遷移で本ページが再 render され、再 fetch される。
//   - **認証必須**：未ログイン時は server-side で /login?next=/problems に redirect。
//     SSoT は Backend の Depends(get_current_user)、本判定は UX 用ガード
//     （3-cross-cutting/03-page-routing.md §2 の server-side cookie + redirect()
//      パターン）。
//   - 表示は「カテゴリ別アコーディオン（初期は全て閉じる）+ 難易度昇順」。
//     ページネーションは廃止し、大きい page_size で 1 回 fetch する全件取得方式。

import Link from "next/link";
import { redirect } from "next/navigation";
import { listProblemsApiProblemsGet } from "@/__generated__/api/sdk.gen";
import type {
  ProblemCategory,
  ProblemDifficulty,
  ProblemSummaryResponse,
} from "@/__generated__/api/types.gen";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion/accordion";
import { Button } from "@/components/ui/button/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card/card";
import { throwIfError } from "@/lib/api/api-error";
import { serverApiClient } from "@/lib/api/server-api-client";
import { hasSessionCookie } from "@/lib/auth/session-cookie";
import { PROBLEM_CATEGORY_OPTIONS } from "@/lib/constants/problem-categories";
import { PROBLEM_DIFFICULTY_OPTIONS } from "@/lib/constants/problem-difficulties";
import { formatDifficultyLabel } from "@/lib/utils/difficulty-label";

import { ProblemsFilterForm } from "./_components/problems-filter-form/problems-filter-form";

// SearchParams: Next.js 16 で page に渡る searchParams は Promise 型。
//   問題一覧で扱うのは category / difficulty の 2 種類のみ
//   （ページネーション撤去のため page は使わない）。
type SearchParams = Promise<{
  category?: string;
  difficulty?: string;
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

// DIFFICULTY_RANK: 難易度の並び順（easy=0, medium=1, hard=2）。
//   カテゴリ枠内でソートする時の比較キーに使う。
const DIFFICULTY_RANK: Record<ProblemDifficulty, number> = Object.fromEntries(
  PROBLEM_DIFFICULTY_OPTIONS.map((o, i) => [o.value, i]),
) as Record<ProblemDifficulty, number>;

// ALL_FETCH_PAGE_SIZE: 全件取得のために渡す page_size。
//   Backend 側に上限は無く（routers/problems.py）、MVP 規模では 1000 で十分。
//   将来この数を超えたら戦略を見直す（YAGNI、CLAUDE.md §設計原則）。
const ALL_FETCH_PAGE_SIZE = 1000;

export default async function ProblemsListPage({ searchParams }: ProblemsPageProps) {
  // 認証ガード：session_id Cookie が無ければ /login?next=/problems に飛ばす。
  //   フィルタを保持して戻したいので、現在の URL（クエリ含む）を組み立てて next に渡す。
  const isLoggedIn = await hasSessionCookie();
  const sp = await searchParams;
  if (!isLoggedIn) {
    const nextParams = new URLSearchParams();
    if (typeof sp.category === "string") nextParams.set("category", sp.category);
    if (typeof sp.difficulty === "string") nextParams.set("difficulty", sp.difficulty);
    const qs = nextParams.toString();
    const nextUrl = qs ? `/problems?${qs}` : "/problems";
    redirect(`/login?next=${encodeURIComponent(nextUrl)}`);
  }

  const category =
    sp.category && (VALID_CATEGORIES as Set<string>).has(sp.category)
      ? (sp.category as ProblemCategory)
      : undefined;
  const difficulty =
    sp.difficulty && (VALID_DIFFICULTIES as Set<string>).has(sp.difficulty)
      ? (sp.difficulty as ProblemDifficulty)
      : undefined;

  // 全件取得。page_size を大きくして 1 回の fetch で全部取る。
  const data = await throwIfError(
    listProblemsApiProblemsGet({
      client: serverApiClient,
      query: { category, difficulty, page: 1, page_size: ALL_FETCH_PAGE_SIZE },
    }),
  );

  // カテゴリ別にグルーピング。category フィルタが効いている時は該当 1 つだけが出る。
  //   キーは PROBLEM_CATEGORY_OPTIONS の順（string / array / recursion / async / type-puzzle）。
  const grouped = new Map<ProblemCategory, ProblemSummaryResponse[]>();
  for (const item of data.items) {
    const list = grouped.get(item.category) ?? [];
    list.push(item);
    grouped.set(item.category, list);
  }
  // 各グループ内を難易度昇順（easy → medium → hard）にソート。
  //   tie-break は title（同じ難易度内は名前順）。
  for (const list of grouped.values()) {
    list.sort((a, b) => {
      const r = DIFFICULTY_RANK[a.difficulty] - DIFFICULTY_RANK[b.difficulty];
      return r !== 0 ? r : a.title.localeCompare(b.title, "ja");
    });
  }

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-8 px-4 py-12">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex flex-col gap-2">
          <h1 className="text-2xl font-semibold">問題一覧</h1>
          <p className="text-sm text-muted-foreground">
            解いてみたい問題をカテゴリ・難易度で絞り込めます。
          </p>
        </div>
        {/* 新規問題を生成: /problems/new への主動線。 */}
        <Button asChild size="sm" className="sm:self-start">
          <Link href="/problems/new">新規問題を生成</Link>
        </Button>
      </header>

      <ProblemsFilterForm category={category} difficulty={difficulty} />

      {data.items.length === 0 ? (
        <p className="rounded-lg border border-border bg-card p-6 text-sm text-muted-foreground">
          条件に合う問題が見つかりませんでした。フィルタを外すか、別のカテゴリを試してください。
        </p>
      ) : (
        // カテゴリ別アコーディオン。
        //   type="multiple": 複数カテゴリを同時に開ける。
        //   defaultValue={[]}: 初期表示は全て閉じた状態。
        //   PROBLEM_CATEGORY_OPTIONS の順序で固定（string → array → recursion → async → type-puzzle）。
        <Accordion type="multiple" defaultValue={[]} className="flex flex-col gap-3">
          {PROBLEM_CATEGORY_OPTIONS.map((opt) => {
            const list = grouped.get(opt.value) ?? [];
            if (list.length === 0) return null;
            return (
              <AccordionItem
                key={opt.value}
                value={opt.value}
                className="rounded-xl border border-border bg-card px-4"
              >
                <AccordionTrigger className="text-base">
                  <span className="flex items-center gap-3">
                    <span className="font-semibold">{opt.label}</span>
                    <span className="text-xs text-muted-foreground">{list.length} 問</span>
                  </span>
                </AccordionTrigger>
                <AccordionContent>
                  <ul className="flex flex-col gap-3">
                    {list.map((problem) => (
                      <li key={problem.id}>
                        <Link
                          href={`/problems/${problem.id}`}
                          className="block rounded-lg transition-all duration-200 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        >
                          <Card>
                            <CardHeader>
                              <CardTitle className="text-sm font-semibold">
                                {problem.title}
                              </CardTitle>
                            </CardHeader>
                            <CardContent className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                              <span className="rounded-md border border-border px-2 py-0.5">
                                {formatDifficultyLabel(problem.difficulty)}
                              </span>
                            </CardContent>
                          </Card>
                        </Link>
                      </li>
                    ))}
                  </ul>
                </AccordionContent>
              </AccordionItem>
            );
          })}
        </Accordion>
      )}
    </main>
  );
}
