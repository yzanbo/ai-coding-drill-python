# 3-cross-cutting/

**変更頻度：中**（機能追加のたびに更新される横断要件）

---

## このディレクトリの役割

**機能追加で成長する横断要件**を定義する。

- 複数機能で共有されるエンティティ関係（ER 図）
- 個別機能を超えた API 共通仕様（認証・エラー形式・レート制限）
- これらは「機能追加のたびに更新される」性質を持つが、役割としては**横断的**

機能個別の詳細・実装ステータスは扱わない（4-features/ を参照）。

---

## ファイル一覧

| # | ファイル | 内容 |
|---|---|---|
| 01 | [data-model](./01-data-model.md) | ER 図（全体俯瞰）・命名規則・横断方針（ID 戦略・タイムスタンプ・JSON カラム・ジョブペイロード共通フィールド・マイグレーション運用） |
| 02 | [api-conventions](./02-api-conventions.md) | API 共通仕様（基本方針・認証・エラー形式・ステータスコード・レート制限・OpenAPI 方針・非同期パターン） |
| _template.md | [_template.md](./_template.md) | 新規横断要件追加用テンプレ |

---

## 更新タイミング

- 新機能（[4-features/](../4-features/) に新規 .md 追加）と同時に：
  - 新規エンティティが必要になったら [01-data-model.md](./01-data-model.md) の ER 図を更新
  - 新規エンドポイントの共通方針が必要なら [02-api-conventions.md](./02-api-conventions.md) を更新
- スキーマ変更・マイグレーションを起こすとき
- API のエラーフォーマット・ステータスコード方針を見直すとき

**個別テーブル・個別エンドポイントの詳細仕様はこのディレクトリには書かない。**

| 詳細仕様の SSoT | 配置 |
|---|---|
| テーブル単位のカラム定義 | Drizzle スキーマ（`apps/api/src/drizzle/schema/`） |
| 個別エンドポイントの req/res | [4-features/](../4-features/) 各 F-XX.md + OpenAPI |
| ジョブペイロードの完全な JSON Schema | `packages/shared-types/schemas/` |

---

## 関連

- [2-foundation/02-architecture.md](../2-foundation/02-architecture.md) — システム全体構造
- [4-features/](../4-features/) — 個別機能（ここで使うテーブル・エンドポイントを定義）
- [docs/adr/0014-json-schema-as-single-source-of-truth.md](../../adr/0014-json-schema-as-single-source-of-truth.md) — JSON Schema SSoT 戦略
- [docs/adr/0017-w3c-trace-context-in-job-payload.md](../../adr/0017-w3c-trace-context-in-job-payload.md) — ジョブペイロードへの traceContext 埋め込み
