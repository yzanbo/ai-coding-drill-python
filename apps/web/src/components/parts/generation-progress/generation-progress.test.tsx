// GenerationProgress のテスト：
//   - currentStep に応じて「完了」「現在」「未着手」の 3 区分が正しく付く
//   - currentStep=null は「キュー待ち」扱いで全段未着手
//   - variant="compact" / "full" の両方で longLabel が出る

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { GenerationProgress } from "./generation-progress";

describe("GenerationProgress (full)", () => {
  it("正常系: currentStep=judging なら 1〜2 段目が完了、3 段目が現在、4 段目が未着手", () => {
    render(<GenerationProgress currentStep="judging" />);
    // 完了段は ✓ マーク。現在段は番号 3。未着手段は番号 4。
    // ✓ は完了 2 段で 2 つ。
    expect(screen.getAllByText("✓").length).toBe(2);
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();
    // longLabel が全段表示される
    expect(screen.getByText("AI が問題を作成中")).toBeInTheDocument();
    expect(screen.getByText("AI が問題の品質を評価中")).toBeInTheDocument();
  });

  it("正常系: currentStep=null（キュー待ち）は全段未着手で 1〜4 番が並ぶ", () => {
    render(<GenerationProgress currentStep={null} />);
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();
    expect(screen.queryByText("✓")).not.toBeInTheDocument();
  });
});

describe("GenerationProgress (compact)", () => {
  it("正常系: 現在ステップの longLabel が 1 行で出る", () => {
    render(<GenerationProgress currentStep="sandbox_verifying" variant="compact" />);
    expect(screen.getByText("模範解答を実行して検証中")).toBeInTheDocument();
  });

  it("正常系: currentStep=null は「キュー待ち」表記", () => {
    render(<GenerationProgress currentStep={null} variant="compact" />);
    expect(screen.getByText("キュー待ち")).toBeInTheDocument();
  });
});
