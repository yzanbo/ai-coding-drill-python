// Playwright 設定（ADR 0038）。R5 で本格利用、R0 では雛形のみ置く。
// 詳細: https://playwright.dev/docs/test-configuration
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  // testDir: E2E テストの置き場所（Vitest と分離するため e2e/ に集約）。
  testDir: "./e2e",
  // fullyParallel: ファイル間を並列実行。
  fullyParallel: true,
  // forbidOnly: CI 上で .only テストが残っていれば fail させる安全策。
  forbidOnly: !!process.env.CI,
  // retries: CI でだけ 2 回まで再実行（フレーキー対策）。ローカルは 0。
  retries: process.env.CI ? 2 : 0,
  reporter: "html",
  use: {
    baseURL: "http://localhost:3000",
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
