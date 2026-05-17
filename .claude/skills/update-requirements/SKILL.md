---
name: update-requirements
description: 要件 .md を先に更新してから実装を修正する
argument-hint: "[<name>] [変更内容の説明]"
---

# 要件先行更新

引数 `$ARGUMENTS` の最初の単語を**機能パス**（`<name>` 形式、例：`problem-generation`）、残りを変更内容として解釈する。

## 手順

### 1. 現在の要件を読み込む

- 機能要件：`docs/requirements/4-features/<name>.md`（`$ARGUMENTS` の先頭単語）
- 関連するベース要件：[docs/requirements/](../../../docs/requirements/)
  - [1-vision/03-user-stories.md](../../../docs/requirements/1-vision/03-user-stories.md)（ユーザーストーリー）
  - [2-foundation/02-architecture.md](../../../docs/requirements/2-foundation/02-architecture.md)（アーキテクチャ）
  - [3-cross-cutting/01-data-model.md](../../../docs/requirements/3-cross-cutting/01-data-model.md)（ER 図・データモデル）
  - [3-cross-cutting/02-api-conventions.md](../../../docs/requirements/3-cross-cutting/02-api-conventions.md)（API 共通仕様）
- 関連 ADR：[docs/adr/](../../../docs/adr/)

ファイルが存在しない場合は、ユーザーに `/new-requirements` で先に作成することを提案する。

### 2. 要件 vs 実装の判断（どちら側を直すか）

変更内容（`$ARGUMENTS` の 2 単語目以降）について、**要件 .md を変えるべきか、実装を変えるべきかを工数を無視して純粋なメリット観点から判断**する。このスキル名は "update-requirements" だが、要件側更新ありきで進めない。要件の方が正しい場合は実装側を直す。

判断軸（工数は度外視）：

- 変更内容が業務・UX として正しい新しい仕様 → 要件 .md を更新（手順 3 へ）
- 変更内容が「実装を要件に合わせる」修正（要件記述は既に正しい） → 要件は触らず手順 6 の実装修正へ進む
- 双方を直す必要がある → 両方を直す（変更点を分解して片方ずつ進める）

判断結果をユーザーに提示して承認を得てから先に進む。

### 3. 要件 .md の更新（手順 2 で要件側を直すと判断した場合）

- 変更差分をユーザーに提示して承認を得る
- ビジネスルール / 機能一覧 / データモデル / API（`_template.md` 準拠のセクション名）のいずれかに変更が生じるか判断
- API 変更がある場合は、画面節の「使用 API」サブ項目も更新対象に含める
- ベース要件の編集ルール [.claude/rules/docs-rules.md](../../rules/docs-rules.md) に従い、重複を避けてリンクで参照
- 承認後に要件 .md を保存

### 4. ベース要件への波及確認

機能要件の変更が以下に波及するかを確認し、必要なら更新：

- [01-overview.md](../../../docs/requirements/1-vision/01-overview.md)：機能一覧
- [02-architecture.md](../../../docs/requirements/2-foundation/02-architecture.md)：コンポーネント責務、データフロー
- [01-data-model.md](../../../docs/requirements/3-cross-cutting/01-data-model.md)：ER 図、テーブル定義
- [02-api-conventions.md](../../../docs/requirements/3-cross-cutting/02-api-conventions.md)：エンドポイント一覧

### 5. ADR 化の判断

変更が**設計判断レベル**であれば、新規 ADR を起票する：

- 「なぜそう決めたか」「他案は何だったか」が後から問われる内容
- フレームワーク選定、ライブラリ選定、データ構造の根本変更、運用方針など

ADR は [docs/adr/template.md](../../../docs/adr/template.md) を元に作成。

### 6. 実装の修正

更新された要件（または手順 2 で「実装側を直す」と判断した内容）に基づいて、コード側の修正を行う：

- 関連するモジュール（`apps/api/app/{models,schemas,repositories,services,routers}/<feature>.py`、`apps/web/src/app/`、`apps/workers/<name>/internal/`）を確認（Backend は Router / Service / Repository / ORM の 3 層分離、→ [ADR 0044](../../../docs/adr/0044-backend-repository-pattern-adoption.md)）
- 各レイヤのルール（[.claude/rules/](../../rules/)）に従って修正
- 変更の影響範囲を特定し、ユーザーに提示してから実装
- **後方互換は取らない**：旧シグネチャ / 旧エンドポイント / 旧ジョブタイプ / re-export shim の併存禁止。呼び出し元も同じコミット内で最新形に直接修正（→ CLAUDE.md「後方互換性について」）

#### 実装中のコミット粒度

- **適切な粒度で適宜コミット**する（このスキルの実行自体がユーザの明示指示として `git add` / `git commit` を許容する）。要件 .md の更新コミットと、実装修正のコミットは分けるのが望ましい
- 実装側もレイヤ（モデル / スキーマ / repository / service / router / web / worker）ごとに分割する
- コミットメッセージは CLAUDE.md「コミットメッセージ」の規約（`<type>(<scope>): <subject>`、本文必須）に従う。AI 生成文言（`Co-Authored-By` / `Generated with` 等）は入れない
- `git push` / PR 作成はユーザの明示指示があるまで行わない

### 7. ステータス更新

実装完了後、`docs/requirements/4-features/<name>.md` のステータスを適宜更新する。
