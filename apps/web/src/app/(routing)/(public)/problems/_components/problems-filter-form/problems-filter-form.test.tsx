// ProblemsFilterForm のコンポーネントテスト。
//   - 初期値で <select> に props の値が反映される
//   - カテゴリ / 難易度を選ぶと URL クエリを書き換える router.push が走る
//   - フィルタクリアボタンで /problems に戻る

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mockPush = vi.fn();
// useSearchParams は ReadonlyURLSearchParams 互換を返す必要があるので URLSearchParams
//   をそのまま渡す（toString() / get() のみ使う想定）。
const mockSearchParams = new URLSearchParams();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush, replace: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => mockSearchParams,
}));

import { ProblemsFilterForm } from "./problems-filter-form";

describe("ProblemsFilterForm", () => {
  beforeEach(() => {
    mockPush.mockReset();
    // URLSearchParams は同一インスタンスを使い回しているので毎回中身を消す。
    for (const key of Array.from(mockSearchParams.keys())) mockSearchParams.delete(key);
  });

  it("初期値: props の category / difficulty が <select> に反映される", () => {
    render(<ProblemsFilterForm category="array" difficulty="easy" />);
    expect(screen.getByLabelText("カテゴリで絞り込み")).toHaveValue("array");
    expect(screen.getByLabelText("難易度で絞り込み")).toHaveValue("easy");
  });

  it("カテゴリを選ぶと /problems?category=... に push する（page は付かない）", async () => {
    const user = userEvent.setup();
    render(<ProblemsFilterForm category={undefined} difficulty={undefined} />);

    await user.selectOptions(screen.getByLabelText("カテゴリで絞り込み"), "array");

    expect(mockPush).toHaveBeenCalledWith("/problems?category=array");
  });

  it("既存フィルタに加えて難易度を選ぶとクエリが合成される", async () => {
    mockSearchParams.set("category", "array");
    const user = userEvent.setup();
    render(<ProblemsFilterForm category="array" difficulty={undefined} />);

    await user.selectOptions(screen.getByLabelText("難易度で絞り込み"), "hard");

    // category / difficulty が両方付き、page は付かない契約（フィルタ変更で 1 ページ目に戻す）。
    expect(mockPush).toHaveBeenCalledWith("/problems?category=array&difficulty=hard");
  });

  it("「すべて」を選ぶとそのキーが URL から取り除かれる", async () => {
    mockSearchParams.set("category", "array");
    mockSearchParams.set("page", "3");
    const user = userEvent.setup();
    render(<ProblemsFilterForm category="array" difficulty={undefined} />);

    await user.selectOptions(screen.getByLabelText("カテゴリで絞り込み"), "");

    // category が消え、page もリセットされる。残った難易度キーは無いので /problems になる。
    expect(mockPush).toHaveBeenCalledWith("/problems");
  });

  it("フィルタが何か付いている時は「フィルタをクリア」ボタンが出て、押下で /problems に戻る", async () => {
    const user = userEvent.setup();
    render(<ProblemsFilterForm category="array" difficulty="easy" />);

    const clearButton = screen.getByRole("button", { name: "フィルタをクリア" });
    await user.click(clearButton);

    expect(mockPush).toHaveBeenCalledWith("/problems");
  });

  it("フィルタが空の時は「フィルタをクリア」ボタンは出ない", () => {
    render(<ProblemsFilterForm category={undefined} difficulty={undefined} />);
    expect(screen.queryByRole("button", { name: "フィルタをクリア" })).not.toBeInTheDocument();
  });
});
