// E2E 共通定数。playwright.config.ts と spec / fixture の間で port / origin 等を
// 共有するために集約する。値が複数箇所に散らばると port 変更時の更新漏れで
// 原因不明な test 失敗を生むため、ここを単一の参照元にする。

export const MOCK_GITHUB_PORT = 18001;
export const MOCK_GITHUB_ORIGIN = `http://127.0.0.1:${MOCK_GITHUB_PORT}`;

export const API_PORT = 8000;
export const WEB_PORT = 3000;

// DATABASE_URL / REDIS_URL: 環境変数で上書き可能。CI と dev で同じ config を
// 使い回せるよう、ハードコードではなく env fallback 構造にしている。
export const DATABASE_URL =
  process.env.DATABASE_URL ??
  "postgresql+asyncpg://postgres:postgres@localhost:5432/ai_coding_drill";
export const REDIS_URL = process.env.REDIS_URL ?? "redis://localhost:6379/0";
