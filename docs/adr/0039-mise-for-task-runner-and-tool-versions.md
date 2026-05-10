# 0039. タスクランナー兼 tool 版数管理に mise を採用

- **Status**: Accepted
- **Date**: 2026-05-09
- **Decision-makers**: 神保 陽平

## Context（背景・課題）

[ADR 0033](./0033-backend-language-pivot-to-python.md) のバックエンド Python pivot と [ADR 0036](./0036-frontend-monorepo-pnpm-only.md) の Turborepo 不採用により、以下のギャップが生じた。

- **3 言語ポリグロット構成**（Python / TS / Go）の各レイヤで使うコマンドが言語別に分散：
  - Python（Backend）：`uv run pytest` / `uv run alembic upgrade head` / `uv run ruff check` 等を `apps/api/` で実行
  - TS（Frontend）：`pnpm --filter @ai-coding-drill/web dev` 等を root で実行
  - Go（Worker）：`go test ./...` を `apps/workers/grading/` で実行
- **`cd` を毎回挟む運用は非効率**で、root から横断コマンドを叩ける仕組みが欲しい
- **ツール版数管理が散逸**：Python 版数（`.python-version`）/ Node 版数（`.nvmrc`）/ Go 版数 / `uv` / `pnpm` のバージョンが各々別ファイル / 別ツール（`pyenv` / `nvm` / `goenv`）で管理されると、ローカルと CI の再現性が脆くなる
- **Turborepo の役割が空席**：[ADR 0036](./0036-frontend-monorepo-pnpm-only.md) で Frontend の Turborepo を不採用にしたため、横断タスク実行（`turbo run lint` / `turbo run test` 等）の代替手段が必要

選定にあたっての要請：

- **言語非依存**：Python / TS / Go のコマンドを 1 ファイルから呼び出せる
- **monorepo 対応**：単一エントリポイントから各レイヤのタスクを起動でき、横断タスク（全言語 lint / test）も書ける
- **再現性**：tool 版数の固定機構を一元化、ローカルと CI で同じバージョンが使われる
- **規模適合**：Bazel / Pants 等のフルスケール polyglot build system は本プロジェクト規模（小〜中、1 人開発）に対し過剰

判断のために参照した情報源：

