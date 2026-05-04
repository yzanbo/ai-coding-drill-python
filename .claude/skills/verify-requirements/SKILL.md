---
name: verify-requirements
description: 要件 .md と実装の整合性を検証する
argument-hint: "[feature-name] (例: problem-generation, grading) または all で全件検証"
---

# 要件 vs 実装の整合性検証

引数 `$ARGUMENTS` を機能名として解釈する。`all` の場合は `docs/requirements/4-features/` 配下の全要件 + ベース要件を対象とする。

## 手順

### 1. 要件の読み込み

- 機能要件：`docs/requirements/4-features/$ARGUMENTS.md`（`all` の場合は全ファイル）
- ベース要件：[docs/requirements/](../../../docs/requirements/)
  - 機能横断仕様：[3-cross-cutting/01-data-model.md](../../../docs/requirements/3-cross-cutting/01-data-model.md)（ER 図）、[3-cross-cutting/02-api-conventions.md](../../../docs/requirements/3-cross-cutting/02-api-conventions.md)（API 共通仕様）
  - 全体構造：[2-foundation/02-architecture.md](../../../docs/requirements/2-foundation/02-architecture.md)
  - 非機能要件：[2-foundation/01-non-functional.md](../../../docs/requirements/2-foundation/01-non-functional.md)

各要件から以下を抽出する：

- **データモデル**：テーブル名、カラム名、型、FK、制約
- **API 仕様**：エンドポイント、メソッド、認証要否
- **ビジネスルール**：ステータス値、バリデーション条件
- **画面一覧**：パス、使用 API

### 2. 実装の読み込み

対応する実装コードを読み込む：

- **スキーマ**：`apps/api/src/drizzle/schema/*.ts` からテーブル定義
- **コントローラ**：`apps/api/src/<feature>/*.controller.ts` からエンドポイント
- **サービス**：`apps/api/src/<feature>/*.service.ts` からビジネスロジック
- **DTO**：`apps/api/src/<feature>/dto/*.ts` からバリデーション
- **フロント画面**：`apps/web/src/app/(routing)/**/page.tsx`
- **採点ワーカー**：`apps/grading-worker/internal/**`（該当時）
- **共有スキーマ**：`packages/shared-types/schemas/*.json`
- **プロンプト**：`packages/prompts/**/*.yaml`（LLM 関連の場合）

### 3. データモデルの突合

要件のテーブル定義と Drizzle スキーマを比較し、差分を検出する：

- テーブルの過不足
- カラムの過不足
- カラム名の不一致（命名規則違反を含む：`_at` / `_id` ルール、→ [.claude/rules/drizzle.md](../../rules/drizzle.md)）
- 型の不一致
- FK 参照先の不一致
- インデックス・制約の過不足

### 4. エンドポイントの突合

要件の API 仕様とコントローラを比較する：

- 要件にあるが実装にないエンドポイント
- 実装にあるが要件にない（不要 or 文書化漏れ）
- 認証要否の不一致（`@Public()` の有無）
- リクエスト・レスポンス DTO の不一致

### 5. フロントエンドの突合

要件の画面一覧とフロント実装を比較する：

- **画面ルート検証**：要件に記載されたパスに対応する `page.tsx` が存在するか
- **使用 API 検証**：画面が使う API がバックエンドに実在するか
- **バリデーション整合性**：要件のバリデーションルールと Zod スキーマ（`lib/validation/`）、API の DTO が一致するか

### 6. 採点ワーカーの突合（該当時）

採点フローに関する要件がある場合：

- ジョブペイロードのスキーマ（`packages/shared-types/schemas/job.schema.json`）が要件と一致するか
- Go ワーカーが期待される `type` を全てハンドルしているか
- 結果書き戻しのフィールドが要件と一致するか

### 7. プロンプトの突合（LLM 関連時）

- 要件で言及されているカテゴリ・難易度がプロンプトの変数と整合するか
- 出力スキーマ（`packages/shared-types/schemas/problem.schema.json` 等）が要件と一致するか
- Judge の評価軸が要件と一致するか

### 8. ER 図の突合

[01-data-model.md](../../../docs/requirements/3-cross-cutting/01-data-model.md) の Mermaid ER 図と Drizzle スキーマを比較：

- ER 図に反映されていないテーブル・カラム・リレーション
- ER 図にあるが実装にないもの

### 9. レポート出力

検証結果を以下の形式でユーザーに提示する：

```
## 検証結果: <feature-name>

### データモデル
- ✅ 一致：<n> テーブル
- ⚠️ 差分あり：
  - <テーブル名>：<差分の説明>

### エンドポイント
- ✅ 一致：<n> 操作
- ⚠️ 差分あり：
  - <操作名>：<差分の説明>

### フロントエンド
- ✅ 画面ルート：<一致数> / <記載数>
- ⚠️ 差分あり：

### 採点ワーカー
- ✅ ジョブハンドラ：<n> 種類
- ⚠️ 差分あり：

### プロンプト・スキーマ
- ✅ 整合 / ⚠️ 差分

### ER 図
- ✅ 整合 / ⚠️ 差分

### 推奨アクション
1. <具体的な修正提案>
```

差分が見つかった場合、要件・実装のどちらを修正すべきか判断を添える。判断できない場合はユーザーに確認する。

### 10. 修正の実行

ユーザーの承認を得てから、差分の修正を行う：

- 要件側の修正 → 機能要件 .md + 該当するベース要件 / ER 図
- 実装側の修正 → スキーマ・コントローラ・サービス・フロント・ワーカー
- 両方の場合は要件を先に確定してから実装を修正
