---
name: update-requirements
description: 要件 .md を先に更新してから実装を修正する
argument-hint: "[feature-name] [変更内容の説明]"
---

# 要件先行更新

引数の最初の単語 `$0` を機能名、残り `$1` 以降を変更内容として解釈する。

## 手順

### 1. 現在の要件を読み込む

- 機能要件：`docs/requirements/4-features/$0.md`
- 関連するベース要件：[docs/requirements/](../../../docs/requirements/)
  - [1-vision/03-user-stories.md](../../../docs/requirements/1-vision/03-user-stories.md)（ユーザーストーリー）
  - [2-foundation/02-architecture.md](../../../docs/requirements/2-foundation/02-architecture.md)（アーキテクチャ）
  - [3-cross-cutting/01-data-model.md](../../../docs/requirements/3-cross-cutting/01-data-model.md)（ER 図・データモデル）
  - [3-cross-cutting/02-api-conventions.md](../../../docs/requirements/3-cross-cutting/02-api-conventions.md)（API 共通仕様）
- 関連 ADR：[docs/adr/](../../../docs/adr/)

ファイルが存在しない場合は、ユーザーに `/new-requirements` で先に作成することを提案する。

### 2. 要件 .md の更新

変更内容（`$1` 以降）に基づいて、要件 .md の該当箇所を更新する：

- 変更差分をユーザーに提示して承認を得る
- ビジネスルール、機能一覧、データモデル、API 仕様のいずれかに変更が生じるか判断
- API 変更がある場合は、画面一覧の「使用 API」セクションも更新対象に含める
- ベース要件の編集ルール [.claude/rules/docs-rules.md](../../rules/docs-rules.md) に従い、重複を避けてリンクで参照
- 承認後に要件 .md を保存

### 3. ベース要件への波及確認

機能要件の変更が以下に波及するかを確認し、必要なら更新：

- [01-overview.md](../../../docs/requirements/1-vision/01-overview.md)：機能一覧 F-XX
- [02-architecture.md](../../../docs/requirements/2-foundation/02-architecture.md)：コンポーネント責務、データフロー
- [01-data-model.md](../../../docs/requirements/3-cross-cutting/01-data-model.md)：ER 図、テーブル定義
- [02-api-conventions.md](../../../docs/requirements/3-cross-cutting/02-api-conventions.md)：エンドポイント一覧

### 4. ADR 化の判断

変更が**設計判断レベル**であれば、新規 ADR を起票する：

- 「なぜそう決めたか」「他案は何だったか」が後から問われる内容
- フレームワーク選定、ライブラリ選定、データ構造の根本変更、運用方針など

ADR は [docs/adr/template.md](../../../docs/adr/template.md) を元に作成。

### 5. 実装の修正

更新された要件に基づいて、コード側の修正を行う：

- 関連するモジュール（`apps/api/src/<feature>/`、`apps/web/src/app/`、`apps/grading-worker/internal/`）を確認
- 各レイヤのルール（[.claude/rules/](../../rules/)）に従って修正
- 変更の影響範囲を特定し、ユーザーに提示してから実装

### 6. ステータス更新

実装完了後、`docs/requirements/4-features/$0.md` のステータスを適宜更新する。
