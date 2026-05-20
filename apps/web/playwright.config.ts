// Playwright 設定（ADR 0038）。
// R1-1 GitHub OAuth ログインの E2E テスト着地に伴い webServer を本格構成化。
// 詳細: https://playwright.dev/docs/test-configuration
import { defineConfig, devices } from "@playwright/test";
import {
  API_PORT,
  DATABASE_URL,
  MOCK_GITHUB_ORIGIN,
  MOCK_GITHUB_PORT,
  REDIS_URL,
  WEB_PORT,
} from "./e2e/_helpers/constants";

// 機密値は含まないため (E2E 用 dummy CLIENT_ID / SECRET + dev 接続情報) 本ファイル
// で定義してよい。DB / Redis URL は constants.ts 側で env fallback 構造にしているため
// CI / dev で同じ config を使い回せる。

// Backend (FastAPI) を E2E 向け env で起動するための環境変数セット。
// - GITHUB_* URL 3 つを mock サーバに向ける (apps/api/app/services/github_oauth.py が参照)
// - APP_ENV=dev のままにする (production にすると安全装置で起動拒否される)
// - GITHUB_CLIENT_ID / SECRET は mock 側では一致チェックしないので dummy で OK
const _API_ENV = {
  APP_ENV: "dev",
  DATABASE_URL: DATABASE_URL,
  REDIS_URL: REDIS_URL,
  GITHUB_CLIENT_ID: "e2e-client-id",
  GITHUB_CLIENT_SECRET: "e2e-client-secret",
  GITHUB_REDIRECT_URI: `http://localhost:${API_PORT}/auth/github/callback`,
  GITHUB_AUTHORIZE_URL: `${MOCK_GITHUB_ORIGIN}/login/oauth/authorize`,
  GITHUB_TOKEN_URL: `${MOCK_GITHUB_ORIGIN}/login/oauth/access_token`,
  GITHUB_USER_API_URL: `${MOCK_GITHUB_ORIGIN}/user`,
  // SESSION_SIGNING_SECRET は dev 既定値で十分 (production チェックは APP_ENV=production でのみ発火)
  SESSION_SIGNING_SECRET: "e2e-only-non-production-secret-do-not-use-anywhere-else",
};

// Mock GitHub サーバを E2E reset 対応で起動するための env。
const _MOCK_GITHUB_ENV = {
  DATABASE_URL: DATABASE_URL,
  REDIS_URL: REDIS_URL,
  E2E_RESET_ENABLED: "true",
};

export default defineConfig({
  // testDir: E2E テストの置き場所 (Vitest と分離するため e2e/ に集約)。
  // _mock-github 等の _ プレフィックスディレクトリは Playwright のテスト探索から除外される。
  testDir: "./e2e",
  // testMatch: *.spec.ts のみテストとして認識 (server.py 等の補助ファイルを誤検出しない)。
  testMatch: "**/*.spec.ts",
  // fullyParallel: ファイル間を並列実行できる設定だが、下記 workers: 1 で
  // 実質逐次になる。設定自体は将来 worker 数を増やしたときの素直さのため残す。
  fullyParallel: true,
  // forbidOnly: CI 上で .only テストが残っていれば fail させる安全策。
  forbidOnly: !!process.env.CI,
  // retries: CI でだけ 2 回まで再実行 (フレーキー対策)。ローカルは 0。
  retries: process.env.CI ? 2 : 0,
  // workers: ローカル / CI ともに 1 で固定。
  // 理由: 全 spec が同じ DB / Redis を共有していて、各テスト前の resetState が
  // 他テストのログイン状態やジョブを吹き飛ばす衝突 (race) を起こすため。
  // (auth.spec.ts と problem-generation.spec.ts のローカル並走で flaky を確認、issue #66)
  // 並列に戻す案 (spec ごとに DB を作り分け / user 単位で消す) は将来検討。
  workers: 1,
  reporter: process.env.CI ? "github" : "html",
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
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
      command: `cd ../api && uv run python ../web/e2e/_mock-github/server.py --port ${MOCK_GITHUB_PORT}`,
      url: `${MOCK_GITHUB_ORIGIN}/_health`,
      timeout: 30_000,
      reuseExistingServer: !process.env.CI,
      env: _MOCK_GITHUB_ENV,
      stdout: "pipe",
      stderr: "pipe",
    },
    {
      // Backend: GITHUB_* URL を mock に向けて起動。
      command: "cd ../api && uv run fastapi dev --port 8000",
      url: `http://localhost:${API_PORT}/healthz`,
      timeout: 60_000,
      reuseExistingServer: !process.env.CI,
      env: _API_ENV,
      stdout: "pipe",
      stderr: "pipe",
    },
    {
      // Web: Next.js dev サーバ (rewrites で /auth/* を Backend に転送)。
      command: "pnpm run dev",
      url: `http://localhost:${WEB_PORT}`,
      timeout: 60_000,
      reuseExistingServer: !process.env.CI,
      env: {
        API_PROXY_TARGET: `http://localhost:${API_PORT}`,
      },
      stdout: "pipe",
      stderr: "pipe",
    },
  ],
});
