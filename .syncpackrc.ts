// ======================================================================
// syncpack 設定（R0-7）
// ======================================================================
//
// 役割：
//   モノレポ内の package.json 群が以下の規約に違反していないか機械検証する。
//   違反があると `pnpm syncpack lint` が非ゼロ終了し CI で落ちる。
//   修正は `pnpm syncpack fix-mismatches` / `pnpm syncpack format` で半自動化可能。
//
// SSoT：
//   このファイルが規約の唯一の真実。CLAUDE.md / ADR 0028 / 06-dev-workflow.md の
//   記述はこのファイルを参照する補助情報に過ぎない。
//
// ファイル形式（.ts を選択した理由）：
//   - 本リポジトリは TypeScript 主体（apps/ / packages/）であり、設定ファイルも
//     TS に揃えるのが一貫性の観点で自然。
//   - syncpack の `RcFile` 型を import することで、各フィールド（versionGroups /
//     semverGroups / pinVersion / policy 等）の typo を config 書き時点で TS が弾く。
//   - エディタ補完で `policy: "sameRange" | "sameRangePinned" | ...` のような
//     リテラル候補が出るため、ドキュメント参照のラウンドトリップが減る。
//   - syncpack v15 は cosmiconfig 経由で `.syncpackrc.ts` を直接認識する（実機検証済み）。
//
// 公式リファレンス: https://syncpack.dev/config/
// ----------------------------------------------------------------------

import type { RcFile } from "syncpack";

const config: RcFile = {
  // versionGroups: 同一パッケージのバージョン揃え方針をパッケージ群ごとに宣言する。
  //   先頭にマッチしたグループのルールが適用されるため、特殊ルールを上に書く順序が重要。
  versionGroups: [
    // ────────────────────────────────────────────────────────────────
    // ルール 1：内部 workspace パッケージは "workspace:*" 固定
    //
    //   pnpm workspaces で `@ai-coding-drill/*` のようなモノレポ内部パッケージを
    //   参照する際、外部 npm レジストリへの誤参照を防ぐため明示的に workspace:*
    //   プロトコルを強制する。
    //   "workspace:*" は「同モノレポ内の同名パッケージの最新を使う」の宣言で、
    //   ビルド時は実際のバージョンに置換される。
    // ────────────────────────────────────────────────────────────────
    {
      label: "Internal workspace packages must use 'workspace:*'",
      packages: ["**"],
      dependencies: ["@ai-coding-drill/**"],
      pinVersion: "workspace:*",
    },

    // ────────────────────────────────────────────────────────────────
    // ルール 2：外部依存は全 workspace で同一バージョンに揃える
    //
    //   モノレポ内の複数 package.json が同じパッケージを別バージョンで持つと、
    //   bundle 重複・型不整合・ESM/CJS 分裂等の事故が発生する。
    //   policy: "sameRange" は「全 workspace で同じ semver 範囲を要求する」設定。
    //   この基本ルールに違反するパッケージは個別の versionGroup で例外指定する。
    // ────────────────────────────────────────────────────────────────
    {
      label: "All external dependencies: same version across workspaces",
      packages: ["**"],
      dependencies: ["**"],
      policy: "sameRange",
    },
  ],

  // semverGroups: semver 範囲指定子（^ / ~ / 完全固定）の統一ルール。
  //   versionGroups がバージョン番号自体を揃え、semverGroups が範囲指定子を揃える。
  semverGroups: [
    // ────────────────────────────────────────────────────────────────
    // ルール 3：semver 範囲指定子は "^" に統一
    //
    //   "^5.4.0"（minor / patch を許容）に統一。
    //   選定理由：
    //     - Dependabot の minor / patch 自動取り込み（ADR 0024）と一貫
    //     - 完全固定（exact pin）は pnpm-lock.yaml で実現済みのため二重管理になる
    //     - "~"（patch のみ）は脆弱性 minor 修正の取り込みが遅れる
    //   workspace:* は semver 範囲ではないので、このルールの対象外（自動的に除外される）。
    // ────────────────────────────────────────────────────────────────
    {
      range: "^",
      packages: ["**"],
      dependencies: ["**"],
    },
  ],

  // ────────────────────────────────────────────────────────────────────
  // syncpack のデフォルト挙動で以下も自動的にカバーされる（明示設定不要）：
  //   - dependencies / devDependencies の重複検知（同一パッケージが両方にある場合）
  //   - package.json のキー順整形（`syncpack format` で実行）
  //   - .repository / .bugs / .author 等のメタフィールド整列
  //
  // 将来追加候補（ADR 0028 の「将来の見直しトリガー」を参照）：
  //   - peerDependencies の範囲整合検証（packages/ が増えてから）
  //   - banned パッケージリスト（lodash 等、事故発生時に追加）
  //   - 特定パッケージの exact pin 強制（react / next 等で互換事故が起きたら）
  //   - workspace 別の例外ルール（複数バージョンが必要な事情が出たら）
  // ────────────────────────────────────────────────────────────────────
};

export default config;
