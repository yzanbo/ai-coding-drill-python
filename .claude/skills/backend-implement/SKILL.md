---
name: backend-implement
description: 要件 .md を読み込んで FastAPI を実装する
argument-hint: "[<name>] (例: problem-generation, grading)"
---

# 要件ベースのバックエンド実装

引数 `$ARGUMENTS` を機能名として解釈する。

## 手順

### 1. 要件の読み込み

- 機能要件：`docs/requirements/4-features/$ARGUMENTS.md`
- ベース要件：[01-overview.md](../../../docs/requirements/1-vision/01-overview.md)、[02-architecture.md](../../../docs/requirements/2-foundation/02-architecture.md)、[01-data-model.md](../../../docs/requirements/3-cross-cutting/01-data-model.md)、[02-api-conventions.md](../../../docs/requirements/3-cross-cutting/02-api-conventions.md)
- 関連 ADR：[docs/adr/](../../../docs/adr/)
- バックエンドルール：[.claude/rules/backend.md](../../rules/backend.md)、[.claude/rules/alembic-sqlalchemy.md](../../rules/alembic-sqlalchemy.md)

ファイルが存在しない場合は、ユーザーに `/new-requirements` で先に作成することを提案する。

### 2. 現状の確認

- 要件のステータスチェックボックスを確認
- 関連する既存コード（router / service / repository / SQLAlchemy モデル / Pydantic スキーマ）を確認（**Repository パターン採用**、Service / Repository / ORM の 3 層分離、→ [ADR 0044](../../../docs/adr/0044-backend-repository-pattern-adoption.md) / [.claude/rules/backend.md](../../rules/backend.md)）
- HTTP API 境界の artifact（`apps/api/openapi.json`）と Job キュー境界の artifact（`apps/api/job-schemas/`）の生成状況を確認（→ [ADR 0006](../../../docs/adr/0006-json-schema-as-single-source-of-truth.md)）
- 要件に対して未実装の部分を特定する

### 3. 実装方針の提示

要件に基づいて実装方針をユーザーに提示する：

- 変更するファイルの一覧
- 新規作成するファイルの一覧
- スキーマ変更の有無（Alembic マイグレーション必要か）
- ジョブキュー（jobs テーブル）への影響
- LLM 呼び出しは Worker 側に閉じる（→ [ADR 0040](../../../docs/adr/0040-worker-grouping-and-llm-in-worker.md)）。Backend は enqueue + 結果取得のみ
- 実装の順序（モデル → Pydantic スキーマ → repository → service → router → テスト、→ [ADR 0044](../../../docs/adr/0044-backend-repository-pattern-adoption.md)）

ユーザーの承認を待ってから次の手順に進む。

### 4. 要件 vs 実装の事前判断（方針の質疑で確定した決定を SSoT 側に反映）

手順 3 の方針提示で**ユーザーと対話的に確定した決定**について、**要件 .md を変えるべきか、実装を変えるべきかを工数を無視して純粋なメリット観点から判断**する。要件 .md の追従ありきで進めず、要件の方が正しい場合は実装側を直す前提に立つ。実装中に決めるとズレが残るため、**着手前に SSoT 側を確定**させる。

判断軸（工数は度外視）：

- 要件 .md の記述が業務・UX として正しい → 実装をそれに合わせる
- 既存実装の挙動が業務・UX として正しい / 要件記述が陳腐化している → 要件 .md を更新（ステータス・受け入れ条件含む）
- 双方が並行進化していて整合しない → 正しい側を選んで他方を直す

反映先：

- 要件側を変える場合：機能要件 .md の該当節（ビジネスルール / 画面 / API / バリデーション 等）、必要なら横断要件（`3-cross-cutting/`）にも追記。観測可能な振る舞いは**受け入れ条件**にも追加
- 実装側を変える場合：手順 5 の実装で対応。**後方互換は取らない**（deprecated エイリアス / shim / 旧 API の併存禁止、最新状態に合わせて直接修正、→ CLAUDE.md「後方互換性について」）
- 実装詳細（依存ライブラリ / 環境変数 / DB 拡張 等）は要件 .md に書かない（SSoT は pyproject / .env / SQLAlchemy モデル側、→ `_template.md` 冒頭の長期運用原則）

設計判断レベルの決定は ADR 起票も検討する。判断結果を反映してから手順 5 の実装に進む。

### 5. 実装

[.claude/rules/backend.md](../../rules/backend.md) のコーディング規約に従って実装する。重要なポイント：

- ディレクトリ構成：機能別フラット（`apps/api/app/{models,schemas,repositories,services,routers}/<feature>.py`、Router / Service / Repository / ORM の 3 層分離、→ [ADR 0044](../../../docs/adr/0044-backend-repository-pattern-adoption.md)）
- async I/O 必須：`AsyncSession` + `async def`
- SQLAlchemy 2.0 新スタイル（`Mapped[T]` / `mapped_column()`）、1.x スタイル禁止
- Pydantic スキーマが SSoT。Router の `response_model` を必ず明示し、OpenAPI 出力を確実にする
- ジョブ投入はトランザクショナルに（`async with session.begin():` 内で `INSERT submissions` + `INSERT jobs` + `NOTIFY new_job`）
- エラーは `app/core/exceptions.py` の handler 経由で HTTPException に変換、メッセージは日本語
- `Any` 禁止、SQLAlchemy `Mapped[T]` / Pydantic / `TypedDict` で型付け
- **後方互換は取らない**：旧シグネチャの併存・deprecated 変数・re-export shim 等は作らない。呼び出し元も同じコミット内で最新形に直接修正する（→ CLAUDE.md「後方互換性について」）

