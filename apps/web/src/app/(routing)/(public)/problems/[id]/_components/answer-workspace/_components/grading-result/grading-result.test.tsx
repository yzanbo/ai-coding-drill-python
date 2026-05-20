// GradingResult のコンポーネントテスト。
//   要件: grading.md §採点結果表示 / §受け入れ条件
//   - pending → 「採点中」+ スピナー
//   - graded + passed=true → 「正解」+ 通過数
//   - graded + 各 failureKind → 種別ラベル + (test_failed なら失敗テスト一覧)
//   - failed → 「一時的なエラー」+ 再試行ボタン (onRetry 呼び出し)
//   - 404 等のエラー → 「採点結果の取得に失敗しました」

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it, vi } from "vitest";

import { API_BASE, server } from "@/test/msw-server";
import { withQueryClient } from "@/test/render-with-query";

import { GradingResult } from "./grading-result";

const SUBMISSION_ID = "00000000-0000-0000-0000-000000000aaa";
const PROBLEM_ID = "00000000-0000-0000-0000-0000000000bb";

// respondSubmission: GET /api/submissions/:id を 1 個のレスポンスで固定する。
const respondSubmission = (body: object) => {
  server.use(
    http.get(`${API_BASE}/api/submissions/${SUBMISSION_ID}`, () => HttpResponse.json(body)),
  );
};

const renderGradingResult = (onRetry: () => void = vi.fn()) =>
  render(<GradingResult submissionId={SUBMISSION_ID} onRetry={onRetry} />, {
    wrapper: withQueryClient(),
  });

describe("GradingResult", () => {
  it("pending: スピナーと「採点中」が表示される", async () => {
    respondSubmission({
      id: SUBMISSION_ID,
      problemId: PROBLEM_ID,
      status: "pending",
    });

    renderGradingResult();

    expect(await screen.findByText(/採点中/)).toBeInTheDocument();
  });

  it("graded + passed=true: 「正解」と通過数が表示される", async () => {
    respondSubmission({
      id: SUBMISSION_ID,
      problemId: PROBLEM_ID,
      status: "graded",
      score: 3,
      totalCount: 3,
      result: {
        passed: true,
        durationMs: 1340,
        testResults: [
          { name: "case1", passed: true, durationMs: 100 },
          { name: "case2", passed: true, durationMs: 120 },
          { name: "case3", passed: true, durationMs: 110 },
        ],
      },
      gradedAt: "2026-05-21T00:00:00Z",
    });

    renderGradingResult();

    expect(await screen.findByText("正解")).toBeInTheDocument();
    // 通過数: 3/3 が含まれる (UI は <span>3/3</span> として描画される)。
    expect(screen.getByText("3/3")).toBeInTheDocument();
  });

  it("graded + test_failed: ラベルと失敗テストの details が含まれる", async () => {
    respondSubmission({
      id: SUBMISSION_ID,
      problemId: PROBLEM_ID,
      status: "graded",
      score: 1,
      totalCount: 3,
      result: {
        passed: false,
        durationMs: 200,
        failureKind: "test_failed",
        testResults: [
          { name: "case1", passed: true, durationMs: 50 },
          {
            name: "case2",
            passed: false,
            durationMs: 60,
            expected: "6",
            actual: "7",
            message: "AssertionError: expected 7 to equal 6",
          },
          {
            name: "case3",
            passed: false,
            durationMs: 70,
            expected: "10",
            actual: "9",
          },
        ],
      },
      gradedAt: "2026-05-21T00:00:00Z",
    });

    renderGradingResult();

    expect(await screen.findByText("テスト不合格")).toBeInTheDocument();
    expect(screen.getByText("1/3")).toBeInTheDocument();
    // 失敗テスト一覧の details summary。失敗 2 件をカウント表記する。
    expect(screen.getByText(/失敗したテストケース \(2\)/)).toBeInTheDocument();
    // 期待値 / 実際の出力 / message が含まれる (details 内、jsdom では非展開でも DOM には居る)。
    expect(screen.getByText("6")).toBeInTheDocument();
    expect(screen.getByText("7")).toBeInTheDocument();
    expect(screen.getByText(/AssertionError/)).toBeInTheDocument();
  });

  it("graded + timeout: 「タイムアウト」ラベル", async () => {
    respondSubmission({
      id: SUBMISSION_ID,
      problemId: PROBLEM_ID,
      status: "graded",
      score: 0,
      totalCount: 0,
      result: { passed: false, durationMs: 5000, failureKind: "timeout", testResults: [] },
      gradedAt: "2026-05-21T00:00:00Z",
    });

    renderGradingResult();

    expect(await screen.findByText("タイムアウト")).toBeInTheDocument();
  });

  it("graded + oom: 「メモリ使用量超過」ラベル", async () => {
    respondSubmission({
      id: SUBMISSION_ID,
      problemId: PROBLEM_ID,
      status: "graded",
      score: 0,
      totalCount: 0,
      result: { passed: false, durationMs: 800, failureKind: "oom", testResults: [] },
      gradedAt: "2026-05-21T00:00:00Z",
    });

    renderGradingResult();

    expect(await screen.findByText("メモリ使用量超過")).toBeInTheDocument();
  });

  it("graded + syntax: 「構文エラー」ラベル", async () => {
    respondSubmission({
      id: SUBMISSION_ID,
      problemId: PROBLEM_ID,
      status: "graded",
      score: 0,
      totalCount: 0,
      result: { passed: false, durationMs: 50, failureKind: "syntax", testResults: [] },
      gradedAt: "2026-05-21T00:00:00Z",
    });

    renderGradingResult();

    expect(await screen.findByText("構文エラー")).toBeInTheDocument();
  });

  it("graded + runtime: 「実行時エラー」ラベル", async () => {
    respondSubmission({
      id: SUBMISSION_ID,
      problemId: PROBLEM_ID,
      status: "graded",
      score: 0,
      totalCount: 0,
      result: { passed: false, durationMs: 80, failureKind: "runtime", testResults: [] },
      gradedAt: "2026-05-21T00:00:00Z",
    });

    renderGradingResult();

    expect(await screen.findByText("実行時エラー")).toBeInTheDocument();
  });

  it("failed (インフラ起因): 再試行ボタンを押すと onRetry が呼ばれる", async () => {
    respondSubmission({
      id: SUBMISSION_ID,
      problemId: PROBLEM_ID,
      status: "failed",
    });
    const onRetry = vi.fn();
    const user = userEvent.setup();

    renderGradingResult(onRetry);

    expect(await screen.findByText("一時的なエラーが発生しました")).toBeInTheDocument();
    const retryButton = screen.getByRole("button", { name: "再試行" });
    await user.click(retryButton);
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("異常系: 404 で「採点結果の取得に失敗しました」が表示される", async () => {
    server.use(
      http.get(
        `${API_BASE}/api/submissions/${SUBMISSION_ID}`,
        () => new HttpResponse(null, { status: 404 }),
      ),
    );

    renderGradingResult();

    await waitFor(() =>
      expect(screen.queryByText("採点結果の取得に失敗しました")).toBeInTheDocument(),
    );
  });
});
