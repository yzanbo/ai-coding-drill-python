"use client";

// /me/generations: 自分の問題生成リクエスト履歴（R1-7）。
//   要件: docs/requirements/4-features/problem-generation.md §生成履歴画面
//
// 設計：
//   - 認証必須。Client Component + TanStack Query で /api/me/generations を 1 秒ポーリング
//   - 全件終端なら停止、タブ非アクティブで停止
//   - 行クリックの遷移は状態別（completed → /problems/:id、pending/running →
//     /problems/generate/:requestId、failed/canceled は遷移なし + インライン表示）
//   - キャンセル / 再試行ボタンは pending / failed の行にのみ表示

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo } from "react";

import type { GenerationRequestSummary } from "@/__generated__/api/types.gen";
import { Button } from "@/components/ui/button/button";
import { Card, CardContent } from "@/components/ui/card/card";
import { formatCategoryLabel } from "@/lib/utils/category-label";

import { useCancelMyGeneration } from "./_hooks/_fetch/use-cancel-my-generation/use-cancel-my-generation";
import { useGetMyGenerations } from "./_hooks/_fetch/use-get-my-generations/use-get-my-generations";
import { useRetryMyGeneration } from "./_hooks/_fetch/use-retry-my-generation/use-retry-my-generation";

// parsePage: ?page= をパース。数値以外 / 0 以下は 1 にフォールバック。
const parsePage = (raw: string | null): number => {
  if (!raw) return 1;
  const n = Number(raw);
  if (!Number.isFinite(n) || n < 1 || !Number.isInteger(n)) return 1;
  return n;
};

const buildHref = (page: number): string =>
  page === 1 ? "/me/generations" : `/me/generations?page=${page}`;

// formatDate: ISO → "YYYY/MM/DD HH:mm"。
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

// formatDuration: 経過時間（ms）を「12 秒」「3 分 5 秒」表記に丸める。
const formatDuration = (createdAt: string, completedAt: string | null | undefined): string => {
  const start = new Date(createdAt).getTime();
  const end = completedAt ? new Date(completedAt).getTime() : Date.now();
  if (!Number.isFinite(start) || !Number.isFinite(end)) return "—";
  const sec = Math.max(0, Math.floor((end - start) / 1000));
  if (sec < 60) return `${sec} 秒`;
  return `${Math.floor(sec / 60)} 分 ${sec % 60} 秒`;
};

// STATUS_LABEL: 状態文字列 → 表示ラベル + 色トーン。
const STATUS_LABEL: Record<
  GenerationRequestSummary["status"],
  { label: string; tone: "ok" | "ng" | "muted" | "warn" }
> = {
  pending: { label: "生成中…", tone: "warn" },
  completed: { label: "成功", tone: "ok" },
  failed: { label: "失敗", tone: "ng" },
  canceled: { label: "キャンセル済", tone: "muted" },
};

const TONE_CLASS = {
  ok: "rounded-md border border-border bg-primary/10 px-2 py-0.5 text-xs font-semibold text-primary",
  ng: "rounded-md border border-border bg-destructive/10 px-2 py-0.5 text-xs font-semibold text-destructive",
  warn: "rounded-md border border-border bg-amber-500/10 px-2 py-0.5 text-xs font-semibold text-amber-600",
  muted: "rounded-md border border-border px-2 py-0.5 text-xs text-muted-foreground",
} as const;

