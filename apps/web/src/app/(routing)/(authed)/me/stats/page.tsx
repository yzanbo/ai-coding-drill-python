"use client";

// /me/stats: 全期間の正答率 + カテゴリ別習熟度（R1-6）。
//   要件: docs/requirements/4-features/learning.md §統計画面
//
// 設計：
//   - 認証必須。/api/me/stats は Cookie 経由のセッションを使うため Client Component
//     + TanStack Query で叩く（RSC 経路の serverApiClient は credentials='omit' のため
//      認証必須エンドポイントには使えない）。
//   - 履歴ゼロでも 200 で total=0 / byCategory=[] が返る前提で、空集計の UI を出す。
//   - 数値表示は accuracy（0.0〜1.0） → "XX.X%" に整形する。

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card/card";
import { formatCategoryLabel } from "@/lib/utils/category-label";

import { useGetMyStats } from "./_hooks/_fetch/use-get-my-stats/use-get-my-stats";

// formatPercent: 0.7142 → "71.4%"。小数 1 桁固定で揺れを抑える。
const formatPercent = (n: number): string => `${(n * 100).toFixed(1)}%`;

export default function MyStatsPage() {
  const { stats, isLoading, error } = useGetMyStats();

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-8 px-4 py-12">
      <header className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold">学習統計</h1>
        <p className="text-sm text-muted-foreground">
          全期間の正答率と、カテゴリごとの習熟度です。取得時点でリアルタイム集計します。
        </p>
      </header>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">読み込み中…</p>
      ) : error ? (
        <p className="text-sm text-destructive">
          統計を取得できませんでした。時間を置いて再度お試しください。
        </p>
      ) : stats ? (
        <>
          <Card>
            <CardHeader>
              <CardTitle className="text-base font-semibold">全体</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-wrap gap-x-8 gap-y-2 text-sm">
              <div>
                <span className="text-muted-foreground">解答数：</span>
                <span className="font-semibold">{stats.total}</span>
              </div>
              <div>
                <span className="text-muted-foreground">正解数：</span>
                <span className="font-semibold">{stats.correct}</span>
              </div>
              <div>
                <span className="text-muted-foreground">正答率：</span>
                <span className="font-semibold">{formatPercent(stats.accuracy)}</span>
              </div>
            </CardContent>
          </Card>

          <section className="flex flex-col gap-3">
            <h2 className="text-lg font-semibold">カテゴリ別</h2>
            {stats.byCategory.length > 0 ? (
              <ul className="flex flex-col gap-3">
                {stats.byCategory.map((row) => (
                  <li key={row.category}>
                    <Card>
                      <CardContent className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 py-4 text-sm">
                        <span className="font-semibold">{formatCategoryLabel(row.category)}</span>
                        <div className="flex flex-wrap gap-x-6 gap-y-1 text-muted-foreground">
                          <span>
                            解答数{" "}
                            <span className="font-semibold text-foreground">{row.attempts}</span>
                          </span>
                          <span>
                            正解数{" "}
                            <span className="font-semibold text-foreground">{row.correct}</span>
                          </span>
                          <span>
                            正答率{" "}
                            <span className="font-semibold text-foreground">
                              {formatPercent(row.accuracy)}
                            </span>
                          </span>
                        </div>
                      </CardContent>
                    </Card>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="rounded-lg border border-border bg-card p-6 text-sm text-muted-foreground">
                まだ採点された解答がありません。まずは問題を解いてみましょう。
              </p>
            )}
          </section>
        </>
      ) : null}
    </main>
  );
}
