// Knip 設定（ADR 0021）。未使用の export / file / dependency を検出する。
// patterns は frontend.md のディレクトリ規約（src/app / components / hooks / lib）に揃え、
// 該当ディレクトリは R1 以降で順次追加される（R0 時点では src/app のみ実在）。
// 未到達の patterns は knip が "Configuration hints" を出すが exit 0、ノイズは
// `--no-config-hints` で抑制（mise.toml の web:knip 側）する運用。
// 詳細: https://knip.dev/reference/configuration
import type { KnipConfig } from "knip";

const config: KnipConfig = {
  // entry: 解析の起点（これらから import を辿って到達可能なものを「使用中」と判定）。
  //   App Router の規約ファイルのみを entry にすることで、_components/ 配下等の孤立コードを検出できる。
  //   Next.js に新しい規約ファイルが追加された際はこのパターンも更新すること。
  entry: [
    "src/app/**/{page,layout,loading,error,global-error,not-found,route,template,default}.{ts,tsx}",
  ],
  // project: 解析対象の全ファイル（entry から参照されていないファイルは未使用と判定）。
  //   frontend.md のディレクトリ規約と一致させる。__generated__/ は ignore 側で扱うため
  //   project には含めない（解析の起点・対象から完全に外す）。
  project: [
    "src/app/**/*.{ts,tsx}",
    "src/components/**/*.{ts,tsx}",
    "src/hooks/**/*.{ts,tsx}",
    "src/lib/**/*.{ts,tsx}",
  ],
  // ignore: 解析から除外するファイル（未使用判定さえ走らせない）。
  //   - src/__generated__/**    : Hey API 生成コード（ADR 0006、R1 以降。frontend.md 実装契約で配置確定）
  //   - src/components/ui/**    : shadcn/ui コンポーネント（規約上 lint しない、R1 以降）
  //   - src/lib/utils.ts        : shadcn/ui の cn() ヘルパー（lib 直下の単発ファイル）
  //   - **/*.stories.{ts,tsx}   : Storybook ストーリー（採用時に発火）
  ignore: [
    "src/__generated__/**",
    "src/components/ui/**",
    "src/lib/utils.ts",
    "**/*.stories.{ts,tsx}",
  ],
  // ignoreDependencies: 静的解析で検出されない / 間接的に使う依存。
  //   - tailwindcss                 : @tailwindcss/postcss プラグイン経由でだけ参照
  //   - @testing-library/react      : テスト追加時に使う（R0 ではテスト未作成）
  //   - @testing-library/user-event : 同上
  ignoreDependencies: ["tailwindcss", "@testing-library/react", "@testing-library/user-event"],
};

export default config;
