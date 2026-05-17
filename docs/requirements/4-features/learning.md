# 学習履歴・統計

## ユーザーストーリー

- **役割**：認証ユーザー（プログラミング学習者）
- **やりたいこと**：過去に解いた問題と正誤、所要時間、弱点カテゴリを確認できる
- **得られる価値**：自分の進捗を把握し、苦手分野を意識的に練習できる

## 概要

ユーザーが自分の学習進捗を可視化するための機能。MVP は単純な集計（正答率・カテゴリ別習熟度・弱点カテゴリ Top N）のみ。R6 以降の「適応型出題」（[適応型出題](../5-roadmap/01-roadmap.md#適応型出題)）の前提データとなる。

## ビジネスルール

- **履歴は不可逆に蓄積**：解答送信ごとに 1 レコード作成、削除・上書きしない
- **正答 = 全テストケース通過**（部分点は MVP では考慮しない）
- **弱点カテゴリの定義**：正答率が一定以下（例：50% 未満）かつ解答数が一定以上（例：3 問以上）のカテゴリを抽出
- **習熟度の集計範囲**：全期間（MVP）。期間指定（過去 30 日など）は将来機能
- **問題が削除された場合**：MVP では問題削除機能自体がないため考慮不要
- **ゲストは履歴対象外**：認証必須機能なので未認証ユーザーには履歴が存在しない
- **ハードデリート方針**：履歴・統計は永続保存し、ソフトデリートは行わない（→ [CLAUDE.md](../../../.claude/CLAUDE.md)）
- **所有権チェックの強制**：サーバ側で必ず `Submission.user_id == current_user.id` を WHERE に含める（実装制約、→ [.claude/rules/backend.md](../../../.claude/rules/backend.md): where 条件の必須ルール）
- **集計はリアルタイム計算**：事前集計テーブル不要（実装方針、MVP 規模では集計クエリで十分）

## スコープ外（このスプリントでは扱わない）

- 弱点に基づく問題生成（[適応型出題](../5-roadmap/01-roadmap.md#適応型出題)）
- 学習目標の設定（「1 日 3 問」等）
- ストリーク（連続解答日数）・バッジ・ゲーミフィケーション
- 期間指定での集計（直近 30 日など）
- 学習履歴のエクスポート機能
- 他ユーザーの履歴閲覧（プライバシー観点で当面実装しない）
- リアルタイムランキング
- グラフ可視化（MVP はテーブル表示で十分、必要なら別途）

## 機能一覧

このドメインで提供する操作の全体俯瞰。詳細仕様は下の各 HOW セクション + OpenAPI（`apps/api/openapi.json`）が SSoT。

| 操作 | 対象ロール | 認証 | 概要 |
|---|---|---|---|
| 自分の解答履歴一覧 | 認証ユーザー | 必須 | `GET /submissions?page=N` でページネーション付き履歴（[自動採点](./grading.md) で詳細）|
| 全体正答率・カテゴリ別習熟度 | 認証ユーザー | 必須 | `GET /me/stats` で全期間の集計を取得 |
| 弱点カテゴリ集計 | 認証ユーザー | 必須 | `GET /me/weakness` で正答率の低いカテゴリ Top N を取得 |

## データモデル

詳細は [3-cross-cutting/01-data-model.md](../3-cross-cutting/01-data-model.md) を参照。

- `submissions`：解答送信ごとに作成（[自動採点](./grading.md) で詳細）。`user_id`, `problem_id`, `status`, `score`, `created_at`, `graded_at` を集計に使用
- `problems`：カテゴリ・難易度を取得する目的で JOIN 対象

集計クエリイメージ（SQL の概念形、実装は SQLAlchemy 2.0 で書く）：

```sql
-- 正答率（全期間）
SELECT
  COUNT(*) AS total,
  COUNT(*) FILTER (WHERE score = totalCount) AS correct
FROM submissions
WHERE user_id = $1 AND status = 'graded';

-- カテゴリ別習熟度
SELECT
  p.category,
  COUNT(*) AS attempts,
  COUNT(*) FILTER (WHERE s.score = s.totalCount) AS correct
FROM submissions s
JOIN problems p ON p.id = s.problem_id
WHERE s.user_id = $1 AND s.status = 'graded'
GROUP BY p.category;
```

## 画面

### 学習履歴一覧画面（対象：認証ユーザー）

- **ルート**：`/me/history`
- **概要**：自分の解答履歴を新しい順に一覧表示
- **主要コンポーネント**：`<SubmissionHistoryList />`、`<PaginationControl />`
- **使用 API**：
  - `GET /submissions?page=...` — 自分の解答履歴
- **主要インタラクション**：
  - 行クリックで対応する問題詳細（`/problems/:id`）へ遷移
  - ページネーション

### 統計画面（対象：認証ユーザー）

- **ルート**：`/me/stats`
- **概要**：全期間の正答率・カテゴリ別習熟度を表示
- **主要コンポーネント**：
  - `<OverallStatsCard />`（全体正答率）
  - `<CategoryMasteryTable />`（カテゴリ別習熟度）
- **使用 API**：
  - `GET /me/stats`

### 弱点カテゴリ画面（対象：認証ユーザー）

- **ルート**：`/me/weakness`
- **概要**：弱点カテゴリ Top N を表示し、対応する問題への遷移を提供
- **主要コンポーネント**：`<WeaknessList />`、`<PracticeButton />`（[適応型出題](../5-roadmap/01-roadmap.md#適応型出題) で問題生成導線、R6 以降）
- **使用 API**：
  - `GET /me/weakness`

### マイページ（オプション、対象：認証ユーザー）

- **ルート**：`/me`
- **概要**：上記 3 画面へのナビゲーション + サマリ
- 必要性が出た段階で実装。MVP では各 `/me/*` への直接アクセスで十分。

## ユーザーフロー

複雑なフロー無し。メニューから各画面に遷移し、API 呼び出しで集計結果を取得して表示するだけ。

## API

| メソッド | パス | 用途 | 認証 |
|---|---|---|---|
| GET | `/submissions` | 自分の解答履歴一覧（ページネーション可） | 必須 |
| GET | `/me/stats` | 自分の正答率・カテゴリ別習熟度 | 必須 |
| GET | `/me/weakness` | 弱点カテゴリ集計 | 必須 |

機械可読の最新仕様は OpenAPI（`apps/api/openapi.json`、ランタイムは FastAPI の `/openapi.json`）が SSoT。

### JSON 例

`GET /me/stats` レスポンス：
```json
{
  "total": 42,
  "correct": 30,
  "accuracy": 0.714,
  "byCategory": [
    { "category": "array",     "attempts": 10, "correct": 8, "accuracy": 0.8 },
    { "category": "recursion", "attempts": 5,  "correct": 1, "accuracy": 0.2 }
  ]
}
```

`GET /me/weakness` レスポンス：
```json
{
  "weakCategories": [
    { "category": "recursion", "attempts": 5, "correct": 1, "accuracy": 0.2 },
    { "category": "async",     "attempts": 4, "correct": 2, "accuracy": 0.5 }
  ]
}
```

## バリデーション

| フィールド | ルール | エラーメッセージ |
|---|---|---|
| `page` (Query) | 任意、整数、1 以上 | ページ番号が不正です |

## 受け入れ条件（Definition of Done）

> 外部から観測可能な振る舞いに絞る。所有権チェックや永続保存方針はビジネスルール参照。

- [ ] `/me/history` で自分の解答履歴一覧（問題タイトル / 結果 / 所要時間 / 解答日時）が表示される
- [ ] `/me/stats` で正答率・カテゴリ別習熟度（解答数・正解数）が表示される
- [ ] `/me/weakness` で弱点カテゴリ（正答率の低いカテゴリ Top N）が表示される
- [ ] 同一問題に複数回解答した場合、すべての履歴が一覧に残る（上書きされていない）
- [ ] 他ユーザーの `submissions` / `me/stats` / `me/weakness` には 403 / 404 が返って閲覧不可
- [ ] 統計はリアルタイム計算で取得時点の値が返る（事前集計のキャッシュ古さ問題が発生しない）

## ステータス

タスク単位の細目チェック（リリース単位の進捗は [01-roadmap.md](../5-roadmap/01-roadmap.md) を参照）。

- [ ] 要件定義完了
- [ ] バックエンド実装完了（me/stats / me/weakness ルーター、または submissions の拡張）
- [ ] フロントエンド実装完了（履歴一覧 / 統計 / 弱点画面）
- [ ] ユニットテスト完了（pytest：集計ロジックの正確性、→ [ADR 0038](../../adr/0038-test-frameworks.md)）
- [ ] E2E テスト完了（解答送信 → 履歴反映 → 統計画面表示の主要フロー、Playwright）
- [ ] **受け入れ条件すべて満たす**
- [ ] PR マージ済み

## 関連

- **関連機能**：
  - [自動採点](./grading.md)（履歴の元データを生成）
  - [適応型出題](../5-roadmap/01-roadmap.md#適応型出題)（弱点情報を活用）
- **関連 ADR**：
  - [ADR 0034: バックエンドフレームワークに FastAPI](../../adr/0034-fastapi-for-backend.md)
  - [ADR 0037: SQLAlchemy 2.0 + Alembic](../../adr/0037-sqlalchemy-alembic-for-database.md)
- **横断要件**：
  - データモデル：[3-cross-cutting/01-data-model.md](../3-cross-cutting/01-data-model.md)
  - API 仕様：[3-cross-cutting/02-api-conventions.md](../3-cross-cutting/02-api-conventions.md#機能別エンドポイント一覧)
- **実装ルール**：[.claude/rules/backend.md](../../../.claude/rules/backend.md)
