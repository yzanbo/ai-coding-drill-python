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
  WORKER_HEALTH_PORT,
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
  // FRONTEND_BASE_URL: callback 後のリダイレクト先 (Backend が組み立てる絶対 URL)。
  // 既定は :3000 だが E2E では :3001 で Web を立てているので明示的に渡す。
  FRONTEND_BASE_URL: `http://localhost:${WEB_PORT}`,
  // SESSION_SIGNING_SECRET は dev 既定値で十分 (production チェックは APP_ENV=production でのみ発火)
  SESSION_SIGNING_SECRET: "e2e-only-non-production-secret-do-not-use-anywhere-else",
};

// Mock GitHub サーバを E2E reset 対応で起動するための env。
const _MOCK_GITHUB_ENV = {
  DATABASE_URL: DATABASE_URL,
  REDIS_URL: REDIS_URL,
  E2E_RESET_ENABLED: "true",
};

// 採点 Worker を E2E 向け env で起動する（issue #80）。
// - DATABASE_URL: 採点 Worker は pgx ドライバなので SQLAlchemy 形式 `+asyncpg` を除いた
//   素の `postgresql://...` 形式を渡す（apps/workers/grading/internal/config/config.go 参照）。
// - WORKER_HEALTH_ADDR: /healthz を listen させる。dev では未設定で無効化される機能を
//   E2E でのみ有効化することで、dev / E2E の Worker プロセスが port 衝突しないようにする。
// - GOOGLE_API_KEY: provider 初期化時に空文字を弾くため dummy を渡す。grading-flow.spec.ts は
//   採点ジョブしか積まないので実際に LLM は呼ばれない（採点ロジックは sandbox のみ使用）。
// - SANDBOX_TMP_DIR: macOS Docker Desktop で $TMPDIR (/var/folders/...) が File Sharing
//   許可外の環境に当たることがあるため /tmp を明示。CI Linux runner では /tmp が常に共有可。
const _WORKER_ENV = {
  DATABASE_URL: DATABASE_URL.replace("+asyncpg", ""),
  WORKER_HEALTH_ADDR: `:${WORKER_HEALTH_PORT}`,
  GOOGLE_API_KEY: "e2e-dummy-key",
  SANDBOX_TMP_DIR: "/tmp",
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
  //   2. Backend FastAPI - port 8001 (env で GITHUB_* URL を mock に向ける)
  //   3. Web Next.js dev - port 3001
  //
  // dev サーバ (:3000 / :8000) と完全にポートを分けている。理由は constants.ts の
  // API_PORT / WEB_PORT のコメントを参照 (dev backend を E2E backend と取り違える事故防止)。
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
      // Backend: GITHUB_* URL を mock に向けて起動 (E2E 専用ポート)。
      command: `cd ../api && uv run fastapi dev --port ${API_PORT}`,
      url: `http://localhost:${API_PORT}/healthz`,
      timeout: 60_000,
      reuseExistingServer: !process.env.CI,
      env: _API_ENV,
      stdout: "pipe",
      stderr: "pipe",
    },
    {
      // Web: Next.js dev サーバ (rewrites で /auth/* を Backend に転送、E2E 専用ポート)。
      // PORT: pnpm run dev (next dev) は PORT 環境変数を読んで listen ポートを決める。
      // API_PROXY_TARGET: next.config.ts の rewrites 転送先を E2E backend に向ける。
      command: "pnpm run dev",
      url: `http://localhost:${WEB_PORT}`,
      timeout: 60_000,
      reuseExistingServer: !process.env.CI,
      env: {
        PORT: String(WEB_PORT),
        API_PROXY_TARGET: `http://localhost:${API_PORT}`,
        // NEXT_DIST_DIR: dev:all の `next dev` (.next/ にロック) と並行起動するため別 distDir。
        NEXT_DIST_DIR: ".next-e2e",
      },
      stdout: "pipe",
      stderr: "pipe",
    },
    {
      // 採点 Worker (Go): grading-flow.spec.ts が pending → graded を観測するために起動 (issue #80)。
      //   `go run` 初回は ~30s コンパイルが入るので timeout を長めに取る。
      //   サンドボックス image (ai-coding-drill-sandbox:latest) は test:up と並ぶ mise depends で
      //   先に build される (mise.toml の web:e2e 参照)。
      command: "cd ../workers/grading && go run ./cmd/grading",
      url: `http://localhost:${WORKER_HEALTH_PORT}/healthz`,
      timeout: 180_000,
      reuseExistingServer: !process.env.CI,
      env: _WORKER_ENV,
      stdout: "pipe",
      stderr: "pipe",
    },
  ],
});
