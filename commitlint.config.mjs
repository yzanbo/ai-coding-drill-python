// commitlint 設定ファイル。
// commit-msg フック（後で lefthook 経由で接続）から起動され、
// コミットメッセージが Conventional Commits 規約に沿うかを検証する。
// 拡張子 .mjs ＝ ES Modules 形式（export default を直接使うため .js より明示的）

export default {
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
  //   level:      0 = 無効 / 1 = warning / 2 = error（commit を弾く）
  //   applicable: 'always' か 'never'
  //   value:      ルール固有の閾値（最大長など）
  // ────────────────────────────────────────────────────────────────
  rules: {
    // subject-case:
    //   既定では subject（コロン以降の本文）を kebab-case や lower-case など
    //   英語ケース規約に沿わせるよう要求する。
    //   日本語コミット（例: "feat: 問題生成 API を追加"）は判定対象外とすべきなので
    //   level=0 で完全に無効化する。
    "subject-case": [0],

    // header-max-length:
    //   ヘッダー（"type(scope): subject" の 1 行目全体）の最大文字数。
    //   既定 72 は英語前提の値で、日本語では情報量に対して短すぎる
    //   （日本語 1 文字 ≒ 英語 2〜3 文字相当の情報量）。
    //   level=2 (error) のまま上限だけ 100 に緩和。
    "header-max-length": [2, "always", 100],

    // body-max-line-length:
    //   本文（ヘッダーの後の改行以降）の 1 行あたり最大文字数。
    //   既定 100 を 200 に緩和（日本語の情報密度に合わせる）。
    //   level=2 (error) のまま運用し、長すぎる行はコミット時点で弾く。
    "body-max-line-length": [2, "always", 200],

    // type-enum:
    //   許可する type を明示。@commitlint/config-conventional の既定値も
    //   同じ 11 種だが、明示することで「このプロジェクトで何が使えるか」を
    //   config 単独で読み取れるようにする（CLAUDE.md / commitlint 設定間の SSoT）。
    //   level=2 (error) で未許可 type を弾く。
    "type-enum": [
      2,
      "always",
      [
        "feat",     // 新機能追加
        "fix",      // バグ修正
        "docs",     // ドキュメントのみの変更
        "refactor", // 機能変化なしのリファクタ
        "test",     // テスト追加・修正
        "chore",    // ビルド・補助ツール・依存更新等
        "ci",       // CI 設定の変更
        "build",    // ビルドシステム・外部依存の変更
        "perf",     // パフォーマンス改善
        "style",    // フォーマット変更（コード意味は変えない）
        "revert",   // 過去コミットの取り消し
      ],
    ],

    // scope-enum:
    //   scope を CLAUDE.md のブランチ命名規則（feature/<scope>/<name>）と整合させる。
    //   モノレポの作業対象を機械的に把握できる（git log --grep="(api)" 等で絞り込み可）。
    //   level=2 (error) で未許可 scope を弾く。
    "scope-enum": [
      2,
      "always",
      [
        "web",     // apps/web（フロントエンド / Next.js）
        "api",     // apps/api（NestJS API）
        "worker",  // apps/grading-worker（Go 採点ワーカー）
        "shared",  // packages/shared-types, packages/prompts 等の共有パッケージ
        "config",  // packages/config（Biome / tsconfig 等の共有設定）
        "infra",   // infra/（Terraform）
        "docs",    // docs/（要件定義 / ADR）
        "db",      // Drizzle スキーマ・マイグレーション
        "deps",    // 依存パッケージの更新
      ],
    ],

    // scope-empty:
    //   scope なしのコミット（リポジトリ全体に関わる変更）も許容する。
    //   level=0 で「scope 無し」をエラー扱いしないことを明示。
    //   例: "chore: commitlint を導入" のようなリポジトリ横断の変更で scope 不要。
    "scope-empty": [0],
  },
};
