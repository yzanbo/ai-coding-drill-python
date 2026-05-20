// problemGenerateFormSchema のスキーマテスト。
//   要件: problem-generation.md §バリデーション
//   - 正常系: 許可値の組み合わせは success
//   - 異常系: 未入力 / 範囲外の値はエラーメッセージ付きで fail
import { describe, expect, it } from "vitest";

import { problemGenerateFormSchema } from "./problem-generate-form-schema";

describe("problemGenerateFormSchema", () => {
  it("正常系: 許可値の組み合わせを受け入れる", () => {
    const result = problemGenerateFormSchema.safeParse({
      category: "array",
      difficulty: "medium",
    });
    expect(result.success).toBe(true);
  });

  it("異常系: category 未入力で「カテゴリを指定してください」を返す", () => {
    const result = problemGenerateFormSchema.safeParse({ difficulty: "easy" });
    expect(result.success).toBe(false);
    if (!result.success) {
      const issue = result.error.issues.find((i) => i.path[0] === "category");
      expect(issue?.message).toBe("カテゴリを指定してください");
    }
  });

  it("異常系: difficulty 未入力で「難易度を指定してください」を返す", () => {
    const result = problemGenerateFormSchema.safeParse({ category: "string" });
    expect(result.success).toBe(false);
    if (!result.success) {
      const issue = result.error.issues.find((i) => i.path[0] === "difficulty");
      expect(issue?.message).toBe("難易度を指定してください");
    }
  });

  it("異常系: 許可値外の category（unknown）を拒否する", () => {
    const result = problemGenerateFormSchema.safeParse({
      category: "unknown-category",
      difficulty: "easy",
    });
    expect(result.success).toBe(false);
  });

  it("異常系: 許可値外の difficulty（impossible）を拒否する", () => {
    const result = problemGenerateFormSchema.safeParse({
      category: "string",
      difficulty: "impossible",
    });
    expect(result.success).toBe(false);
  });
});
