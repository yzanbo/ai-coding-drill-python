// Hey API（@hey-api/openapi-ts）の設定（ADR 0006）。
// apps/api/openapi.json を読んで apps/web/src/__generated__/api/ 配下に
// TS 型 + Zod スキーマ + fetch ベースの HTTP クライアントを生成する。
//
// 形式判断:
//   設定は TypeScript で書く。Hey API は defineConfig を export しており、
//   typo を保存時に IDE / tsc が即時に弾けるため（CLAUDE.md「設定ファイル形式
//   の優先順位」§1: 型 export あり → TS）。
//
// 入力源:
//   ../api/openapi.json は HTTP API 境界 artifact（Pydantic SSoT 由来、
//   apps/api/scripts/export_openapi.py が生成）。HTTP エンドポイントではなく
//   ファイルを読むことで、DB / Redis / OAuth の起動なしに型生成が走る。
//
// 出力先:
//   src/__generated__/api/（コミット対象、Biome / Knip では除外設定済み、
//   tsc --noEmit は対象に含めて型整合性を検証する）。
//
// 実行方法:
//   pnpm exec openapi-ts
//   （mise タスク: mise run web:types-gen）

import { defineConfig } from "@hey-api/openapi-ts";

export default defineConfig({
  // input: 入力 OpenAPI 仕様書のパス。本プロジェクトでは Pydantic から書き出した
  //   apps/api/openapi.json をファイルとして直接参照する。
  input: "../api/openapi.json",

  // output: 生成物の出力先。
  //   このプロジェクトは Biome 採用で Prettier を入れていないため postProcess は
  //   設定しない（Hey API デフォルトの整形のまま出力する）。生成物は biome.jsonc
  //   の overrides で lint / format 対象外、Knip も ignore に追加済み。
  output: {
    path: "./src/__generated__/api",
  },

  // plugins: 生成する成果物の種類。
  //   - @hey-api/client-fetch : 標準 fetch ベースの型付き HTTP クライアント
  //   - @hey-api/sdk          : エンドポイントごとの型付き呼び出し関数群
  //   - @hey-api/typescript   : 純粋な TS 型定義（components/schemas 由来）
  //   - zod                   : 各スキーマに対応する Zod のバリデータ
  plugins: ["@hey-api/client-fetch", "@hey-api/typescript", "@hey-api/sdk", "zod"],
});