export default function MyGenerationsPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const page = useMemo(() => parsePage(searchParams.get("page")), [searchParams]);

  const { generations, isLoading, error } = useGetMyGenerations(page);
  const cancelMutation = useCancelMyGeneration();
  const retryMutation = useRetryMyGeneration();

  // 範囲外 page は最終ページに寄せる（/me/history と同じ挙動、UX 一貫性）。
  useEffect(() => {
    if (!generations) return;
    if (generations.totalPages > 0 && page > generations.totalPages) {
      router.replace(buildHref(generations.totalPages));
    }
  }, [generations, page, router]);

  const hasPrev = page > 1;
  const hasNext = generations ? page < generations.totalPages : false;

  return (
    <main className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-8 px-4 py-12">
      <header className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold">生成履歴</h1>
        <p className="text-sm text-muted-foreground">
          自分が発行した問題生成リクエストを新しい順に表示します。生成中の行は 1 秒間隔で
          自動更新されます（タブを離れている間は更新を停止します）。
        </p>
      </header>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">読み込み中…</p>
      ) : error ? (
        <p className="text-sm text-destructive">
          履歴を取得できませんでした。時間を置いて再度お試しください。
        </p>
      ) : generations ? (
        <>
          {generations.items.length === 0 ? (
            <p className="rounded-lg border border-border bg-card p-6 text-sm text-muted-foreground">
              まだ生成リクエストがありません。問題一覧から新規問題を生成してみましょう。
            </p>
          ) : (
            <ul className="flex flex-col gap-3">
              {generations.items.map((item) => (
                <GenerationRow
                  key={item.id}
                  item={item}
                  onCancel={(id) => cancelMutation.cancel(id)}
                  onRetry={(id) => retryMutation.retry(id)}
                  isCancelPending={cancelMutation.isPending}
                  isRetryPending={retryMutation.isPending}
                />
              ))}
            </ul>
          )}

          {generations.totalPages > 1 ? (
            <nav className="flex items-center justify-between gap-4" aria-label="ページネーション">
              <Button asChild variant="outline" size="sm" disabled={!hasPrev}>
                {hasPrev ? (
                  <Link href={buildHref(page - 1)}>前のページ</Link>
                ) : (
                  <span aria-disabled="true">前のページ</span>
                )}
              </Button>
              <span className="text-xs text-muted-foreground">
                {page} / {generations.totalPages}
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

type GenerationRowProps = {
  item: GenerationRequestSummary;
  onCancel: (id: string) => Promise<unknown>;
  onRetry: (id: string) => Promise<unknown>;
  isCancelPending: boolean;
  isRetryPending: boolean;
};

// GenerationRow: 1 行の表示 + アクションボタン。
//   行クリックの遷移先は状態別に分岐：
//     - completed: /problems/:id（生成された問題本体）
//     - pending: /problems/generate/:requestId（ステータス画面）
//     - failed / canceled: 遷移なし（行内に失敗理由 / キャンセル済を表示）
const GenerationRow = ({
  item,
  onCancel,
  onRetry,
  isCancelPending,
  isRetryPending,
}: GenerationRowProps) => {
  const status = STATUS_LABEL[item.status];
  const linkHref = ((): string | null => {
    if (item.status === "completed" && item.producedProblemId) {
      return `/problems/${item.producedProblemId}`;
    }
    if (item.status === "pending") {
      return `/problems/generate/${item.id}`;
    }
    return null;
  })();

  const inner = (
    <Card>
      <CardContent className="flex flex-wrap items-start justify-between gap-x-6 gap-y-2 py-4 text-sm">
        <div className="flex flex-col gap-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-semibold">{formatCategoryLabel(item.category)}</span>
            <span className="rounded-md border border-border px-2 py-0.5 text-xs text-muted-foreground">
              {item.difficulty}
            </span>
            <span className={TONE_CLASS[status.tone]}>{status.label}</span>
            {item.retryCount > 0 ? (
              <span className="rounded-md border border-border px-2 py-0.5 text-xs text-muted-foreground">
                再試行 {item.retryCount} 回目
              </span>
            ) : null}
            {item.promptVersion ? (
              <span className="rounded-md border border-border px-2 py-0.5 text-xs text-muted-foreground">
                prompt {item.promptVersion}
              </span>
            ) : null}
          </div>
          <span className="text-xs text-muted-foreground">
            {formatDate(item.createdAt)} ／ 所要 {formatDuration(item.createdAt, item.completedAt)}
          </span>
          {item.status === "failed" && item.failureReason ? (
            <span className="text-xs text-destructive">失敗理由: {item.failureReason}</span>
          ) : null}
        </div>
        <div className="flex items-center gap-2">
          {item.status === "pending" ? (
            <Button
              size="sm"
              variant="outline"
              disabled={isCancelPending}
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                void onCancel(item.id);
              }}
            >
              キャンセル
            </Button>
          ) : null}
          {item.status === "failed" ? (
            <Button
              size="sm"
              disabled={isRetryPending}
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                void onRetry(item.id);
              }}
            >
              再試行
            </Button>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );

  return (
    <li>
      {linkHref ? (
        <Link
          href={linkHref}
          className="block w-full text-left transition-all duration-200 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-xl"
        >
          {inner}
        </Link>
      ) : (
        inner
      )}
    </li>
  );
};
