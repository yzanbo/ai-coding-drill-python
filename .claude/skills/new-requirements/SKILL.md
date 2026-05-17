---
name: new-requirements
description: 機能別の要件 .md を対話的に新規作成する
argument-hint: "[<name>] [概要の説明]"
---

# 機能要件の新規作成

引数 `$ARGUMENTS` の最初の単語を**機能ファイル名**（`<name>` 形式、例：`problem-adaptive-quiz`）、残りを機能の概要として解釈する。既存ドメイン（`authentication` / `problem-*` / `grading` / `learning` 等）に該当するなら同じドメイン名を使う（**1 ドメイン 1 ファイル**）、同ドメイン内に複数ワークフローを置く場合はドメイン名 prefix で分割する（例：`problem-generation` / `problem-display-and-answer`）。→ `docs/requirements/4-features/README.md` の機能一覧表で既存命名を確認できる。

機能要件は `docs/requirements/4-features/<name>.md` に作成する。
ベースとなる全体要件（[docs/requirements/](../../../docs/requirements/)）に対する**機能別の追加仕様**として位置付ける。

## 手順

### 1. テンプレートと既存要件の確認

- ベース要件 [docs/requirements/1-vision/01-overview.md](../../../docs/requirements/1-vision/01-overview.md) と [4-features/README.md](../../../docs/requirements/4-features/README.md) の機能一覧表を読み、既存機能との重複・関連を把握
- 既存の `docs/requirements/4-features/` 配下があれば確認し、粒度とスタイルの参考にする
- ベース要件の編集ルール [.claude/rules/docs-rules.md](../../rules/docs-rules.md) に従う

### 2. 概要からの深掘り（対話フェーズ）

ユーザーから受け取った概要を元に、以下の観点で不足情報を質問する：

- **ターゲットユーザー**：認証必須か、未認証も使えるか
- **画面**：新規画面が必要か、既存画面を拡張するか
- **データモデル**：新規テーブル・カラムが必要か（→ [01-data-model.md](../../../docs/requirements/3-cross-cutting/01-data-model.md) との整合性）
- **API**：新規エンドポイントが必要か（→ [02-api-conventions.md](../../../docs/requirements/3-cross-cutting/02-api-conventions.md) との整合性）
- **LLM 利用**：問題生成・評価への影響があるか
- **採点 Worker への影響**：Go Worker 側の処理が増えるか
- **既存機能との関係**：既存の問題・採点・履歴フローとの依存関係
- **制約・エッジケース**：同時実行、レート制限、データ整合性

一度に全てを聞かず、最も重要な 2〜3 問に絞って質問する。
ユーザーの回答を受けてさらに深掘りが必要なら追加で質問する。

### 3. 機能要件 .md の生成

対話で得た情報をまとめ、`docs/requirements/4-features/<name>.md` を **`docs/requirements/4-features/_template.md` をコピーして雛形にする**（ファイル名は `$ARGUMENTS` の先頭単語）。**セクション構造・順序・HTML コメント（裏ルール）はテンプレートを忠実に踏襲する**こと（テンプレートが SSoT、本スキル内では構造を複製しない）。

テンプレートのセクション順序：WHY（ユーザーストーリー）→ WHAT（概要 / ビジネスルール / スコープ外）→ 機能一覧（全体俯瞰）→ HOW（データモデル / 画面 / ユーザーフロー / API / バリデーション）→ 完成検証（受け入れ条件）→ 進捗（ステータス）→ 外部参照（関連）。

**重要**：
- API 仕様の細部（リクエスト・レスポンスの全フィールド）や DTO 仕様はここに書かない。OpenAPI（Swagger）と Pydantic に委ねる。ビジネスルールとドメイン知識に集中する
- バリデーション節は**業務上の理由があるルールのみ**書く（機械的検証は Pydantic / Zod が SSoT）
- データモデル節は**関わるテーブル名の列挙のみ**、カラム定義は書かない（drift 防止）
- ステータス節の項目はテンプレート通り。**追加・削除しない**（Worker が不要な機能では「ワーカー実装完了」項目を最初から作らない判断はあり）
- HTML コメント（`<!--` 〜 `-->`）は**削除しない**（CLAUDE が次回更新時に運用ルールを再認識するための裏ルール、`_template.md` 冒頭の運用原則 5 を参照）

### 4. レビュー

作成した内容をユーザーに提示し、修正点がないか確認する。修正があれば反映し、最終版を保存する。

### 5. ベース要件との整合チェック

機能要件で**新規エンドポイント・新規テーブル・新規画面・新規ユーザーストーリー**を追加した場合、それらをベース要件にも反映する：

- [1-vision/01-overview.md](../../../docs/requirements/1-vision/01-overview.md)：機能俯瞰一覧に 機能を追記（概要レベルのみ）
- [1-vision/03-user-stories.md](../../../docs/requirements/1-vision/03-user-stories.md)：該当ペルソナのマトリクスにストーリーを追加（[`_template-03-user-stories.md`](../../../docs/requirements/1-vision/_template-03-user-stories.md) の形式に従う）
- [3-cross-cutting/01-data-model.md](../../../docs/requirements/3-cross-cutting/01-data-model.md)：ER 図と命名規則・横断方針を更新
- [3-cross-cutting/02-api-conventions.md](../../../docs/requirements/3-cross-cutting/02-api-conventions.md)：機能別エンドポイント一覧に 機能行を追加
- [4-features/README.md](../../../docs/requirements/4-features/README.md)：機能一覧表に 機能行を追加
- [5-roadmap/01-roadmap.md](../../../docs/requirements/5-roadmap/01-roadmap.md)：プロダクトバックログに項目追加

ただし詳細はベースに書かず、機能要件 .md へのリンクで誘導する。

機能 .md は [4-features/_template.md](../../../docs/requirements/4-features/_template.md) を雛形に作成する。新規ユーザーストーリーは先に追加してから機能要件詳細を書く（[`_template-03-user-stories.md`](../../../docs/requirements/1-vision/_template-03-user-stories.md) のガイドに従う）。
