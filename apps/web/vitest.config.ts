// Vitest 設定（ADR 0038）。React コンポーネント / フックを jsdom 上で実行する。
// 詳細: https://vitest.dev/config/

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  // plugins: React の JSX / Fast Refresh を Vitest 経由でも有効化。
  plugins: [react()],
  test: {
    // environment: ブラウザ API（document / window）を再現する jsdom。
    environment: "jsdom",
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
