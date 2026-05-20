// 問題生成リクエスト画面のフォーム入力スキーマ。
//   許可値は OpenAPI / Pydantic 由来の生成 Zod (zProblemCategory / zProblemDifficulty) を SSoT として
//   .options から取り出し、未入力時に表示する日本語メッセージだけここで上書きする。
//   要件: docs/requirements/4-features/problem-generation.md §バリデーション

import * as z from "zod";

import { zProblemCategory, zProblemDifficulty } from "@/__generated__/api/zod.gen";

export const problemGenerateFormSchema = z.object({
  // category: 未選択（undefined）の時に「カテゴリを指定してください」と表示する。
  category: z.enum(zProblemCategory.options, { error: "カテゴリを指定してください" }),
  difficulty: z.enum(zProblemDifficulty.options, { error: "難易度を指定してください" }),
});

export type ProblemGenerateFormValues = z.infer<typeof problemGenerateFormSchema>;
