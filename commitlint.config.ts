// commitlint 設定ファイル。
// commit-msg フック（lefthook 経由で接続）から起動され、
// コミットメッセージが Conventional Commits 規約に沿うかを検証する。
//
// ファイル形式（.ts を選択した理由）：
//   ADR 0028「設定ファイル形式の選定方針」に従い、ツールが型を export している
//   自由選択ケースでは TS を最優先する方針。`@commitlint/types` の `UserConfig` 型を
//   import することで、`type-enum` / `scope-enum` / `level` 等のフィールドと値の
//   typo を config 書き時点で検知できる（保存時に IDE / `tsc` が即時に弾く）。

import type { UserConfig } from "@commitlint/types";
import { RuleConfigSeverity } from "@commitlint/types";

const config: UserConfig = {
  // ────────────────────────────────────────────────────────────────
  // extends: ベースとなるルールセットを継承する。
  // @commitlint/config-conventional は Conventional Commits 公式の
  // 標準ルール一式（type 必須・許可 type リスト・subject 必須など）を提供。
  // 自前で全ルールを書く代わりにこれを土台にして、必要箇所だけ rules で上書きする。
  // ────────────────────────────────────────────────────────────────
  extends: ["@commitlint/config-conventional"],

  // ────────────────────────────────────────────────────────────────
  // rules: 個別ルールの上書き。
  // 値は [level, applicable, value?] の配列形式。
  //   level:      0 = Disabled / 1 = Warning / 2 = Error（commit を弾く）
  //               TS では RuleConfigSeverity 列挙体を使うことで意味を明示できる。
  //   applicable: 'always' か 'never'
  //   value:      ルール固有の閾値（最大長など）
  // ────────────────────────────────────────────────────────────────
  rules: {
    // subject-case:
    //   既定では subject（コロン以降の本文）を kebab-case や lower-case など
    //   英語ケース規約に沿わせるよう要求する。
    //   日本語コミット（例: "feat: 問題生成 API を追加"）は判定対象外とすべきなので
    //   level=Disabled で完全に無効化する。
    "subject-case": [RuleConfigSeverity.Disabled],

    // header-max-length:
    //   ヘッダー（"type(scope): subject" の 1 行目全体）の最大文字数。
    //   既定 72 は英語前提の値で、日本語では情報量に対して短すぎる
    //   （日本語 1 文字 ≒ 英語 2〜3 文字相当の情報量）。
    //   level=Error のまま上限だけ 100 に緩和。
    "header-max-length": [RuleConfigSeverity.Error, "always", 100],

    // body-max-line-length:
    //   本文（ヘッダーの後の改行以降）の 1 行あたり最大文字数。
    //   既定 100 を 200 に緩和（日本語の情報密度に合わせる）。
    //   level=Error のまま運用し、長すぎる行はコミット時点で弾く。
    "body-max-line-length": [RuleConfigSeverity.Error, "always", 200],

    // type-enum:
    //   許可する type を明示。@commitlint/config-conventional の既定値も
    //   同じ 11 種だが、明示することで「このプロジェクトで何が使えるか」を
    //   config 単独で読み取れるようにする（CLAUDE.md / commitlint 設定間の SSoT）。
    //   level=Error で未許可 type を弾く。
    "type-enum": [
      RuleConfigSeverity.Error,
      "always",
      [
        "feat", // 新機能追加
        "fix", // バグ修正
        "docs", // ドキュメントのみの変更
        "refactor", // 機能変化なしのリファクタ
        "test", // テスト追加・修正
        "chore", // ビルド・補助ツール・依存更新等
        "ci", // CI 設定の変更
        "build", // ビルドシステム・外部依存の変更
        "perf", // パフォーマンス改善
        "style", // フォーマット変更（コード意味は変えない）
        "revert", // 過去コミットの取り消し
      ],
    ],

    // scope-enum:
    //   scope を CLAUDE.md のブランチ命名規則（feature/<scope>/<name>）と整合させる。
    //   モノレポの作業対象を機械的に把握できる（git log --grep="(api)" 等で絞り込み可）。
    //   level=Error で未許可 scope を弾く。
    "scope-enum": [
      RuleConfigSeverity.Error,
      "always",
      [
        "web", // apps/web（フロントエンド / Next.js）
        "api", // apps/api（FastAPI / Python バックエンド）
        "worker", // apps/grading-worker（Go 採点ワーカー）
        "shared", // packages/prompts 等の共有パッケージ（packages/shared-types は不採用、ADR 0006 で OpenAPI 単一伝送路化）
        "config", // ルート直接配置の tooling 設定ファイル群（biome.jsonc / tsconfig.json / mise.toml / lefthook.yml 等。packages/config は廃止、ADR 0036）
        "infra", // infra/（Terraform）
        "docs", // docs/（要件定義 / ADR）
        "db", // DB スキーマ・マイグレーション（SQLAlchemy 2.0 + Alembic、ADR 0037）
        "deps", // 依存パッケージの更新（production / github-actions）。Dependabot が production 依存・github-actions 更新時に自動付与
        "deps-dev", // 依存パッケージの更新（devDependencies）。Dependabot が prefix-development + include:scope で自動付与
      ],
    ],

    // scope-empty:
    //   scope なしのコミット（リポジトリ全体に関わる変更）も許容する。
    //   level=Disabled で「scope 無し」をエラー扱いしないことを明示。
    //   例: "chore: commitlint を導入" のようなリポジトリ横断の変更で scope 不要。
    "scope-empty": [RuleConfigSeverity.Disabled],
  },
};

export default config;
