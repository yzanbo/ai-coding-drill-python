// StatusBadge のテスト：
//   - children がそのまま表示される
//   - tone ごとに対応する Tailwind クラスが付く（色の SSoT が壊れないよう pin）
//
//   Tailwind は最終的に CSS に展開されるため、class 名そのものを assertion する。

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusBadge } from "./status-badge";

describe("StatusBadge", () => {
  it("正常系: children のテキストが表示される", () => {
    render(<StatusBadge tone="ok">成功</StatusBadge>);
    expect(screen.getByText("成功")).toBeInTheDocument();
  });

  it.each([
    ["ok", "text-primary"],
    ["ng", "text-destructive"],
    ["warn", "text-amber-600"],
    ["muted", "text-muted-foreground"],
  ] as const)("正常系: tone=%s は %s クラスを付ける", (tone, expectedClass) => {
    render(<StatusBadge tone={tone}>X</StatusBadge>);
    const el = screen.getByText("X");
    expect(el.className).toContain(expectedClass);
  });

  it("正常系: className prop を merge できる", () => {
    render(
      <StatusBadge tone="ok" className="ml-2">
        X
      </StatusBadge>,
    );
    expect(screen.getByText("X").className).toContain("ml-2");
  });
});
