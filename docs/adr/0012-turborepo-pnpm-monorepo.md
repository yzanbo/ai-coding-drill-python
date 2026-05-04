# 0012. モノレポツールに Turborepo + pnpm workspaces を採用

- **Status**: Accepted
- **Date**: 2026-04-25
- **Decision-makers**: 神保 陽平

## Context（背景・課題）

複数アプリ（Next.js / NestJS / Go ワーカー、将来 Python パイプライン）と共有パッケージ（型・スキーマ・プロンプト）を 1 つのリポジトリで管理する必要がある。

- パッケージ数想定：
  - **MVP（Phase 1〜5）**：5〜10 個（apps × 3、packages × 数個、infra）
  - **Phase 7（RAG・評価パイプライン追加後）**：8〜12 個（Python アプリ × 1〜2 を追加）
- 言語構成（[ADR 0010](./0010-phased-language-introduction.md)）：
  - MVP：TypeScript + Go
  - Phase 7：上記 + Python
- 共有スキーマ（JSON Schema）を TS / Go / Python の 3 言語で参照したい
- 個人開発・ポートフォリオ規模、過剰なツールは避けたい
- CI 時間を抑えたい

## Decision（決定内容）

**Turborepo + pnpm workspaces** を採用する。

- **pnpm workspaces**：JS/TS パッケージ間の依存解決とリンク（土台）
- **Turborepo**：ビルド順序・並列実行・キャッシュ・Vercel リモートキャッシュ（上層）
- **Go の統合**：`apps/grading-worker/` 配下に独立した `go.mod` として配置、Turborepo は `package.json` の script から `go build` を呼ぶ素朴な統合
- **Python の統合（Phase 7）**：`apps/rag-worker/` などに `pyproject.toml` を置き、依存管理は `uv` で行う。Turborepo は `package.json` の script から `uv run` / `uv build` を呼ぶコマンド実行レベルの統合に留める
- **共有スキーマ**：`packages/shared-types/` に JSON Schema を置き、TS（zod-from-json-schema 等）・Go（quicktype 等）・Python（datamodel-code-generator 等）で型を自動生成

### 想定ディレクトリ構成

```
ai-coding-drill/
├── apps/
│   ├── web/                    ← Next.js（MVP）
│   │   ├── e2e/                ← Playwright E2E
│   │   ├── Dockerfile
│   │   └── package.json
│   ├── api/                    ← NestJS（MVP）
│   │   ├── src/
│   │   │   ├── auth/
│   │   │   ├── problems/
│   │   │   ├── generation/
│   │   │   ├── grading/
│   │   │   └── observability/
│   │   ├── drizzle/            ← Drizzle ORM スキーマ + マイグレーション
│   │   ├── test/fixtures/
│   │   ├── Dockerfile
│   │   └── package.json
│   ├── grading-worker/         ← Go（MVP、独立した go.mod）
│   │   ├── cmd/
│   │   ├── internal/
│   │   ├── sandbox/            ← 採点用コンテナ Dockerfile
│   │   │   ├── Dockerfile
│   │   │   └── package.json    ← Vitest + tsx
│   │   ├── go.mod
│   │   ├── Dockerfile
│   │   └── package.json
│   ├── rag-worker/             ← Python（Phase 7、pyproject.toml + uv）
│   └── eval-pipeline/          ← Python バッチ（Phase 7）
├── packages/
│   ├── config/
│   │   ├── biome-config/       ← 共有 biome.json
│   │   └── tsconfig/           ← 共有 tsconfig
│   ├── shared-types/           ← JSON Schema を SSoT、各言語向け型生成
│   │   ├── schemas/            ← JSON Schema（SSoT）
│   │   ├── generated/          ← ts/（コミット）, go/（gitignore）, python/（gitignore）
│   │   └── scripts/
│   └── prompts/                ← YAML プロンプト
├── notebooks/                  ← Phase 7、Jupyter
├── infra/                      ← Terraform
│   ├── modules/                ← network / db / ecs / worker / monitoring
│   └── envs/                   ← staging / production
├── docs/
│   ├── requirements/
│   └── adr/
├── .github/workflows/          ← GitHub Actions
├── .env.example                ← 共有環境変数（DB URL 等）
├── pnpm-workspace.yaml
├── turbo.json
├── biome.json                  ← ルート Biome 設定
├── docker-compose.yml
├── README.md
└── SYSTEM_OVERVIEW.md
```

