// ProblemGenerateForm の結合テスト。
//   要件: problem-generation.md §問題生成画面
//   - カテゴリ + 難易度を選んで送信すると /problems/generate/:requestId に遷移する
//   - 何も選ばずに送信するとバリデーションエラーが出る
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { API_BASE, server } from "@/test/msw-server";
import { withQueryClient } from "@/test/render-with-query";

import { ProblemGenerateForm } from "./problem-generate-form";

const mockReplace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mockReplace, push: vi.fn(), prefetch: vi.fn(), refresh: vi.fn() }),
}));

beforeEach(() => {
  mockReplace.mockReset();
});

describe("ProblemGenerateForm", () => {
  it("正常系: カテゴリと難易度を選んで送信すると、ステータス画面に router.replace される", async () => {
    server.use(
      http.post(`${API_BASE}/problems/generate`, () =>
        HttpResponse.json({ requestId: "req-001", status: "pending" }, { status: 202 }),
      ),
    );

    render(<ProblemGenerateForm />, { wrapper: withQueryClient() });

    // ラジオは label でラップしているので、ラベル文言（accessibleName）をクリックすれば選択される。
    await userEvent.click(screen.getByRole("radio", { name: /配列/ }));
    await userEvent.click(screen.getByRole("radio", { name: /やさしい/ }));
    await userEvent.click(screen.getByRole("button", { name: "問題を生成する" }));

    await vi.waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/problems/generate/req-001"));
  });

  it("異常系: 未入力で送信するとバリデーションエラーが表示される", async () => {
    render(<ProblemGenerateForm />, { wrapper: withQueryClient() });

    await userEvent.click(screen.getByRole("button", { name: "問題を生成する" }));

    expect(await screen.findByText("カテゴリを指定してください")).toBeInTheDocument();
    expect(await screen.findByText("難易度を指定してください")).toBeInTheDocument();
    expect(mockReplace).not.toHaveBeenCalled();
  });
});
