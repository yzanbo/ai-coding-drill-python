// format-percent のテスト：丸めの再現と境界値。

import { describe, expect, it } from "vitest";

import { formatPercent } from "./format-percent";

describe("formatPercent", () => {
  it.each([
    [0, "0.0%"],
    [0.5, "50.0%"],
    [0.7142, "71.4%"],
    [0.99995, "100.0%"], // toFixed(1) の四捨五入で 100.0
    [1, "100.0%"],
  ])("正常系: %s -> %s", (input, expected) => {
    expect(formatPercent(input)).toBe(expected);
  });
});
