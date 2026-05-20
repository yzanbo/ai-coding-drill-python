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
// Redis は dev (/0) と分離した DB index (/1) を使う。理由はポート分離と同じ:
// E2E の /_test/reset が FLUSHDB するため、dev:all のセッションを巻き添えで消さないよう
// 物理的に名前空間を分ける。DB index 分離は Redis ネイティブ機能で追加インフラ不要。
// 注: Postgres の DB 名分離は docker-compose の init script + Alembic migration の
// 多重実行が必要になるため follow-up issue として別 PR で扱う。
export const DATABASE_URL =
  process.env.DATABASE_URL ??
  "postgresql+asyncpg://postgres:postgres@localhost:5432/ai_coding_drill";
export const REDIS_URL = process.env.REDIS_URL ?? "redis://localhost:6379/1";
