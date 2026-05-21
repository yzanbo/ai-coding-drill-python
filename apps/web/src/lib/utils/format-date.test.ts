// format-date のテスト：
//   - 正常系：有効な ISO 8601 を YYYY/MM/DD HH:mm に整形
//   - 異常系：null / undefined / 不正文字列はすべて "—"
//   - ゼロ埋め：1 桁月日時分が 2 桁になる
//
//   タイムゾーン：getMonth() 等を使うため OS ロケール依存。CI / ローカル
//   どちらでも壊れないよう「同じ Date を 2 回作って結果を比較」する間接形で書く。
//   （getTimezoneOffset 等で UTC ↔ ローカル換算する厳密テストは過剰）

import { describe, expect, it } from "vitest";

import { formatDate } from "./format-date";

describe("formatDate", () => {
  it("正常系: YYYY/MM/DD HH:mm 形式に整形する", () => {
    // 2026-05-21 のローカル深夜 0:00 を作って、月日が 05/21 で出ることを pin。
    const local = new Date(2026, 4, 21, 9, 5);
    expect(formatDate(local.toISOString())).toBe("2026/05/21 09:05");
  });

  it("正常系: 1 桁月日時分はゼロ埋めされる", () => {
    const local = new Date(2026, 0, 3, 1, 7);
    expect(formatDate(local.toISOString())).toBe("2026/01/03 01:07");
  });

  it.each([null, undefined, "", "not-a-date"])("異常系: 無効値 (%s) は em-dash を返す", (v) => {
    expect(formatDate(v)).toBe("—");
  });
});
