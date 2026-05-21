// server-api-client.ts の env 分岐テスト。
//
// 何を担保するか：
//   - 本番（NODE_ENV=production）かつ API_PROXY_TARGET 未設定なら起動時に throw
//     （silent な localhost フォールバックを防ぐ）
//   - 本番でも `next build` 中（NEXT_PHASE=phase-production-build）は throw しない
//     （build phase は API_PROXY_TARGET 不要のため誤発火を避ける）
//   - dev / test では API_PROXY_TARGET 未設定でも http://localhost:8000 にフォールバック
//
// 仕組み：
//   server-api-client.ts はモジュールトップレベルで env を読んで分岐するため、
//   テスト毎に process.env を書き換え → vi.resetModules() → 動的 import で副作用を観測する。
//   create*Client の呼び出し自体は副作用が少ないため、importable かどうか（throw するか / しないか）
//   と export された serverApiClient が呼べる object であることだけを確認する。

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// __generated__/api/client は実体を import すると Hey API ランタイムを引き込むため、
//   テストでは createClient / createConfig を spy 化して副作用を観測する。
vi.mock("@/__generated__/api/client", () => ({
  createClient: vi.fn((config) => ({ __config: config })),
  createConfig: vi.fn((config) => config),
}));

// vi.stubEnv: NODE_ENV / NEXT_PHASE 等の readonly 型 env を安全に書き換える Vitest 公式 API。
//   afterEach の vi.unstubAllEnvs() で必ず原状復帰する。
beforeEach(() => {
  vi.stubEnv("API_PROXY_TARGET", undefined as unknown as string);
  vi.stubEnv("NEXT_PHASE", undefined as unknown as string);
  vi.resetModules();
});

afterEach(() => {
  vi.unstubAllEnvs();
});

type ClientShape = { __config: { baseUrl: string } };

describe("serverApiClient の env 分岐", () => {
  it("本番（NODE_ENV=production）で API_PROXY_TARGET 未設定なら import 時に throw", async () => {
    vi.stubEnv("NODE_ENV", "production");

    await expect(import("./server-api-client")).rejects.toThrow(/API_PROXY_TARGET is required/);
  });

  it("本番でも NEXT_PHASE=phase-production-build なら throw しない（build phase バイパス）", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("NEXT_PHASE", "phase-production-build");

    const mod = await import("./server-api-client");
    expect(mod.serverApiClient).toBeDefined();
  });

  it("本番で API_PROXY_TARGET が設定されていれば throw しない", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("API_PROXY_TARGET", "https://api.example.com");

    const mod = await import("./server-api-client");
    expect(mod.serverApiClient).toBeDefined();
    // createClient に渡された baseUrl が env の値そのままであることを確認する。
    expect((mod.serverApiClient as unknown as ClientShape).__config.baseUrl).toBe(
      "https://api.example.com",
    );
  });

  it("dev / test では API_PROXY_TARGET 未設定でも throw せず localhost:8000 にフォールバック", async () => {
    vi.stubEnv("NODE_ENV", "development");

    const mod = await import("./server-api-client");
    expect((mod.serverApiClient as unknown as ClientShape).__config.baseUrl).toBe(
      "http://localhost:8000",
    );
  });
});
