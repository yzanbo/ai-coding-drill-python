"use client";

// ProblemGenerateForm: カテゴリ・難易度を選んで「生成リクエスト」する RHF フォーム。
//   - 入力は radio-group のカード型 UI（候補が少なく、初学者が一覧で選べる方が UX が良いため）
//   - 送信成功で /problems/generate/:requestId に遷移（同期で待たせない設計）
//   要件: docs/requirements/4-features/problem-generation.md §問題生成画面
//
// a11y のエラー結び付け方:
//   role="alert" は live region で「画面の主役を割り込み読み上げ」するため、フォームのインラインエラーには強すぎる。
//   代わりに <p id="...-error"> + RadioGroup の aria-describedby/aria-errormessage で関連付け、
//   スクリーンリーダーにラジオへフォーカスが当たった時にだけエラーを読ませる。

import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { useId } from "react";
import { Controller, useForm } from "react-hook-form";

import { Button } from "@/components/ui/button/button";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group/radio-group";
import { PROBLEM_CATEGORY_OPTIONS } from "@/lib/constants/problem-categories";
import { PROBLEM_DIFFICULTY_OPTIONS } from "@/lib/constants/problem-difficulties";
import {
  type ProblemGenerateFormValues,
  problemGenerateFormSchema,
} from "@/lib/validation/problem-generate-form-schema";

import { usePostProblemGenerate } from "../../_hooks/_fetch/use-post-problem-generate/use-post-problem-generate";

// optionCardClassName: ラジオカード共通スタイル。
//   - 未選択時: 通常の枠線
//   - 選択時: data-[state=checked] を Radix Item が当てるので、その値で枠と背景を強調
//   - フォーカス時: ring を出してキーボード操作の現在地を可視化
const optionCardClassName =
  "flex cursor-pointer items-start gap-3 rounded-lg border border-border bg-card p-4 text-card-foreground shadow-sm transition-colors duration-200 hover:bg-accent has-[[data-state=checked]]:border-primary has-[[data-state=checked]]:bg-primary/5 has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring";

export const ProblemGenerateForm = () => {
  const router = useRouter();

  // form: RHF 本体。zod スキーマを通して許可値外を弾く。
  //   mode: onTouched → 初回 blur で発火し、以降はリアルタイム検証（frontend.md §フォームバリデーション）。
  //   defaultValues: 未選択を明示的に undefined で開始する（指定なしだと内部で
  //     undefined 扱いだが、Controller の value が controlled / uncontrolled の境を
  //     またぐ React 警告に将来引っかからないよう、初期値の意図を読みやすい形で残す）。
  const form = useForm<ProblemGenerateFormValues>({
    resolver: zodResolver(problemGenerateFormSchema),
    mode: "onTouched",
    defaultValues: { category: undefined, difficulty: undefined },
  });

  // useId: SSR / CSR で安定したユニーク ID を生成。
  //   エラー文の id を RadioGroup の aria-describedby / aria-errormessage に紐付けるために使う。
  //   同じフォームが画面に複数描画されても衝突しないようにフィールド名を suffix に付ける。
  const idPrefix = useId();
  const categoryErrorId = `${idPrefix}-category-error`;
  const difficultyErrorId = `${idPrefix}-difficulty-error`;

  const { requestGenerate, isPending } = usePostProblemGenerate({
    onSuccess: (data) => {
      // 受付完了で requestId を持って生成ステータス画面へ。replace で履歴を汚さない。
      router.replace(`/problems/generate/${data.requestId}`);
    },
  });

  return (
    <form
      className="flex flex-col gap-8"
      onSubmit={form.handleSubmit((values) => requestGenerate(values))}
      noValidate
    >
      <Controller
        control={form.control}
        name="category"
        render={({ field, fieldState }) => (
          <fieldset className="flex flex-col gap-3">
            <legend className="text-base font-semibold">カテゴリ</legend>
            <RadioGroup
              // value: undefined 時は空文字で渡す（Radix は controlled で string を期待するため）。
              value={field.value ?? ""}
              onValueChange={field.onChange}
              onBlur={field.onBlur}
              className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3"
              aria-invalid={!!fieldState.error || undefined}
              // aria-errormessage: エラー発生時のみ参照させて、スクリーンリーダーに余計な要素を読ませない。
              aria-errormessage={fieldState.error ? categoryErrorId : undefined}
            >
              {PROBLEM_CATEGORY_OPTIONS.map((option) => {
                const id = `category-${option.value}`;
                return (
                  // label でラジオを囲うことで、カード全体クリックで選択される。
                  <label key={option.value} htmlFor={id} className={optionCardClassName}>
                    <RadioGroupItem id={id} value={option.value} className="mt-1" />
                    <span className="flex flex-col gap-1">
                      <span className="text-sm font-medium">{option.label}</span>
                      <span className="text-xs text-muted-foreground">{option.description}</span>
                    </span>
                  </label>
                );
              })}
            </RadioGroup>
            {fieldState.error && (
              <p id={categoryErrorId} className="text-sm text-destructive">
                {fieldState.error.message}
              </p>
            )}
          </fieldset>
        )}
      />

      <Controller
        control={form.control}
        name="difficulty"
        render={({ field, fieldState }) => (
          <fieldset className="flex flex-col gap-3">
            <legend className="text-base font-semibold">難易度</legend>
            <RadioGroup
              value={field.value ?? ""}
              onValueChange={field.onChange}
              onBlur={field.onBlur}
              className="grid gap-3 sm:grid-cols-3"
              aria-invalid={!!fieldState.error || undefined}
              aria-errormessage={fieldState.error ? difficultyErrorId : undefined}
            >
              {PROBLEM_DIFFICULTY_OPTIONS.map((option) => {
                const id = `difficulty-${option.value}`;
                return (
                  <label key={option.value} htmlFor={id} className={optionCardClassName}>
                    <RadioGroupItem id={id} value={option.value} className="mt-1" />
                    <span className="flex flex-col gap-1">
                      <span className="text-sm font-medium">{option.label}</span>
                      <span className="text-xs text-muted-foreground">{option.description}</span>
                    </span>
                  </label>
                );
              })}
            </RadioGroup>
            {fieldState.error && (
              <p id={difficultyErrorId} className="text-sm text-destructive">
                {fieldState.error.message}
              </p>
            )}
          </fieldset>
        )}
      />

      <div className="flex justify-end">
        <Button type="submit" size="lg" disabled={isPending}>
          {isPending ? "送信中…" : "問題を生成する"}
        </Button>
      </div>
    </form>
  );
};
