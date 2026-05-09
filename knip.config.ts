// Knip 設定ファイル
//
// Knip は「使われていない export / ファイル / 依存パッケージ」を検出する静的解析ツール。
// 役割：
//   - dead code（誰も import していない export / ファイル）の早期検出
//   - 未使用 dependency / devDependency の検出（package.json の腐敗防止）
//   - export 蓄積前に設定を入れることで、後から一括検出 → 削除可否判断のコストを回避
//     （→ ADR 0021「補完ツールを R0 から導入」）
//
// 設計方針（R0 時点）：
//   - apps/web はまだ存在しないため、workspaces 設定は **apps/web 追加時に効くハコ**
//     として先行定義する（先取りで構造を置く設計）。
//   - 個別 plugin は **Knip の自動検出に委ねる** のを基本方針とする。
//     Knip は package.json / 設定ファイルの存在を見て biome / commitlint / syncpack /
//     lefthook / next 等のプラグインを自動有効化するため、明示列挙は不要。
//   - 本ファイル自身（knip.config.ts）は Knip が暗黙的に entry として扱うため明示不要。
//
// 設定形式が `.ts` である理由：
//   - ADR 0022「設定ファイル形式の選定方針（自由選択時は TS > JSONC > YAML）」に従う。
//   - `KnipConfig` 型を `import type` することで、フィールド・リテラル値の typo を保存時に弾ける。
//   - syncpack（.syncpackrc.ts）/ commitlint（commitlint.config.ts）と表記体系が揃う。
//
// 実行：
//   pnpm knip       # 違反検出（CI 用）
//   pnpm knip:fix   # 自動削除可能なものを修正（手動レビュー前提）
import type { KnipConfig } from "knip";

const config: KnipConfig = {
  // workspaces: モノレポ各 workspace に対する個別ルール。
  //   "." はリポジトリルート、"apps/*" / "packages/*" は pnpm-workspace.yaml と対称。
  //   未存在の workspace パターンは Knip が黙って無視するため、R1 以降に追加される
  //   apps/web / apps/api / apps/grading-worker（Go なので対象外）が出現した瞬間に自動的に
  //   解析対象となる。
  workspaces: {
    // ルート：lefthook.yml / commitlint.config.ts / .syncpackrc.ts / biome.jsonc /
    //         tsconfig.json / 本ファイル等が居る。Knip プラグインが大半を自動検出するため、
    //         明示 entry はゼロでよい（commitlint.config.ts は commitlint plugin が拾う）。
    ".": {
      // ignoreDependencies / ignore は R0 時点では空。
      //   誤検知（実際は使われているのに未使用判定される）が発生したらここに追記し、
      //   **その根拠**（どの import / どの間接利用）をコメントで残す運用。
      //   「とりあえず追加」を禁止することで SSoT としての価値を保つ。
    },

    // apps/web（R1 で投入予定の Next.js アプリ）：
    //   App Router の規約ファイル（page / layout / route 等）のみを entry にすることで、
    //   _components/ 等の孤立ファイルを未使用として検出できる。
    //   Next.js プラグインで auto-detect されるが、明示することで意図を SSoT 化する。
    "apps/web": {
      entry: [
        "src/app/**/{page,layout,loading,error,global-error,not-found,route,template,default}.{ts,tsx}",
        "next.config.{js,mjs,ts}",
      ],
      project: ["src/**/*.{ts,tsx}"],
    },

    // apps/api（R1 で投入予定の NestJS アプリ）：
    //   NestJS は src/main.ts が起動 entry。Module 解決は NestJS プラグインが
    //   @Module デコレータの providers / controllers / imports を解析する。
    "apps/api": {
      entry: ["src/main.ts"],
      project: ["src/**/*.ts"],
    },

    // packages/*（共有パッケージ）：
    //   `packages/config`（現状 package.json のみ）/ `packages/prompts`（YAML のみ）/
    //   将来の `packages/shared-types` 等を一律のルールで扱う。
    //   package.json の `exports` フィールドが entry の SSoT になる（Knip 自動検出）。
    "packages/*": {
      entry: ["src/index.{ts,tsx}"],
      project: ["src/**/*.{ts,tsx}"],
    },
  },
};

export default config;
