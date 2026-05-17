---
name: verify-requirements
description: 要件 .md と実装の整合性を検証する
argument-hint: "[<name>] (例: problem-generation, grading) または all で全件検証"
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

各要件から以下を抽出する（セクション名は `_template.md` 準拠）：

- **データモデル**：関わるテーブル名の列挙のみ（カラム単位の最終仕様は SQLAlchemy モデルと ER 図が SSoT、ここでは記載しない方針）
- **API**：エンドポイント、メソッド、認証要否（owner feature にのみ JSON 例が書かれる、他 feature からはアンカー参照）
- **ビジネスルール**：ステータス値、バリデーション条件（ただし機械的検証は Pydantic / Zod が SSoT、本セクションは業務上の理由があるルールのみ）
- **画面**：ルート、使用 API、主要インタラクション

### 2. 実装の読み込み

対応する実装コードを読み込む：

- **スキーマ**：`apps/api/app/models/*.py` から SQLAlchemy モデル
- **ルーター**：`apps/api/app/routers/*.py` からエンドポイント
- **サービス**：`apps/api/app/services/*.py` からビジネスロジック（認可・分岐・Pydantic 詰め替え、→ [ADR 0044](../../../docs/adr/0044-backend-repository-pattern-adoption.md)）
- **リポジトリ**：`apps/api/app/repositories/*.py` から SQLAlchemy クエリ実装（ORM オブジェクトを返す、→ [ADR 0044](../../../docs/adr/0044-backend-repository-pattern-adoption.md)）
- **Pydantic スキーマ**：`apps/api/app/schemas/*.py` からバリデーション
- **フロント画面**：`apps/web/src/app/(routing)/**/page.tsx`
- **採点 Worker**：`apps/workers/grading/internal/**`（該当時）
- **共有 artifact**：`apps/api/openapi.json`（HTTP API 境界）/ `apps/api/job-schemas/*.json`（Job キュー境界）
- **プロンプト**：`apps/workers/grading/prompts/**/*.yaml` / `apps/workers/generation/prompts/**/*.yaml`（LLM 関連の場合、ADR 0040）

### 3. データモデルの突合

要件の「データモデル」節で**列挙されているテーブル名**が SQLAlchemy モデルに存在するかを突合する（要件にはテーブル名以外は書かれない方針、`_template.md` 準拠）：

- 要件で言及されているテーブルが `apps/api/app/models/` に存在するか
- 逆に要件で言及されていないテーブルを実装が使っていれば、要件に追記すべきか判断

**カラム単位の詳細**（カラム名・型・FK・制約・命名規則違反 `_at` / `_id`、→ [.claude/rules/alembic-sqlalchemy.md](../../rules/alembic-sqlalchemy.md)）は要件側に書かれていないため、§8 の「ER 図 vs SQLAlchemy モデル」で突合する。

### 4. エンドポイントの突合

要件の「API」節（テーブル + JSON 例）と FastAPI ルーターを比較する：

- 要件にあるが実装にないエンドポイント
- 実装にあるが要件にない（不要 or 文書化漏れ）
- 認証要否の不一致（router の `dependencies=[Depends(get_current_user)]` の有無）
- リクエスト・レスポンス Pydantic スキーマの不一致
- **owner feature ルールの遵守**：各エンドポイントは 1 つの feature .md が所有し、他 feature はアンカー参照のみ。同じエンドポイントが複数 feature の API テーブルに重複していないか確認

### 5. フロントエンドの突合

要件の「画面」節とフロント実装を比較する：

- **画面ルート検証**：要件に記載されたパスに対応する `page.tsx` が存在するか
- **使用 API 検証**：画面が使う API がバックエンドに実在するか
- **バリデーション整合性**：要件「バリデーション」節の業務ルールが Zod スキーマ（Hey API 生成、`apps/web/src/lib/api/generated/`）、API の Pydantic スキーマと整合しているか（機械的検証は Pydantic / Zod が SSoT）

### 6. 採点 Worker の突合（該当時）

採点フローに関する要件がある場合：

- ジョブペイロードのスキーマ（`apps/api/job-schemas/*.json`、Pydantic から書き出し）が要件と一致するか
- Go Worker が期待される `type` を全てハンドルしているか
- 結果書き戻しのフィールドが要件と一致するか

### 7. プロンプトの突合（LLM 関連時）

- 要件で言及されているカテゴリ・難易度がプロンプトの変数と整合するか
- 出力スキーマ（`apps/api/job-schemas/problem.schema.json` 等、Pydantic から書き出し）が要件と一致するか
- Judge の評価軸が要件と一致するか

### 8. ER 図の突合

[01-data-model.md](../../../docs/requirements/3-cross-cutting/01-data-model.md) の Mermaid ER 図と SQLAlchemy モデルを比較：

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

### 採点 Worker
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