- [Mise: Monorepo Tasks - Hacker News](https://news.ycombinator.com/item?id=45491621)
- [Introducing Monorepo Tasks - mise Discussion #6564](https://github.com/jdx/mise/discussions/6564)
- [Monorepo Tasks - mise-en-place 公式](https://mise.jdx.dev/tasks/monorepo.html)
- [Taskfile vs Just vs Make - mylinux.work](https://mylinux.work/guides/taskfile-vs-just-vs-make/)

## Decision（決定内容）

**`mise`** を採用し、以下 3 つの役割をリポジトリルートに集約する：

1. **タスクランナー**：`mise.toml` に各レイヤのタスク（dev / test / lint / typecheck / migrate 等）を定義、`mise run <task>` で root から起動
2. **tool 版数管理**：Python / Node / Go / uv / pnpm 等のバージョンを `mise.toml` の `[tools]` セクションで宣言。`pyenv` / `nvm` / `goenv` は採用しない（mise に集約）
3. **環境変数管理**：開発時の環境変数（`DATABASE_URL` 等）を `.env` から読み込む `mise` 標準機構を使う

設定 SSoT：

- **`mise.toml`**（リポジトリルート）：tool 版数 + 横断タスクを記述
- **各 app 配下の `.mise.toml`**（必要に応じて）：app 固有のタスクを記述。Monorepo Tasks 機能で root から `mise run //api:test` 形式で呼び出し可能

[ADR 0022 設定ファイル形式優先順位](./0022-config-file-format-priority.md) の Tier 2 ecosystem 慣習として `mise.toml`（TOML）を採用。

## Why（採用理由）

### 1. Turborepo 不採用で生じた orchestration の空席を埋める設計思想

- mise は 2026 年に **Monorepo Tasks 機能**を追加し、「**mise を既に使うチームに対し Nx / Turborepo を置き換える**」と公式 Discussion で明言（[mise Discussion #6564](https://github.com/jdx/mise/discussions/6564)）
- [ADR 0036](./0036-frontend-monorepo-pnpm-only.md) で Turborepo を不採用にした文脈と完全に対応：失われた横断 orchestration 機能を、より広い役割（tool 版数管理 + env 管理 + タスク）で代替

### 2. tool 版数 + タスクが 1 ツールで完結（pyenv / nvm / goenv の統合）

- `.python-version` / `.nvmrc` / Go バージョン定義 / `uv` / `pnpm` のバージョン pin が **`mise.toml` 1 ファイルに集約**
- 「`uv run` する前の venv activate を忘れる」「Node の version mismatch でローカルが動かない」等の事故が構造的に消える
- ローカル / CI / 新規参画者の環境差異がゼロに近づく
- Astral 系（uv / ruff、→ [ADR 0020](./0020-python-code-quality.md) / [ADR 0035](./0035-uv-for-python-package-management.md)）とも衝突しない：mise はメタ層、uv は Python パッケージ層で役割分離

### 3. 言語非依存で 3 言語ポリグロット構成（[ADR 0003](./0003-phased-language-introduction.md)）に適合

- Python / TS / Go のコマンドを `mise.toml` の `[tasks.*]` に同居させられる
- `mise run lint` で全言語の lint を直列 / 並列実行（`depends` で依存関係定義）
- `cd` 不要、root から全タスク起動

### 4. 環境変数の自動ロードで「正しい tool + env で起動」を保証

- `mise` がディレクトリ移動時に自動で `[env]` セクション・`.env` ファイル・指定 tool 版数をロード
- `direnv` 相当の機能を組込で提供、別ツール導入不要

### 5. 規模適合：Bazel / Pants 級のフルスケール polyglot build system は不要

- mise はあくまで「タスク呼び出し + 環境セットアップ」のメタ層、build キャッシュ・分散ビルド等の重機能は持たない
- 本プロジェクト規模（小〜中、1 人開発）には mise の軽量さが最適
- 将来チーム / CI 規模が拡大しても mise の monorepo tasks で当面対応可能

### 6. CI 統合が容易

- GitHub Actions の公式 setup-action（`jdx/mise-action`）で 1 ステップ導入
- CI で `mise install` → `mise run ci` の流れで「ローカルと完全同一の環境」が再現可能
- [ADR 0031](./0031-ci-success-umbrella-job.md) の `ci-success` umbrella ジョブの各 needs（lint / typecheck / test 等）が `mise run <task>` で統一できる

## Alternatives Considered（検討した代替案）

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| **mise（採用）** | tool 版数 + タスク + env 管理を統合した polyglot 向けメタツール | — |
| `just` | Rust 製、簡潔な構文の command runner | **monorepo 向けに設計されていない**（[mylinux.work](https://mylinux.work/guides/taskfile-vs-just-vs-make/)）：multiple justfile で unified task discovery / wildcards 不可。tool 版数管理機能なし、別途 `pyenv` / `nvm` / `goenv` を併用する必要があり散逸 |
| Makefile | OS 標準、追加ツール不要 | tab/space 事故、`.PHONY` ボイラープレート、引数渡しが冗長。tool 版数管理機能なし。**1976 年設計**で polyglot monorepo の現代的要請に対応していない |
| Taskfile（go-task） | YAML ベースの Make 代替、checksum / 並列実行内蔵 | YAML のインデント事故、コメント運用が `mise` の TOML より弱い。tool 版数管理機能なし。`mise` の monorepo 対応に劣る |
| `pnpm` scripts のまま（root `package.json` から `uv run` / `go test` を shell out） | 追加ツール不要 | TS Frontend 限定の `pnpm` が root を支配する**概念的な歪み**（[ADR 0036](./0036-frontend-monorepo-pnpm-only.md) で pnpm を Frontend 用途と確定したばかり）。tool 版数管理機能なし |
| Turborepo 復活 | TS 側だけは戻す | [ADR 0036](./0036-frontend-monorepo-pnpm-only.md) で価値ドライバが効かないと判断したばかり、polyglot 横断機能は持たないため空席は埋まらない |
| Bazel / Pants | 大規模 polyglot 向け build system | 本プロジェクト規模（小〜中）に対し**過剰**、CLAUDE.md「規模に応じた選定」原則違反。学習コストが mise の数倍 |
| `direnv` + npm scripts + 別途 `pyenv` / `nvm` / `goenv` | 既存 OSS の組み合わせ | 4 ツール散逸、CLAUDE.md「言語標準ツール 1 本に揃える」原則違反。再現性も弱い |

## Consequences（結果・トレードオフ）

### 得られるもの

- **`cd` 不要の root 起動**：`mise run api:db-migrate` 等が root から 1 コマンドで叩ける、開発体験が大幅改善
- **tool 版数の単一 SSoT**：`mise.toml` 1 ファイルに Python / Node / Go / uv / pnpm のバージョンが集約、ローカル / CI / 新規参画者で完全再現
- **環境差異事故ゼロ**：mise が自動で正しい tool 版数 + env をロード、「Python が違う」「Node が違う」事故が構造的に消える
- **ポートフォリオ価値**：「Turborepo を入れず mise で polyglot monorepo を運用する判断」を**規模適合の意思決定として説明可能**
- **Turborepo 代替の整合性**：[ADR 0036](./0036-frontend-monorepo-pnpm-only.md) と一対の判断として首尾一貫

### 失うもの・受容するリスク

- **mise インストールが新規参画者の前提**：`brew install mise` / `curl https://mise.run | sh` を README に明記する必要
- **TOML 構文の学習コスト**：`just` の最簡構文よりは冗長
- **mise の Monorepo Tasks 機能は 2026 新機能**：成熟度はまだ 1 年程度、`mise` 本体は v2 系で安定だが Monorepo Tasks 部分の breaking change リスクは残る
- **エディタ統合は限定的**：VS Code 拡張はあるが、`tsconfig.json` のような first-class IDE サポートには劣る

### 将来の見直しトリガー

- **mise の Monorepo Tasks 機能が停滞・後退した場合** → `just` + 別途 `mise` の tools 機能のみ採用、または `Taskfile` 移行を検討
- **チーム規模が拡大し本格的な build cache / 分散ビルドが必要になった場合** → Nx / Turborepo / Bazel 級への乗り換えを再評価（極めて低確率）
- **Astral が tool 版数管理機能を uv に統合した場合** → mise の tool 部分を uv に寄せ、mise を tasks のみの利用に縮小する可能性

## References

- [ADR 0036: Frontend モノレポ管理を pnpm workspaces のみに縮小](./0036-frontend-monorepo-pnpm-only.md)（Turborepo 不採用 → mise が orchestration 空席を埋める対の判断）
- [ADR 0035: Python のパッケージ管理に uv を採用](./0035-uv-for-python-package-management.md)（mise が uv のバージョンを管理する関係）
- [ADR 0033: バックエンドを Python に pivot](./0033-backend-language-pivot-to-python.md)（polyglot 構成の前提）
- [ADR 0003: レイヤ別ポリグロット構成](./0003-phased-language-introduction.md)（3 言語構成の前提）
- [ADR 0031: ci-success umbrella ジョブ](./0031-ci-success-umbrella-job.md)（CI で `mise run <task>` を統一呼び出しする前提）
- [ADR 0022: 設定ファイル形式優先順位](./0022-config-file-format-priority.md)（mise.toml の Tier 2 ecosystem 慣習）
- [mise 公式](https://mise.jdx.dev/)
- [mise Monorepo Tasks](https://mise.jdx.dev/tasks/monorepo.html)
- [jdx/mise-action（GitHub Actions）](https://github.com/jdx/mise-action)
