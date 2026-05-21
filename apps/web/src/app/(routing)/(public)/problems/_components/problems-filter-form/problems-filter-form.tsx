"use client";

// ProblemsFilterForm: 問題一覧ページのフィルタ UI（Client Component）。
//   URL クエリ（?category=...&difficulty=...）を SSoT として書き換える。
//   親ページは Server Component で、URL 遷移で再 render → 再 fetch される。
//
// なぜネイティブ <select> を使うか：
//   shadcn/ui の Select は未導入で、本フェーズの目的（フィルタ）には
//   ネイティブ select で十分。a11y も標準で揃う。デザインは Tailwind で揃える。

import { useRouter, useSearchParams } from "next/navigation";
import { useTransition } from "react";
import type { ProblemCategory, ProblemDifficulty } from "@/__generated__/api/types.gen";
import { Button } from "@/components/ui/button/button";
import { PROBLEM_CATEGORY_OPTIONS } from "@/lib/constants/problem-categories";
import { PROBLEM_DIFFICULTY_OPTIONS } from "@/lib/constants/problem-difficulties";

type ProblemsFilterFormProps = {
  category: ProblemCategory | undefined;
  difficulty: ProblemDifficulty | undefined;
};

// 共通スタイル：枠線・フォーカスリング・hover を他フォームと揃える。
const selectClassName =
  "rounded-md border border-border bg-card px-3 py-2 text-sm transition-colors duration-200 hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

export const ProblemsFilterForm = ({ category, difficulty }: ProblemsFilterFormProps) => {
  const router = useRouter();
  const searchParams = useSearchParams();
  // useTransition: フィルタ更新時のナビゲーションを pending として表示できる。
  //   ネットワーク遅延でフィルタが効いていないように見えるのを避ける。
  const [isPending, startTransition] = useTransition();

  // applyFilter: name に値を反映した URL クエリで /problems に navigate する。
  //   value が空文字 / 未指定なら該当キーを取り除く。
  //   page は常にリセット（フィルタが変わったら 1 ページ目に戻す）。
  const applyFilter = (name: "category" | "difficulty", value: string) => {
    const next = new URLSearchParams(searchParams?.toString() ?? "");
    if (value) next.set(name, value);
    else next.delete(name);
    next.delete("page");
    const qs = next.toString();
    startTransition(() => {
      router.push(qs ? `/problems?${qs}` : "/problems");
    });
  };

  const clearAll = () => {
    startTransition(() => {
      router.push("/problems");
    });
  };

  const hasAnyFilter = Boolean(category || difficulty);

  return (
    <form
      // form タグ自体は無動作（select の onChange で navigate する）。
      // ただし Enter キー押下時にページが /problems にリロードされて欲しいので
      // submit ハンドラを抑制。
      onSubmit={(e) => e.preventDefault()}
      className="flex flex-wrap items-end gap-3"
      aria-busy={isPending}
    >
      <label className="flex flex-col gap-1 text-xs text-muted-foreground">
        カテゴリ
        <select
          className={selectClassName}
          value={category ?? ""}
          onChange={(e) => applyFilter("category", e.target.value)}
          aria-label="カテゴリで絞り込み"
        >
          <option value="">すべて</option>
          {PROBLEM_CATEGORY_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </label>

      <label className="flex flex-col gap-1 text-xs text-muted-foreground">
        難易度
        <select
          className={selectClassName}
          value={difficulty ?? ""}
          onChange={(e) => applyFilter("difficulty", e.target.value)}
          aria-label="難易度で絞り込み"
        >
          <option value="">すべて</option>
          {PROBLEM_DIFFICULTY_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </label>

      {hasAnyFilter ? (
        <Button type="button" variant="outline" size="sm" onClick={clearAll}>
          フィルタをクリア
        </Button>
      ) : null}
    </form>
  );
};
