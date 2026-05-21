"use client";

// /me/history: 自分の解答履歴一覧（R1-6）。
//   要件: docs/requirements/4-features/learning.md §学習履歴一覧画面
//
// 設計：
//   - 認証必須。Client Component + TanStack Query で GET /api/submissions?page=N を叩く
//     （Cookie が必要なため RSC 経路は使えない）。
//   - URL ?page= でページ番号を表現する（/problems と同じパターン）。
//   - ページ番号は Client 側の useSearchParams で取得。範囲外（totalPages 超）は
//     ボタン disable で防ぐ。
//   - 行クリックで対応する問題詳細（/problems/:id）へ遷移する（要件の主要インタラクション）。
//
// 状態表記（grading.md §JSON 例 #get-submissions と整合）：
//   - status='graded' + score / totalCount → "X / Y 通過"
//   - status='pending' → "採点中"
//   - status='failed'  → "失敗"（インフラ起因の採点失敗）

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo } from "react";

import type { SubmissionStatus, SubmissionSummary } from "@/__generated__/api/types.gen";
import { Button } from "@/components/ui/button/button";
import { Card, CardContent } from "@/components/ui/card/card";

import { useGetMySubmissions } from "./_hooks/_fetch/use-get-my-submissions/use-get-my-submissions";

// parsePage: ?page= をパース。数値以外 / 0 以下は 1 にフォールバック。
const parsePage = (raw: string | null): number => {
  if (!raw) return 1;
  const n = Number(raw);
  if (!Number.isFinite(n) || n < 1 || !Number.isInteger(n)) return 1;
  return n;
};

// formatStatus: 採点状態 + スコアを UI 用文字列に整形する。
//   pending / failed は score / totalCount が NULL のため別表記にする。
const formatStatus = (sub: SubmissionSummary): { label: string; tone: "ok" | "ng" | "muted" } => {
  const status: SubmissionStatus = sub.status;
  if (status === "graded") {
    const total = sub.totalCount ?? 0;
    const passed = sub.score ?? 0;
    // 全テスト通過なら "正解"、それ以外は "X / Y 通過" のフォーマット。
    if (total > 0 && passed === total) {
      return { label: `正解（${passed} / ${total}）`, tone: "ok" };
    }
    return { label: `${passed} / ${total} 通過`, tone: "ng" };
  }
  if (status === "failed") return { label: "失敗", tone: "ng" };
  return { label: "採点中", tone: "muted" };
};

// formatDate: ISO 文字列を "YYYY/MM/DD HH:mm" に整形（ローカルタイムゾーン）。
//   履歴一覧の縦並びで読みやすい固定桁表記にする。
const formatDate = (iso: string | null | undefined): string => {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  const hh = String(d.getHours()).padStart(2, "0");
  const mi = String(d.getMinutes()).padStart(2, "0");
  return `${yyyy}/${mm}/${dd} ${hh}:${mi}`;
};

const buildHref = (page: number): string =>
  page === 1 ? "/me/history" : `/me/history?page=${page}`;

export default function MyHistoryPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const page = useMemo(() => parsePage(searchParams.get("page")), [searchParams]);

  const { submissions, isLoading, error } = useGetMySubmissions(page);

  // ?page=999 のように範囲外を踏まれた時は最終ページに寄せる（/problems と同じ挙動）。
  //   Server Component 側は redirect() で 307 を返せるが、本ページは Client Component
  //   なので useEffect + router.replace で代替する。fetch 完了後に判定するため
  //   一瞬 items=0 の表示が出る可能性はあるが、URL とユーザー認識を合わせる方を優先する。
  //   totalPages=0（履歴ゼロ）の場合は寄せ先が無いので無視（page=1 が空配列を返す）。
  useEffect(() => {
    if (!submissions) return;
    if (submissions.totalPages > 0 && page > submissions.totalPages) {
      router.replace(buildHref(submissions.totalPages));
    }
  }, [submissions, page, router]);

  const hasPrev = page > 1;
  const hasNext = submissions ? page < submissions.totalPages : false;

  return (
    <main className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-8 px-4 py-12">
      <header className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold">解答履歴</h1>
        <p className="text-sm text-muted-foreground">
          自分の解答を新しい順に表示します。同じ問題への複数回解答は、それぞれ独立した行として残ります。
        </p>
      </header>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">読み込み中…</p>
      ) : error ? (
        <p className="text-sm text-destructive">
          履歴を取得できませんでした。時間を置いて再度お試しください。
        </p>
      ) : submissions ? (
        <>
          {submissions.items.length === 0 ? (
            <p className="rounded-lg border border-border bg-card p-6 text-sm text-muted-foreground">
              まだ解答がありません。問題一覧から解いてみましょう。
            </p>
          ) : (
            <ul className="flex flex-col gap-3">
              {submissions.items.map((sub) => {
                const status = formatStatus(sub);
                return (
                  <li key={sub.id}>
                    {/* 行クリックで該当問題へ遷移（要件: §主要インタラクション）。
                        Link を使うことで Cmd+クリックの新規タブ開きと prefetch
                        が効き、screen reader にも role=link として正しく
                        伝わる。 */}
                    <Link
                      href={`/problems/${sub.problemId}`}
                      className="block w-full text-left transition-all duration-200 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-xl"
                    >
                      <Card>
                        <CardContent className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 py-4 text-sm">
                          <div className="flex flex-col gap-1">
                            <span className="font-semibold">{sub.problemTitle}</span>
                            <span className="text-xs text-muted-foreground">
                              {formatDate(sub.gradedAt)}
                            </span>
                          </div>
                          <span
                            className={
                              status.tone === "ok"
                                ? "rounded-md border border-border bg-primary/10 px-2 py-0.5 text-xs font-semibold text-primary"
                                : status.tone === "ng"
                                  ? "rounded-md border border-border bg-destructive/10 px-2 py-0.5 text-xs font-semibold text-destructive"
                                  : "rounded-md border border-border px-2 py-0.5 text-xs text-muted-foreground"
                            }
                          >
                            {status.label}
                          </span>
                        </CardContent>
                      </Card>
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}

          {submissions.totalPages > 1 ? (
            <nav className="flex items-center justify-between gap-4" aria-label="ページネーション">
              <Button asChild variant="outline" size="sm" disabled={!hasPrev}>
                {hasPrev ? (
                  <Link href={buildHref(page - 1)}>前のページ</Link>
                ) : (
                  <span aria-disabled="true">前のページ</span>
                )}
              </Button>
              <span className="text-xs text-muted-foreground">
                {page} / {submissions.totalPages}
              </span>
              <Button asChild variant="outline" size="sm" disabled={!hasNext}>
                {hasNext ? (
                  <Link href={buildHref(page + 1)}>次のページ</Link>
                ) : (
                  <span aria-disabled="true">次のページ</span>
                )}
              </Button>
            </nav>
          ) : null}
        </>
      ) : null}
    </main>
  );
}
