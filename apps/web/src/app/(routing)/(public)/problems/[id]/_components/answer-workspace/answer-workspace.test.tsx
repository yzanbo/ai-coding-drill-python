// AnswerWorkspace のコンポーネントテスト。
//   - ゲスト：実行ボタン押下で /login?next=/problems/:id に push される
//   - 認証ユーザー：実行ボタン押下で POST /api/submissions が走り、
//     submissionId のフィードバックが表示される
//   - localStorage の保存と復元
//
// CodeEditor を vi.mock で textarea に差し替える理由：
//   CodeMirror 6 は jsdom 環境で動かない（getClientRects 等の measurement に
//   実ブラウザを要求する）。本テストは AnswerWorkspace の振る舞いのみ検証する
//   ためエディタは textarea 等価モックで十分。

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { API_BASE, server } from "@/test/msw-server";
import { withQueryClient } from "@/test/render-with-query";

const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush, replace: vi.fn(), prefetch: vi.fn() }),
}));

// CodeEditor を差し替え：value を反映した textarea を出し、onChange に文字列を渡す。
vi.mock("./_components/code-editor/code-editor", () => ({
  CodeEditor: ({ value, onChange }: { value: string; onChange: (next: string) => void }) => (
    <textarea
      aria-label="解答コードエディタ"
      value={value}
      onChange={(e) => onChange(e.target.value)}
    />
  ),
}));

import { AnswerWorkspace } from "./answer-workspace";

const PROBLEM_ID = "00000000-0000-0000-0000-000000000001";

// useGetAuthMe 用の /auth/me ハンドラを切り替えるユーティリティ。
const respondAuthAs = (state: "guest" | "authed") => {
  if (state === "guest") {
    server.use(http.get(`${API_BASE}/auth/me`, () => new HttpResponse(null, { status: 401 })));
  } else {
    server.use(
      http.get(`${API_BASE}/auth/me`, () =>
        HttpResponse.json(
          { id: "u-1", displayName: "テストユーザー", email: "t@example.com" },
          { status: 200 },
        ),
      ),
    );
  }
};

describe("AnswerWorkspace", () => {
  beforeEach(() => {
    mockPush.mockReset();
    window.localStorage.clear();
  });

  it("ゲスト：実行ボタン押下で /login?next=/problems/:id に push される", async () => {
    respondAuthAs("guest");
    const user = userEvent.setup();
    render(<AnswerWorkspace problemId={PROBLEM_ID} />, { wrapper: withQueryClient() });

    // 認証状態の確定（401 受信）まで待つ：ボタンが disabled→enabled になる。
    const button = await screen.findByRole("button", { name: "実行" });
    await waitFor(() => expect(button).not.toBeDisabled());

    await user.click(button);

    expect(mockPush).toHaveBeenCalledWith(
      `/login?next=${encodeURIComponent(`/problems/${PROBLEM_ID}`)}`,
    );
  });

  it("認証ユーザー：実行ボタン押下で POST /api/submissions が走り submissionId がフィードバックされる", async () => {
    respondAuthAs("authed");
    server.use(
      http.post(`${API_BASE}/api/submissions`, () =>
        HttpResponse.json({ submissionId: "sub-xyz", status: "pending" }, { status: 202 }),
      ),
    );
    const user = userEvent.setup();
    render(<AnswerWorkspace problemId={PROBLEM_ID} />, { wrapper: withQueryClient() });

    const button = await screen.findByRole("button", { name: "実行" });
    await waitFor(() => expect(button).not.toBeDisabled());

    await user.click(button);

    // 送信中表示 → 完了フィードバック の遷移。
    expect(await screen.findByText(/sub-xyz/)).toBeInTheDocument();
    expect(mockPush).not.toHaveBeenCalled();
  });

  it("localStorage に問題ごとの draft が保存され、再マウント時に復元される", async () => {
    respondAuthAs("authed");
    const user = userEvent.setup();
    const { unmount } = render(<AnswerWorkspace problemId={PROBLEM_ID} />, {
      wrapper: withQueryClient(),
    });

    const editor = await screen.findByLabelText("解答コードエディタ");
    // 初期値（DEFAULT_CODE）を消して別文字列に書き換える。
    await user.clear(editor);
    await user.type(editor, "const solve = () => 42;");

    // localStorage に書き出されている。
    await waitFor(() =>
      expect(window.localStorage.getItem(`ai-coding-drill:answer:${PROBLEM_ID}`)).toBe(
        "const solve = () => 42;",
      ),
    );

    unmount();

    // 再マウントすると復元される。
    render(<AnswerWorkspace problemId={PROBLEM_ID} />, { wrapper: withQueryClient() });
    const restored = await screen.findByLabelText("解答コードエディタ");
    await waitFor(() => expect(restored).toHaveValue("const solve = () => 42;"));
  });
});
