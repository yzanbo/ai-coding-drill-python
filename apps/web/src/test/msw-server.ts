// テスト時の API モックサーバ（MSW、node モード）。
//   Hey API SDK が叩く /auth/* の fetch をテスト中に横取りして任意の
//   レスポンスを返す。handlers は各テストで `server.use(...)` で都度
//   差し替える運用（共有 handler は持たせず、テスト独立性を最優先する）。
//
//   起動・停止・リセットは vitest.setup.ts 側で beforeAll / afterEach /
//   afterAll に登録している（テスト本体には書かない）。
import { setupServer } from "msw/node";

export const server = setupServer();

// API_BASE: jsdom の document.location.origin と同じ値（vitest.config.ts の
//   environmentOptions.jsdom.url で固定）。Hey API クライアントは baseUrl: ""
//   で起動するので、相対 URL の fetch がここに解決される。MSW v2 node モードは
//   絶対 URL の handler が必要なため、テストはこの prefix を使う。
export const API_BASE = "http://localhost:3000";
