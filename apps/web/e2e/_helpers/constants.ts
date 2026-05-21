// E2E 共通定数。playwright.config.ts と spec / fixture の間で port / origin 等を
// 共有するために集約する。値が複数箇所に散らばると port 変更時の更新漏れで
// 原因不明な test 失敗を生むため、ここを単一の参照元にする。

export const MOCK_GITHUB_PORT = 18001;
export const MOCK_GITHUB_ORIGIN = `http://127.0.0.1:${MOCK_GITHUB_PORT}`;

// E2E は dev サーバ (:3000 / :8000) と完全に別ポートで起動する。
// 理由: Playwright の reuseExistingServer:true が「同じポートを listen していれば中身を
// 問わず使い回す」挙動のため、dev:all で先に起動済みの Backend (本物の GitHub OAuth 設定
// を読んだ .env で起動) を E2E 用 mock 設定の Backend と取り違える事故が起きていた。
// dev と E2E でポートを分けると reuseExistingServer は dev プロセスを誤って拾わなくなり、
// 同一 E2E セッション内での再利用 / 開発者が手動で立てた E2E サーバの再利用という本来の
// 役割だけが効くようになる。
export const API_PORT = 8001;
export const WEB_PORT = 3001;

// DATABASE_URL / REDIS_URL: 環境変数で上書き可能。CI と dev で同じ config を
// 使い回せるよう、ハードコードではなく env fallback 構造にしている。
//
// E2E は dev (5432 / 6379) と分離した専用ミドルウェア（docker-compose.e2e.yml）に接続する:
//   - Postgres: ホスト 5433 / DB 名 `ai_coding_drill_e2e`
//   - Redis:    ホスト 6380 / DB index /0（dev とポートで分かれているので index は 0 でよい）
// この分離は issue #86 の長期 fix。/_test/reset の TRUNCATE / FLUSHDB が dev データを
// 巻き添えで消す事故を構造的に防ぐため、ポートと DB 名の両方で物理的に名前空間を分ける。
// /_test/reset 側の安全ガードは DB 名末尾 `_e2e` を要求する allowlist になっている
// （apps/web/e2e/_mock-github/server.py の _ensure_e2e_db_url）。
export const DATABASE_URL =
  process.env.DATABASE_URL ??
  "postgresql+asyncpg://postgres:postgres@localhost:5433/ai_coding_drill_e2e";
export const REDIS_URL = process.env.REDIS_URL ?? "redis://localhost:6380/0";
