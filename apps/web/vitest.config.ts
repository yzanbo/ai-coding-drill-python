// Vitest 設定（ADR 0038）。React コンポーネント / フックを jsdom 上で実行する。
// 詳細: https://vitest.dev/config/

import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  // plugins: React の JSX / Fast Refresh を Vitest 経由でも有効化。
  plugins: [react()],
  // resolve.alias: tsconfig.json の `paths` ("@/*": ["./src/*"]) を Vitest 側
  //   （Vite ベースの resolver）にも教える。これが無いとテストファイルから
  //   `@/lib/...` 等の import が解決できず "Failed to resolve import" になる。
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  test: {
    // environment: ブラウザ API（document / window）を再現する jsdom。
    environment: "jsdom",
    // environmentOptions.jsdom.url: jsdom の document.location をテスト用に固定。
    //   既定の "about:blank" だと相対 URL の fetch（例 fetch("/auth/me")）が
    //   解決できず例外になるため、本番と同じ http://localhost:3000 を割り当てる。
    environmentOptions: {
      jsdom: { url: "http://localhost:3000" },
    },
    // globals: describe / it / expect をグローバルに公開（毎ファイル import 不要）。
    globals: true,
    // setupFiles: 各テストの前段で読まれる初期化スクリプト。
    //             @testing-library/jest-dom の matcher（toBeInTheDocument 等）を組込む。
    setupFiles: ["./vitest.setup.ts"],
    // exclude: Playwright（E2E）配下と Next.js のビルド生成物を除外。
    exclude: ["**/node_modules/**", "**/.next/**", "**/e2e/**"],
    // passWithNoTests: テストファイルが 1 つも無くても exit 0 で抜ける。
    //   R0 段階ではテスト未作成のため必要（R1 以降で初テスト追加時にこのフラグは外しても可）。
    passWithNoTests: true,
  },
});
