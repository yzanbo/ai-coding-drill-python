// authAwareRetry の挙動契約。
//   - 401 は failureCount に関わらず即 false（retry しない）
//   - その他のエラーは failureCount < 1 の時だけ true（= 計 2 回試行）
//   - ネットワーク断（response 無し）相当の ApiError(status=0) は retry 対象

import { describe, expect, it } from "vitest";

import { ApiError } from "./api-error";
import { authAwareRetry } from "./query-retry";

describe("authAwareRetry", () => {
  it("401 は failureCount=0 でも retry しない", () => {
    const err = new ApiError(401, null);
    expect(authAwareRetry(0, err)).toBe(false);
  });

  it("401 は failureCount=5 でも retry しない", () => {
    const err = new ApiError(401, null);
    expect(authAwareRetry(5, err)).toBe(false);
  });

  it("500 は failureCount=0 の時に retry する", () => {
    const err = new ApiError(500, null);
    expect(authAwareRetry(0, err)).toBe(true);
  });

  it("500 は failureCount=1 の時には retry しない（計 2 回試行で打ち止め）", () => {
    const err = new ApiError(500, null);
    expect(authAwareRetry(1, err)).toBe(false);
  });

  it("ネットワーク断（ApiError status=0）は 1 回だけ retry する", () => {
    const err = new ApiError(0, null);
    expect(authAwareRetry(0, err)).toBe(true);
    expect(authAwareRetry(1, err)).toBe(false);
  });

  it("ApiError でない素の Error も 1 回だけ retry する", () => {
    const err = new Error("boom");
    expect(authAwareRetry(0, err)).toBe(true);
    expect(authAwareRetry(1, err)).toBe(false);
  });
});
