// commitlint 設定ファイル。
// commit-msg フック（lefthook 経由で接続）から起動され、
// コミットメッセージが Conventional Commits 規約に沿うかを検証する。
//
// ファイル形式（.mjs を選択した理由）：
//   ADR 0036 拡張方針により、root から TS ツーリング（typescript / tsconfig.json）を排除し
//   apps/web/ に閉じ込める設計を採用。これに伴い root の .ts 設定ファイルは
//   .mjs に置き換える。@commitlint/types の `RuleConfigSeverity` 列挙体に依存できなくなるため、
//   level の値は数値（0=Disabled / 1=Warning / 2=Error）を直接指定する。
//
// extends を使わずインライン展開する理由：
//   ADR 0036 拡張で root の package.json を廃止し、commitlint は mise の `npm:@commitlint/cli`
//   経由でインストールされるが、mise の npm: backend は各 npm パッケージを別 prefix に展開する。
//   このため `extends: ["@commitlint/config-conventional"]` の Node module 解決が失敗する。
//   解決策として、@commitlint/config-conventional のルールセットを本ファイルに直接インライン展開する
//   （conventional rules を踏襲しつつ本プロジェクト固有の上書きを統合した形）。
//
// level 値の凡例：
//   0 = Disabled（ルール無効化）
//   1 = Warning（警告のみ、コミットは通る）
//   2 = Error（コミットを弾く）

/** @type {import("@commitlint/types").UserConfig} */
const config = {
  // ────────────────────────────────────────────────────────────────
  // rules: ルールセット（@commitlint/config-conventional 由来 + 本プロジェクト固有上書き）
  // 値は [level, applicable, value?] の配列形式。
  //   level:      0 = Disabled / 1 = Warning / 2 = Error（commit を弾く）
  //   applicable: 'always' か 'never'
  //   value:      ルール固有の閾値（最大長など）
  // ────────────────────────────────────────────────────────────────
  rules: {
    // ─── @commitlint/config-conventional 由来（インライン展開） ───────────────

    // body-leading-blank: 本文の前に空行が必要（Warning）
    "body-leading-blank": [1, "always"],
    // footer-leading-blank: footer の前に空行が必要（Warning）
    "footer-leading-blank": [1, "always"],
    // footer-max-line-length: footer の 1 行最大文字数
    "footer-max-line-length": [2, "always", 100],
    // type-case: type は lower-case
    "type-case": [2, "always", "lower-case"],
    // type-empty: type 必須
    "type-empty": [2, "never"],
    // subject-empty: subject 必須
    "subject-empty": [2, "never"],
    // subject-full-stop: subject の末尾に "." を置かない
    "subject-full-stop": [2, "never", "."],

    // ─── 本プロジェクト固有の上書き ────────────────────────────────────

    // subject-case:
    //   既定では subject（コロン以降の本文）を kebab-case や lower-case など
    //   英語ケース規約に沿わせるよう要求する。
    //   日本語コミット（例: "feat: 問題生成 API を追加"）は判定対象外とすべきなので
    //   level=Disabled で完全に無効化する。
    "subject-case": [0],

    // header-max-length:
    //   ヘッダー（"type(scope): subject" の 1 行目全体）の最大文字数。
    //   既定 72 は英語前提の値で、日本語では情報量に対して短すぎる
    //   （日本語 1 文字 ≒ 英語 2〜3 文字相当の情報量）。
    //   level=Error のまま上限だけ 100 に緩和。
    "header-max-length": [2, "always", 100],

    // body-max-line-length:
    //   本文（ヘッダーの後の改行以降）の 1 行あたり最大文字数。
    //   既定 100 を 200 に緩和（日本語の情報密度に合わせる）。
    //   level=Error のまま運用し、長すぎる行はコミット時点で弾く。
    "body-max-line-length": [2, "always", 200],

    // type-enum:
    //   許可する type を明示。@commitlint/config-conventional の既定値も
    //   同じ 11 種だが、明示することで「このプロジェクトで何が使えるか」を
    //   config 単独で読み取れるようにする（CLAUDE.md / commitlint 設定間の SSoT）。
    //   level=Error で未許可 type を弾く。
    "type-enum": [
      2,
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
      2,
      "always",
      [
        "web", // apps/web（フロントエンド / Next.js）
        "api", // apps/api（FastAPI / Python バックエンド）
        "worker", // apps/workers/*（Go 採点・問題生成ワーカー、ADR 0040）
        "shared", // OpenAPI / JSON Schema artifact など複数 app から参照される共有 artifact（apps/api/openapi.json / apps/api/job-schemas/ 等。packages/ は廃止）
        "config", // ルート直接配置の tooling 設定ファイル群（mise.toml / lefthook.yml / commitlint.config.mjs 等。packages/config は廃止、ADR 0036）
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
    "scope-empty": [0],
  },
};

export default config;
