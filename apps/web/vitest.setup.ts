// Vitest 初期化ファイル（vitest.config.ts の setupFiles から読まれる）。
// @testing-library/jest-dom: toBeInTheDocument / toHaveTextContent などの
//   DOM 用 matcher を expect に組み込み、テストの記述を読みやすくする。
import "@testing-library/jest-dom/vitest";
import { afterAll, afterEach, beforeAll } from "vitest";

import { client } from "./src/__generated__/api/client.gen";
import { configureApiClient } from "./src/lib/api/api-client";
import { API_BASE, server } from "./src/test/msw-server";

// configureApiClient: Hey API クライアントに credentials / CSRF interceptor を
//   1 度だけ仕込む（idempotent）。テスト全体で interceptor を効かせるため、
//   ここで起動時に呼び出しておく。
// baseUrl: 本番は同一オリジン rewrites を前提に "" だが、Node + jsdom の
//   `new Request(url, ...)` は相対 URL を解釈できないため、テストでは絶対
//   URL に倒す。MSW handler 側も同じ API_BASE prefix を使う。
configureApiClient();
client.setConfig({ baseUrl: API_BASE });

// ResizeObserver: jsdom には未実装。Radix UI の RadioGroup / Popover などが
//   内部でこの API を呼ぶため、最低限の空実装を global に注入する（テストで
//   サイズ変化を観測する必要は無いので、すべて no-op で問題ない）。
class NoopResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}
if (typeof globalThis.ResizeObserver === "undefined") {
  globalThis.ResizeObserver = NoopResizeObserver as unknown as typeof ResizeObserver;
}

// MSW（API モックサーバ）のライフサイクル管理。
//   beforeAll: 全テスト前に 1 度だけ起動。未登録 URL に fetch すると例外で
//     落としてテストの "サイレントなネットワーク到達" を防ぐ（onUnhandledRequest）。
//   afterEach: 各テスト終了時に handlers をリセット（テスト間の漏れを防ぐ）。
//   afterAll: 全テスト終了時にサーバを停止。
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
