// ApiError / throwIfError の単体テスト。
//   - response 不在（ネットワーク断・CORS 失敗）は status=0 で投げる
//   - 4xx / 5xx は status を保持して投げる
//   - 2xx は data を返す
import { describe, expect, it } from "vitest";

import { ApiError, throwIfError } from "./api-error";

describe("ApiError", () => {
  it("status / body / message を保持する", () => {
    const err = new ApiError(404, { detail: "not found" }, "見つかりません");
    expect(err.status).toBe(404);
    expect(err.body).toEqual({ detail: "not found" });
    expect(err.message).toBe("見つかりません");
    expect(err.name).toBe("ApiError");
    expect(err).toBeInstanceOf(Error);
  });

  it("message 省略時はデフォルト文言が入る", () => {
    const err = new ApiError(500, undefined);
    expect(err.message).toBe("API error (status=500)");
  });
});

describe("throwIfError", () => {
  it("成功レスポンスは data をそのまま返す", async () => {
    const okResponse = new Response("ok", { status: 200 });
    const result = await throwIfError(Promise.resolve({ data: { foo: 1 }, response: okResponse }));
    expect(result).toEqual({ foo: 1 });
  });

  it("response が undefined（fetch 自体が失敗）なら status=0 の ApiError を投げる", async () => {
    await expect(throwIfError(Promise.resolve({ error: "network down" }))).rejects.toMatchObject({
      status: 0,
      body: "network down",
    });
  });

  it("4xx の時 status と body を持つ ApiError を投げる", async () => {
    const unauthorized = new Response(null, { status: 401 });
    await expect(
      throwIfError(Promise.resolve({ error: { detail: "no session" }, response: unauthorized })),
    ).rejects.toMatchObject({
      status: 401,
      body: { detail: "no session" },
    });
  });

  it("5xx でも同様に投げる", async () => {
    const serverError = new Response(null, { status: 500 });
    await expect(
      throwIfError(Promise.resolve({ error: "boom", response: serverError })),
    ).rejects.toBeInstanceOf(ApiError);
  });
});