- 各アプリ直下に `Dockerfile` を配置（ビルドコンテキスト最小化、アプリごとに独立 CI ビルド可能）
- 共有環境変数はルートの `.env.example`、アプリ固有変数は各アプリ直下の `.env.example`
- 共有スキーマは [ADR 0014](./0014-json-schema-as-single-source-of-truth.md) に従い JSON Schema を SSoT として各言語向け型を自動生成
- TS のコード品質ツールは [ADR 0013](./0013-biome-for-tooling.md) に従い Biome に統一

## Alternatives Considered（検討した代替案）

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| Turborepo + pnpm workspaces | （採用） | — |
| Nx + pnpm workspaces | 大規模 JS/TS モノレポの本格派、Python プラグインあり | 学習コスト高、独自概念多数（Project / Target / Executor / Generator）、本プロジェクト規模では過剰 |
| pnpm workspaces のみ | パッケージマネージャ標準機能のみ | ビルドキャッシュなし、並列実行が手動、CI が遅くなる |
| Bazel | 多言語ネイティブサポート（TS / Go / Python が同列） | 学習コスト極大、セットアップに数週間、Phase 7 規模でも過剰、ポートフォリオで「なぜ？」が問われる |
| Lerna | 古参 | 2022 年以降 Nx 傘下、独立した進化なし |
| Rush | エンタープライズ向け | 個人開発で採用例少、コミュニティ小 |
| ポリレポ（リポジトリ分割） | 各アプリ独立リポジトリ | 共有スキーマの同期が手動、PR が複数リポジトリにまたがる、個人開発で運用負荷高 |

## Consequences（結果・トレードオフ）

### 得られるもの
- セットアップが容易（`pnpm dlx create-turbo` で雛形即完成）
- インクリメンタルビルドと並列実行で CI 時間を 50〜70% 削減見込み
- Vercel リモートキャッシュ無料連携で複数 PR・複数開発者間でキャッシュ共有
- TS のローカルパッケージを `workspace:*` 参照で同期不要
- Go・Python は薄い統合（コマンド実行レベル）で、それぞれの言語ネイティブのツール（`go mod`, `uv`）を活かせる
- 「規模に応じた選定」「言語ごとに適切な統合粒度」をポートフォリオで語れる
- 学習コストが低く、実装に集中できる

### 失うもの・受容するリスク
- Nx ほどの厳格なモジュール境界制約・依存ポリシー機能はない
- Bazel ほどの多言語深統合はない：
  - Go / Python は本質的に Turborepo の "外" で動く（依存解析・キャッシュは限定的）
  - Python の依存変更で TS 側が無駄に再ビルドされる可能性は低いが、逆も同様
- Turborepo の独自機能（リモートキャッシュ等）に部分的に依存
- Phase 7 で Python の依存が複雑化した場合、Turborepo の管理外で運用される領域が増える可能性

### 将来の見直しトリガー
- パッケージ数が 30 を超え、依存グラフ可視化や厳格な境界制約が必要になった場合 → **Nx へ移行を検討**
- Python の依存・ビルドパイプラインが複雑化し、薄い統合では足りなくなった場合 → **Python 側だけ独立リポジトリ化**または**Bazel 移行**を検討
- 言語が 4 つ以上に増えた、または各言語の深い相互依存が発生した場合 → **Bazel 移行**を検討

## References

- [05-runtime-stack.md: モノレポ構成](../requirements/2-foundation/05-runtime-stack.md)
- [ADR 0010: 言語の段階導入](./0010-phased-language-introduction.md)
- [Turborepo 公式](https://turborepo.com/)
- [pnpm workspaces 公式](https://pnpm.io/workspaces)
- [uv 公式](https://docs.astral.sh/uv/)
