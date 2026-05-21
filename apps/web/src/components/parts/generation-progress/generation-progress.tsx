"use client";

// GenerationProgress: 問題生成の進行ステップを 4 段で可視化する部品。
//
//   ステップは Worker (apps/workers/grading/internal/grading/problem_generate.go の
//   Handle) と 1:1：
//     1. llm_generating     - AI が問題を作成中
//     2. sandbox_verifying  - 模範解答を実行検証中
//     3. judging            - 品質をチェック中
//     4. persisting         - 結果を保存中
//
//   現在ステップ＝色付き丸、完了済＝チェックマーク、未着手＝薄色丸。
//   currentStep=null は「キュー待ち（Worker 未着手）」扱いで全段未着手表示。
//
//   variant:
//     - "full"     : 全ステップを並べてラベル付き（生成ステータス画面用）
//     - "compact"  : 横並びの小さい丸 + ラベル 1 行（生成履歴一覧用）

import type { GenerationRequestSummary } from "@/__generated__/api/types.gen";
import { cn } from "@/lib/utils";

// ProgressStep: API レスポンスから NonNullable で導出。
//   Hey API は Pydantic の Literal を top-level 型として export せず、フィールド側に
//   inline 展開するため、フィールド型から逆算する形で 1 つの enum に揃える。
//   FailureReasonTag (page.tsx) と同じパターン。
export type ProgressStep = NonNullable<GenerationRequestSummary["progressStep"]>;

// STEPS: 表示順。Worker の Handle の実行順序と一致させる。
const STEPS: { value: ProgressStep; label: string; longLabel: string }[] = [
  { value: "llm_generating", label: "AI 作成", longLabel: "AI が問題を作成中" },
  { value: "sandbox_verifying", label: "動作検証", longLabel: "模範解答を実行して検証中" },
  { value: "judging", label: "品質チェック", longLabel: "AI が問題の品質を評価中" },
  { value: "persisting", label: "保存", longLabel: "結果を保存中" },
];

// 現在ステップの index を返す。null（未着手 = キュー待ち）は -1。
const indexOf = (step: ProgressStep | null | undefined): number => {
  if (!step) return -1;
  return STEPS.findIndex((s) => s.value === step);
};

type GenerationProgressProps = {
  currentStep: ProgressStep | null | undefined;
  variant?: "full" | "compact";
  className?: string;
};

export const GenerationProgress = ({
  currentStep,
  variant = "full",
  className,
}: GenerationProgressProps) => {
  const currentIdx = indexOf(currentStep);

  if (variant === "compact") {
    // 履歴一覧の 1 行に収める：4 つの小さい丸 + 現在ステップのラベル。
    const current = currentIdx >= 0 ? STEPS[currentIdx] : null;
    return (
      <span className={cn("inline-flex items-center gap-2", className)}>
        <span aria-hidden="true" className="flex items-center gap-1">
          {STEPS.map((step, idx) => (
            <span
              key={step.value}
              className={cn(
                "h-2 w-2 rounded-full",
                idx < currentIdx && "bg-primary",
                idx === currentIdx && "animate-pulse bg-amber-500",
                idx > currentIdx && "bg-muted",
              )}
            />
          ))}
        </span>
        <span className="text-xs text-muted-foreground">
          {current ? current.longLabel : "キュー待ち"}
        </span>
      </span>
    );
  }

  // full: ステータス画面のメイン表示。縦並びで進行が見やすい。
  return (
    <ol className={cn("flex flex-col gap-2", className)}>
      {STEPS.map((step, idx) => {
        const state = idx < currentIdx ? "done" : idx === currentIdx ? "current" : "pending";
        return (
          <li key={step.value} className="flex items-center gap-3 text-sm">
            <span
              aria-hidden="true"
              className={cn(
                "flex h-6 w-6 items-center justify-center rounded-full border text-xs",
                state === "done" && "border-primary bg-primary/10 text-primary",
                state === "current" &&
                  "animate-pulse border-amber-500 bg-amber-500/10 text-amber-600",
                state === "pending" && "border-border text-muted-foreground",
              )}
            >
              {state === "done" ? "✓" : idx + 1}
            </span>
            <span
              className={cn(
                state === "current" && "font-semibold",
                state === "pending" && "text-muted-foreground",
              )}
            >
              {step.longLabel}
            </span>
          </li>
        );
      })}
    </ol>
  );
};
