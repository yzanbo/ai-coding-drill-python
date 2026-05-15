// Knip 設定（ADR 0021）。未使用の export / file / dependency を検出する。
// 別プロジェクト axon（/Users/jinboyouhei/Documents/site/axon/frontend/knip.config.ts）の構成を踏襲。
// R0 時点では src/app しか存在しないため、components/ hooks/ lib/ 関連の patterns / ignore は
// 当該ディレクトリ作成時（R1 以降）に axon の構成へ拡張する。
// 詳細: https://knip.dev/reference/configuration
import type { KnipConfig } from "knip";

const config: KnipConfig = {
  // entry: 解析の起点となるファイル。これらから import を辿って到達可能なものを「使用中」と判定。
  //   Next.js App Router の規約ファイル（page / layout / loading / error / not-found / route /
  //   template / default / global-error）だけを entry にすることで、_components/ や _hooks/ 配下の
  //   孤立コードを未使用として検出できる。新しい規約ファイルが Next.js に追加されたらここも更新する。
  entry: [
    "src/app/**/{page,layout,loading,error,global-error,not-found,route,template,default}.{ts,tsx}",
  ],
  // project: 解析対象。R1 で src/components / src/hooks / src/lib を追加するときに拡張する。
  project: ["src/app/**/*.{ts,tsx}"],
  // ignoreDependencies: 静的解析で検出されない / 間接的に使う依存。
  //   - tailwindcss             : @tailwindcss/postcss 経由でだけ参照
  //   - @testing-library/react  : テスト追加時に使う（R0 ではテスト未作成）
  //   - @testing-library/user-event : 同上
  ignoreDependencies: ["tailwindcss", "@testing-library/react", "@testing-library/user-event"],
};

export default config;
