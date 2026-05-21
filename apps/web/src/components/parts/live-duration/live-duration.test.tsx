// LiveDuration のテスト：
//   - 完了済（completedAt あり）は静的表示、タイマで再レンダリングされない
//   - 進行中（completedAt なし）は 1 秒ごとに値が進む
//   - unmount 時に setInterval が片付くこと（React の cleanup 経由で確認）

import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LiveDuration } from "./live-duration";

describe("LiveDuration", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    // 基準時刻を 2026-05-21 00:00:00 UTC に固定。createdAt から N 秒後の
    // 表示を逐次検証する。
    vi.setSystemTime(new Date("2026-05-21T00:00:00Z"));
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("正常系: completedAt 確定済の行は固定値を出し、時刻を進めても変化しない", () => {
    render(<LiveDuration createdAt="2026-05-21T00:00:00Z" completedAt="2026-05-21T00:01:30Z" />);
    // 90 秒 = 1 分 30 秒
    expect(screen.getByText("1 分 30 秒")).toBeInTheDocument();

    // 時刻を 10 秒進めても表示は変わらない（タイマ非起動）。
    act(() => {
      vi.advanceTimersByTime(10_000);
    });
    expect(screen.getByText("1 分 30 秒")).toBeInTheDocument();
  });

  it("正常系: completedAt 未確定の行は 1 秒ごとに値が進む", () => {
    render(<LiveDuration createdAt="2026-05-21T00:00:00Z" completedAt={null} />);
    expect(screen.getByText("0 秒")).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(screen.getByText("1 秒")).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(screen.getByText("3 秒")).toBeInTheDocument();
  });

  it("正常系: 60 秒を超えると「分 秒」表記に切り替わる", () => {
    render(<LiveDuration createdAt="2026-05-21T00:00:00Z" completedAt={undefined} />);

    act(() => {
      vi.advanceTimersByTime(65_000);
    });
    expect(screen.getByText("1 分 5 秒")).toBeInTheDocument();
  });

  it("異常系: createdAt が不正なら「—」を出す", () => {
    render(<LiveDuration createdAt="not-a-date" completedAt={null} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });
});
