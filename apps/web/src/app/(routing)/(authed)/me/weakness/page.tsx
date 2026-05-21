"use client";

// /me/weakness: 弱点カテゴリ Top N（R1-6）。
//   要件: docs/requirements/4-features/learning.md §弱点カテゴリ画面
//
// 設計：
//   - 認証必須。Client Component + TanStack Query で /api/me/weakness を叩く
//     （理由は /me/stats と同じ）。
//   - 抽出ルール（3 問以上 / 50% 未満 / Top 5）は Backend 側に閉じ込めてあり、
//     ここはレスポンスをそのまま並べる責務に限定する。
//   - 弱点候補が無い場合（履歴が薄いケース）は空表示を出す。
//   - 「練習する」導線は R6 以降（適応型出題）で生やすため MVP では設けない。

import { Card, CardContent } from "@/components/ui/card/card";
import { formatCategoryLabel } from "@/lib/utils/category-label";

import { useGetMyWeakness } from "./_hooks/_fetch/use-get-my-weakness/use-get-my-weakness";

const formatPercent = (n: number): string => `${(n * 100).toFixed(1)}%`;

export default function MyWeaknessPage() {
  const { weakness, isLoading, error } = useGetMyWeakness();

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-8 px-4 py-12">
      <header className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold">弱点カテゴリ</h1>
        <p className="text-sm text-muted-foreground">
          3 問以上解答していて、正答率 50% 未満のカテゴリを表示します（最大 5 件）。
        </p>
      </header>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">読み込み中…</p>
      ) : error ? (
        <p className="text-sm text-destructive">
          弱点情報を取得できませんでした。時間を置いて再度お試しください。
        </p>
      ) : weakness && weakness.weakCategories.length === 0 ? (
        <p className="rounded-lg border border-border bg-card p-6 text-sm text-muted-foreground">
          現時点で弱点と判定されたカテゴリはありません。解答数が増えると判定対象になります。
        </p>
      ) : weakness ? (
        <ul className="flex flex-col gap-3">
          {weakness.weakCategories.map((row) => (
            <li key={row.category}>
              <Card>
                <CardContent className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 py-4 text-sm">
                  <span className="font-semibold">{formatCategoryLabel(row.category)}</span>
                  <div className="flex flex-wrap gap-x-6 gap-y-1 text-muted-foreground">
                    <span>
                      解答数 <span className="font-semibold text-foreground">{row.attempts}</span>
                    </span>
                    <span>
                      正解数 <span className="font-semibold text-foreground">{row.correct}</span>
                    </span>
                    <span>
                      正答率{" "}
                      <span className="font-semibold text-destructive">
                        {formatPercent(row.accuracy)}
                      </span>
                    </span>
                  </div>
                </CardContent>
              </Card>
            </li>
          ))}
        </ul>
      ) : null}
    </main>
  );
}
