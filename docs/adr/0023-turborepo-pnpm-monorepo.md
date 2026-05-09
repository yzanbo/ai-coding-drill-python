# 0023. モノレポツールに Turborepo + pnpm workspaces を採用

- **Status**: Accepted
- **Date**: 2026-04-25
- **Decision-makers**: 神保 陽平

## Context（背景・課題）

複数アプリ（Next.js / NestJS / Go ワーカー、将来 Python パイプライン）と共有パッケージ（型・スキーマ・プロンプト）を 1 つのリポジトリで管理する必要がある。

- パッケージ数想定：
  - **MVP（R1〜R5）**：5〜10 個（apps × 3、packages × 数個、infra）
  - **R7（RAG・評価パイプライン追加後）**：8〜12 個（Python アプリ × 1〜2 を追加）
- 言語構成（[ADR 0003](./0003-phased-language-introduction.md)）：
  - MVP：TypeScript + Go
  - R7：上記 + Python
- 共有スキーマ（JSON Schema）を TS / Go / Python の 3 言語で参照したい
- 個人開発・ポートフォリオ規模、過剰なツールは避けたい
- CI 時間を抑えたい

## Decision（決定内容）

**Turborepo + pnpm workspaces** を採用する。

- **pnpm workspaces**：JS/TS パッケージ間の依存解決とリンク（土台）
- **Turborepo**：ビルド順序・並列実行・キャッシュ・Vercel リモートキャッシュ（上層）
- **Go の統合**：`apps/grading-worker/` 配下に独立した `go.mod` として配置、Turborepo は `package.json` の script から `go build` を呼ぶ素朴な統合
- **Python の統合（R7）**：`apps/rag-worker/` などに `pyproject.toml` を置き、依存管理は `uv` で行う。Turborepo は `package.json` の script から `uv run` / `uv build` を呼ぶコマンド実行レベルの統合に留める
- **共有スキーマ**：`packages/shared-types/` に JSON Schema を置き、TS（zod-from-json-schema 等）・Go（quicktype 等）・Python（datamodel-code-generator 等）で型を自動生成

## Why（採用理由）

ビルドオーケストレーション層（Turborepo）とパッケージマネージャ層（pnpm）を分けて根拠を整理する。

### なぜ Turborepo か（Nx / Bazel / pnpm 単体ではなく）

1. **インクリメンタルビルド（コンテンツハッシュベースのキャッシュ）**
   - 入力ファイル・依存・環境変数のハッシュをキーに成果物をキャッシュし、変更がないパッケージは再ビルドをスキップ
   - 型修正 1 行で 10 パッケージ全てがビルドされる無駄を排除でき、CI 時間が顕著に縮む
2. **依存グラフベースの並列実行**
   - `turbo.json` の `dependsOn` から依存グラフを構築し、依存しないタスクを CPU コア数まで自動並列化
   - パッケージ間の並列に加え、`lint` / `typecheck` / `build` のような独立タスクも同時実行
3. **Vercel リモートキャッシュによるチーム・CI 横断の成果物共有**
   - ローカルでビルドした成果物をクラウドに保存し、別マシン・別 PR・CI からも同じハッシュなら復元可能
   - 個人利用は無料、誰かが一度ビルドすれば全員がスキップできる
   - 「同じ内容のビルドを世界で 1 回しかやらない」状態を CI レベルで実現
4. **学習コストが低く、設定が `turbo.json` 1 ファイルに収まる**
   - Nx のような独自概念（Project / Target / Executor / Generator）が無く、`package.json` の script をそのままラップする素朴な構造
   - 「規模に応じた選定」の原則に合致し、ポートフォリオでも判断根拠を簡潔に説明できる
5. **多言語との薄い統合（Go / Python に対する非侵襲性）**
   - `package.json` の script から `go build` や `uv run` を呼ぶだけのコマンド実行レベル統合
   - Go は `go.mod` / Go module キャッシュ、Python は `uv` の lock を併用し、言語ネイティブのツールを活かせる
   - Bazel のように全言語を 1 つのビルドシステムに巻き込む必要がない
