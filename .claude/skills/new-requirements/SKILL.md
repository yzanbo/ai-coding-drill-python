---
name: new-requirements
description: 機能別の要件 .md を対話的に新規作成する
argument-hint: "[feature-name] [概要の説明]"
---

# 機能要件の新規作成

引数の最初の単語 `$0` を機能名（ファイル名）、残り `$1` 以降を機能の概要として解釈する。

機能要件は `docs/requirements/4-features/<feature-name>.md` に作成する。
ベースとなる全体要件（[docs/requirements/](../../../docs/requirements/)）に対する**機能別の追加仕様**として位置付ける。

## 手順

### 1. テンプレートと既存要件の確認

- ベース要件 [docs/requirements/1-vision/01-overview.md](../../../docs/requirements/1-vision/01-overview.md) を読み、F-01〜F-08 の既存機能との重複・関連を把握
- 既存の `docs/requirements/4-features/` 配下があれば確認し、粒度とスタイルの参考にする
- ベース要件の編集ルール [.claude/rules/docs-rules.md](../../rules/docs-rules.md) に従う

### 2. 概要からの深掘り（対話フェーズ）

ユーザーから受け取った概要を元に、以下の観点で不足情報を質問する：

- **ターゲットユーザー**：認証必須か、未認証も使えるか
- **画面**：新規画面が必要か、既存画面を拡張するか
- **データモデル**：新規テーブル・カラムが必要か（→ [01-data-model.md](../../../docs/requirements/3-cross-cutting/01-data-model.md) との整合性）
- **API**：新規エンドポイントが必要か（→ [02-api-conventions.md](../../../docs/requirements/3-cross-cutting/02-api-conventions.md) との整合性）
- **LLM 利用**：問題生成・評価への影響があるか
- **採点ワーカーへの影響**：Go ワーカー側の処理が増えるか
- **既存機能との関係**：既存の問題・採点・履歴フローとの依存関係
- **制約・エッジケース**：同時実行、レート制限、データ整合性

一度に全てを聞かず、最も重要な 2〜3 問に絞って質問する。
ユーザーの回答を受けてさらに深掘りが必要なら追加で質問する。

### 3. 機能要件 .md の生成

対話で得た情報をまとめ、`docs/requirements/4-features/$0.md` を以下のセクション構成で作成する：

```markdown
# 機能要件：<機能名>

## 概要

## ターゲットユーザー

## ユーザーストーリー

## 画面一覧
| パス | 役割 | 認証 | 主要コンポーネント | 使用 API |
|---|---|---|---|---|

## データモデル変更
- 新規テーブル / 既存テーブルへのカラム追加

## API 仕様
- 新規エンドポイント一覧（パス、メソッド、用途、リクエスト・レスポンス概要）

## LLM 利用（該当時）
- 使用するプロンプト
- 評価軸の追加・変更

## ビジネスルール
- コードに落とすだけでは伝わらないドメイン知識
- ステータス値、バリデーション条件、状態遷移

## 既存機能との関係
- 依存・影響範囲

## 制約・エッジケース
- 同時実行、排他制御、データ整合性

## ステータス
- [x] 要件定義完了
- [ ] バックエンド実装完了
- [ ] フロントエンド実装完了
- [ ] 採点ワーカー実装完了（該当時）
- [ ] テスト完了
```

**重要**：API 仕様の細部（リクエスト・レスポンスの全フィールド）や DTO 仕様はここに書かない。OpenAPI（Swagger）と DTO に委ねる。ビジネスルールとドメイン知識に集中する。

### 4. レビュー

作成した内容をユーザーに提示し、修正点がないか確認する。修正があれば反映し、最終版を保存する。

### 5. ベース要件との整合チェック

機能要件で**新規エンドポイント・新規テーブル・新規画面・新規ユーザーストーリー**を追加した場合、それらをベース要件にも反映する：

- [1-vision/01-overview.md](../../../docs/requirements/1-vision/01-overview.md)：機能俯瞰一覧に F-XX を追記（概要レベルのみ）
- [1-vision/03-user-stories.md](../../../docs/requirements/1-vision/03-user-stories.md)：該当ペルソナのマトリクスにストーリーを追加（[`_template-03-user-stories.md`](../../../docs/requirements/1-vision/_template-03-user-stories.md) の形式に従う）
- [3-cross-cutting/01-data-model.md](../../../docs/requirements/3-cross-cutting/01-data-model.md)：ER 図と命名規則・横断方針を更新
- [3-cross-cutting/02-api-conventions.md](../../../docs/requirements/3-cross-cutting/02-api-conventions.md)：機能別エンドポイント一覧に F-XX 行を追加
- [4-features/README.md](../../../docs/requirements/4-features/README.md)：機能一覧表に F-XX 行を追加
- [5-roadmap/01-roadmap.md](../../../docs/requirements/5-roadmap/01-roadmap.md)：プロダクトバックログに項目追加

ただし詳細はベースに書かず、機能要件 .md へのリンクで誘導する。

機能 .md は [4-features/_template.md](../../../docs/requirements/4-features/_template.md) を雛形に作成する。新規ユーザーストーリーは先に追加してから機能要件詳細を書く（[`_template-03-user-stories.md`](../../../docs/requirements/1-vision/_template-03-user-stories.md) のガイドに従う）。
