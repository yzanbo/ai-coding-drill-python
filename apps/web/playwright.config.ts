// Playwright 設定（ADR 0038）。
// R1-1 GitHub OAuth ログインの E2E テスト着地に伴い webServer を本格構成化。
// 詳細: https://playwright.dev/docs/test-configuration
import { defineConfig, devices } from "@playwright/test";

// E2E 専用環境変数。docker compose で起動した dev DB / Redis に向ける想定。
// 機密値は含まないため (E2E 用 dummy CLIENT_ID / SECRET / dev 接続情報) 本ファイルで定義してよい。
// _ プレフィックスは「Playwright 起動スクリプト内専用、production には流さない」目印。
const _MOCK_GITHUB_PORT = 18001;
const _API_PORT = 8000;
const _WEB_PORT = 3000;
const _DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/ai_coding_drill";
const _REDIS_URL = "redis://localhost:6379/0";
const _MOCK_GITHUB_ORIGIN = `http://127.0.0.1:${_MOCK_GITHUB_PORT}`;

// Backend (FastAPI) を E2E 向け env で起動するための環境変数セット。
// - GITHUB_* URL 3 つを mock サーバに向ける (apps/api/app/services/github_oauth.py が参照)
// - APP_ENV=dev のままにする (production にすると安全装置で起動拒否される)
// - GITHUB_CLIENT_ID / SECRET は mock 側では一致チェックしないので dummy で OK
const _API_ENV = {
  APP_ENV: "dev",
  DATABASE_URL: _DATABASE_URL,
  REDIS_URL: _REDIS_URL,
  GITHUB_CLIENT_ID: "e2e-client-id",
  GITHUB_CLIENT_SECRET: "e2e-client-secret",
  GITHUB_REDIRECT_URI: `http://localhost:${_API_PORT}/auth/github/callback`,
  GITHUB_AUTHORIZE_URL: `${_MOCK_GITHUB_ORIGIN}/login/oauth/authorize`,
  GITHUB_TOKEN_URL: `${_MOCK_GITHUB_ORIGIN}/login/oauth/access_token`,
  GITHUB_USER_API_URL: `${_MOCK_GITHUB_ORIGIN}/user`,
  // SESSION_SIGNING_SECRET は dev 既定値で十分 (production チェックは APP_ENV=production でのみ発火)
  SESSION_SIGNING_SECRET: "e2e-only-non-production-secret-do-not-use-anywhere-else",
};

// Mock GitHub サーバを E2E reset 対応で起動するための env。
const _MOCK_GITHUB_ENV = {
  DATABASE_URL: _DATABASE_URL,
  REDIS_URL: _REDIS_URL,
  E2E_RESET_ENABLED: "true",
};

export default defineConfig({
  // testDir: E2E テストの置き場所 (Vitest と分離するため e2e/ に集約)。
  // _mock-github 等の _ プレフィックスディレクトリは Playwright のテスト探索から除外される。
  testDir: "./e2e",
  // testMatch: *.spec.ts のみテストとして認識 (server.py 等の補助ファイルを誤検出しない)。
  testMatch: "**/*.spec.ts",
  // fullyParallel: ファイル間を並列実行。
  // ただし auth テストは DB / Redis を共有するため beforeEach で reset する設計。
  fullyParallel: true,
  // forbidOnly: CI 上で .only テストが残っていれば fail させる安全策。
  forbidOnly: !!process.env.CI,
  // retries: CI でだけ 2 回まで再実行 (フレーキー対策)。ローカルは 0。
  retries: process.env.CI ? 2 : 0,
  // workers: CI では 1 (DB 共有のため衝突回避)、ローカルは並列で良い。
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? "github" : "html",
  use: {
    baseURL: `http://localhost:${_WEB_PORT}`,
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],

  // webServer: テスト起動時に並行起動する補助プロセス群。
  // 3 つのサーバを同時に立てる:
  //   1. Mock GitHub OAuth サーバ (uvicorn) - port 18001
  //   2. Backend FastAPI - port 8000 (env で GITHUB_* URL を mock に向ける)
  //   3. Web Next.js dev - port 3000
  //
  // 各プロセスは url で起動完了を待つ (Playwright が HTTP HEAD をポーリング)。
  // reuseExistingServer は dev でローカル起動済みのサーバを使い回す (CI は新規起動)。
  webServer: [
    {
      // Mock GitHub OAuth サーバ: apps/api の uv env で動かす (python-multipart を含む)。
      command: `cd ../api && uv run python ../web/e2e/_mock-github/server.py --port ${_MOCK_GITHUB_PORT}`,
      url: `${_MOCK_GITHUB_ORIGIN}/_health`,
      timeout: 30_000,
      reuseExistingServer: !process.env.CI,
      env: _MOCK_GITHUB_ENV,
      stdout: "pipe",
      stderr: "pipe",
    },
    {
      // Backend: GITHUB_* URL を mock に向けて起動。
      command: "cd ../api && uv run fastapi dev --port 8000",
      url: `http://localhost:${_API_PORT}/healthz`,
      timeout: 60_000,
      reuseExistingServer: !process.env.CI,
      env: _API_ENV,
      stdout: "pipe",
      stderr: "pipe",
    },
    {
      // Web: Next.js dev サーバ (rewrites で /auth/* を Backend に転送)。
      command: "pnpm run dev",
      url: `http://localhost:${_WEB_PORT}`,
      timeout: 60_000,
      reuseExistingServer: !process.env.CI,
      env: {
        API_PROXY_TARGET: `http://localhost:${_API_PORT}`,
      },
      stdout: "pipe",
      stderr: "pipe",
    },
  ],
});