6. **pnpm との親和性が事実上の標準**
   - Vercel が両方を開発・推奨しており、`create-turbo` のテンプレートが pnpm 前提
   - workspaces の依存グラフをそのままタスクグラフ計算に流用でき、設定の重複が少ない

### なぜ pnpm か（npm / yarn / bun ではなく）

1. **`workspace:` プロトコルでローカル参照が明示的**
   - `"@ai-coding-drill/shared-types": "workspace:*"` と書けばモノレポ内のローカルパッケージを symlink で直結し、npm レジストリへのフォールバックが起きない
   - npm の workspaces はバージョン指定で代用するため、ローカル参照かレジストリ参照かが曖昧になる
   - publish しないモノレポ専用パッケージにとって「レジストリを見ない」と明言できる安全性は重要
2. **厳格な依存解決（幻の依存の防止）**
   - npm / yarn classic は hoisting でフラットに展開するため、`package.json` に書いていない依存も偶然 import できてしまう（"phantom dependency"）
   - pnpm は symlink ベースの隔離された `node_modules/` を作るため、宣言していない依存は import 段階でエラーになる
   - モノレポでパッケージ間の責務境界を保つために本質的に効く
3. **ディスク効率と install 速度**
   - グローバルストア（`~/.pnpm-store/`）+ hard link 方式により、複数プロジェクト・複数ブランチで同じ依存が重複展開されない
   - `pnpm install` は npm の概ね 2 倍以上速く、CI のキャッシュミス時の差が大きい
4. **Turborepo との組み合わせが事実上の標準**
   - Vercel（Turborepo の開発元）自身が pnpm を採用・推奨し、`create-turbo` のテンプレートも pnpm 前提
   - 依存グラフが明示的なため Turborepo のキャッシュキー計算が正確
   - GitHub Actions・Vercel・Turborepo 公式ドキュメントの例がほぼ pnpm で揃っており、トラブル時の情報量が最多
5. **エコシステム成熟度と将来性**
   - Vue / Vite / Svelte / Astro など主要 OSS が pnpm を採用済みで、衰退リスクが低い
   - PnP（Yarn Berry）のような互換性の摩擦も少なく、ツールチェーン全体がそのまま動く