#### 実装中のコミット粒度

- **適切な粒度で適宜コミット**する（このスキルの実行自体がユーザの明示指示として `git add` / `git commit` を許容する）。雛形・ロジック・ルーター結線・テストなど論理的にまとまる単位で区切る
- 1 コミット ≒ 1 レビュー単位を意識：モデル追加 / スキーマ追加 / repository / service / router / マイグレーション / OpenAPI 再生成 などを混ぜない
- コミットメッセージは CLAUDE.md「コミットメッセージ」の規約（`<type>(<scope>): <subject>`、本文必須）に従う。AI 生成文言（`Co-Authored-By` / `Generated with` 等）は入れない
- `git push` / PR 作成はユーザの明示指示があるまで行わない

### 6. スキーマ変更時の手順

1. `apps/api/app/models/<feature>.py` の SQLAlchemy モデルを修正
2. `mise run api:db-revision -- "<msg>"` でマイグレーション雛形生成（autogenerate）
3. 生成された `apps/api/alembic/versions/<rev>_<slug>.py` を確認、autogenerate 拾い漏れ（インデックス rename / 拡張 / データ移行）を手で補完
4. 適用：`mise run api:db-migrate`
5. [01-data-model.md](../../../docs/requirements/3-cross-cutting/01-data-model.md) の ER 図・テーブル定義も更新

詳細は [.claude/rules/alembic-sqlalchemy.md](../../rules/alembic-sqlalchemy.md)。

### 7. 共有 artifact 変更時

- HTTP API 境界（FastAPI ルートの追加・変更）→ `mise run api:openapi-export` で `apps/api/openapi.json` を更新 → Web 側は `mise run web:types-gen` で TS / Zod / HTTP クライアントを再生成
- Job キュー境界（`app/schemas/jobs/*.py` の Pydantic）→ `mise run api:job-schemas-export` で `apps/api/job-schemas/*.json` を更新 → Worker 側は `mise run worker:types-gen` で Go struct を再生成
- 詳細は [ADR 0006](../../../docs/adr/0006-json-schema-as-single-source-of-truth.md)
- 新規プロンプトは Worker 配下（`apps/workers/<name>/prompts/*.yaml`、→ [ADR 0040](../../../docs/adr/0040-worker-grouping-and-llm-in-worker.md) / [.claude/rules/prompts.md](../../rules/prompts.md)）

### 8. 動作確認

- `mise run api:typecheck` で pyright エラーなし
- `mise run api:lint` で ruff 警告なし
- `mise run api:audit` で pip-audit 検出なし
- `mise run api:deps-check` で deptry 警告なし
- ローカルで Swagger UI（http://localhost:8000/docs）から手動疎通確認

問題があれば修正してから次の手順に進む。

### 9. 要件 vs 実装の事後判断（動作確認で出た差分をどちら側で吸収するか）

動作確認まで通った段階で、実装と要件 .md の間に差分があれば、**ステータス更新の前に**「要件を直す / 実装を直す」を**工数を無視して純粋なメリット観点から判断**して解消する。「実装が SSoT だから要件側を書き換える」と機械的に決めない。

判断軸（工数は度外視）：

- 実装の振る舞いが業務・UX として正しい → 要件 .md を更新（受け入れ条件・API 節・データモデル節など）
- 要件 .md の記述が業務・UX として正しい / 実装が要件から外れている → 実装を直す（**後方互換 NG、最新状態に合わせて修正**、→ CLAUDE.md「後方互換性について」）
- 実装中に「これも担保すべき」と気付いた振る舞いは、要件側に受け入れ条件として追加する候補

確認対象の差分例：

- **追加された振る舞い / 契約**：新規エンドポイントの response / status code、新規ヘッダー検証、エラーケースの追加 等
- **データモデル節の関わるテーブル**：新規追加したテーブル
- **画面節 / API 節の追従**：最終的なパス・JSON 構造

軽微な追従（フィールド名修正等）はこのスキル内で直接更新してよい。差分の規模が大きい場合は `/update-requirements` で対話的に進める。

### 10. ステータス更新

動作確認と要件追従まで完了したら、`docs/requirements/4-features/$ARGUMENTS.md` のステータスチェックボックスのうち**バックエンド実装完了**にチェックを入れる。

ステータス節の項目構成は機能ごとに `docs/requirements/4-features/_template.md` を踏襲し、機能固有の補足（例：「auth ルーター / セッションサービス / GitHub OAuth クライアント」）が括弧書きで追加されているケースもある。**項目の追加・削除はしない**（テンプレートからの drift を作らない）。テンプレ本体の更新が必要なら `_template.md` を直し、既存機能ファイルにも同じ構造を反映する。
