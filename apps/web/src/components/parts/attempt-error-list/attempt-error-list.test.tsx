// AttemptErrorList のテスト：
//   - 要素 0 件なら何も描画しない
//   - 要素 N 件なら summary + 全要素が描画される
//   - failureReason のタグが日本語ラベルに変換される

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AttemptErrorList } from "./attempt-error-list";

describe("AttemptErrorList", () => {
  it("正常系: 要素 0 件なら何も描画しない", () => {
    const { container } = render(<AttemptErrorList attemptErrors={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it("正常系: 3 試行のエラーが全て描画され、タグが日本語ラベルになる", () => {
    render(
      <AttemptErrorList
        attemptErrors={[
          {
            attempt: 1,
            failureReason: "llm_rate_limit",
            message: "grading: rate limit",
            failedAt: "2026-05-21T00:00:01Z",
          },
          {
            attempt: 2,
            failureReason: "judge_below_threshold",
            message: "grading: judge score 60 < 70",
            failedAt: "2026-05-21T00:01:30Z",
          },
          {
            attempt: 3,
            failureReason: "sandbox_failed",
            message: "grading: 2/5 tests failed",
            failedAt: "2026-05-21T00:03:10Z",
          },
        ]}
      />,
    );

    expect(screen.getByText(/3 回分の試行エラー/)).toBeInTheDocument();
    expect(screen.getByText("AI レート制限")).toBeInTheDocument();
    expect(screen.getByText("品質スコア不足")).toBeInTheDocument();
    expect(screen.getByText("テスト不合格")).toBeInTheDocument();
    expect(screen.getByText("grading: rate limit")).toBeInTheDocument();
  });

  it("正常系: attempt=0 (MarkDead 経路) は試行番号が — で表示される", () => {
    render(
      <AttemptErrorList
        attemptErrors={[
          {
            attempt: 0,
            failureReason: "llm_unauthorized",
            message: "grading: unauthorized",
            failedAt: "2026-05-21T00:00:01Z",
          },
        ]}
      />,
    );
    expect(screen.getByText("試行 —")).toBeInTheDocument();
    expect(screen.getByText("AI 認証失敗")).toBeInTheDocument();
  });
});