## 想定ディレクトリ構成

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
│   ├── rag-worker/             ← Python（R7、pyproject.toml + uv）
│   └── eval-pipeline/          ← Python バッチ（R7）
├── packages/
│   ├── config/
│   │   └── tsconfig/           ← 共有 tsconfig（Biome 設定はリポジトリルート biome.jsonc に直接配置 → ADR 0018）
│   ├── shared-types/           ← JSON Schema を SSoT、各言語向け型生成
│   │   ├── schemas/            ← JSON Schema（SSoT）
│   │   ├── generated/          ← ts/（コミット）, go/（gitignore）, python/（gitignore）
│   │   └── scripts/
│   └── prompts/                ← YAML プロンプト
├── notebooks/                  ← R7、Jupyter
├── infra/                      ← Terraform
│   ├── modules/                ← network / db / ecs / worker / monitoring
│   └── envs/                   ← staging / production
├── docs/
│   ├── requirements/
│   └── adr/
├── .github/workflows/          ← GitHub Actions
├── .env.example                ← 共有環境変数（DB URL 等）
├── pnpm-workspace.yaml
├── turbo.jsonc
├── biome.jsonc                 ← ルート Biome 設定
├── docker-compose.yml
├── README.md
└── SYSTEM_OVERVIEW.md
```

- 各アプリ直下に `Dockerfile` を配置（ビルドコンテキスト最小化、アプリごとに独立 CI ビルド可能）
- 共有環境変数はルートの `.env.example`、アプリ固有変数は各アプリ直下の `.env.example`
- 共有スキーマは [ADR 0006](./0006-json-schema-as-single-source-of-truth.md) に従い JSON Schema を SSoT として各言語向け型を自動生成
- TS のコード品質ツールは [ADR 0018](./0018-biome-for-tooling.md) に従い Biome に統一

## Alternatives Considered（検討した代替案）

### モノレポ管理ツール

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| Turborepo + pnpm workspaces | （採用） | — |
| Nx + pnpm workspaces | 大規模 JS/TS モノレポの本格派、Python プラグインあり | 学習コスト高、独自概念多数（Project / Target / Executor / Generator）、本プロジェクト規模では過剰 |
| pnpm workspaces のみ | パッケージマネージャ標準機能のみ | ビルドキャッシュなし、並列実行が手動、CI が遅くなる |
| Bazel | 多言語ネイティブサポート（TS / Go / Python が同列） | 学習コスト極大、セットアップに数週間、R7 規模でも過剰、ポートフォリオで「なぜ？」が問われる |
| Lerna | 古参 | 2022 年以降 Nx 傘下、独立した進化なし |
| Rush | エンタープライズ向け | 個人開発で採用例少、コミュニティ小 |
| ポリレポ（リポジトリ分割） | 各アプリ独立リポジトリ | 共有スキーマの同期が手動、PR が複数リポジトリにまたがる、個人開発で運用負荷高 |

### パッケージマネージャ

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| pnpm | （採用） | — |
| npm（v7+ workspaces） | Node.js 標準同梱、最も安定 | `workspace:` プロトコル相当が無くローカル参照が曖昧、hoisting による幻の依存、install 速度・ディスク効率で劣る |
| Yarn Classic（v1） | workspaces を最初に流行らせた古参 | メンテナンスモード（v1 系は新機能なし）、新規採用の積極的理由なし |
| Yarn Berry（PnP モード） | `node_modules/` を捨て `.pnp.cjs` で依存解決、ディスク効率最強 | エコシステム互換性の摩擦（一部 bundler / IDE で追加設定が必要）、Turborepo との組み合わせ実績が薄い |
| Yarn Berry（node_modules リンカ） | PnP を諦めた使い方 | pnpm に対する明確な優位がなく、選ぶ積極的理由がない |
| Bun | 速度最強、ランタイム + バンドラ + テスト統合 | 2026 年時点でもエッジケースの安定性に懸念、Turborepo との統合は可能だが Bun 自身のタスクランナーと役割が重複、ポートフォリオでは pnpm のほうが説明可能性が高い |

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
- Turborepo の独自機能（リモートキャッシュ等）に部分的に依存（ローカルキャッシュは独立して機能するため致命傷にはならない）
- R7 で Python の依存が複雑化した場合、Turborepo の管理外で運用される領域が増える可能性
- ごく稀に pnpm の厳格な解決と相性が悪いパッケージが存在する → `node-linker=hoisted` で個別回避可能、頻度は低い
- npm 経験者がメンバーに加わった場合、`pnpm-lock.yaml` の扱いと `workspace:*` の意味を学習する必要がある（個人開発のため当面は無関係）

### 将来の見直しトリガー
- パッケージ数が 30 を超え、依存グラフ可視化や厳格な境界制約が必要になった場合 → **Nx へ移行を検討**
- Python の依存・ビルドパイプラインが複雑化し、薄い統合では足りなくなった場合 → **Python 側だけ独立リポジトリ化**または**Bazel 移行**を検討
- 言語が 4 つ以上に増えた、または各言語の深い相互依存が発生した場合 → **Bazel 移行**を検討

## References

- [05-runtime-stack.md: モノレポ構成](../requirements/2-foundation/05-runtime-stack.md)
- [ADR 0003: 言語の段階導入](./0003-phased-language-introduction.md)
- [Turborepo 公式](https://turborepo.com/)
- [pnpm workspaces 公式](https://pnpm.io/workspaces)
- [uv 公式](https://docs.astral.sh/uv/)
