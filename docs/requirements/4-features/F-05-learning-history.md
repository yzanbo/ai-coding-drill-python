# F-05: 学習履歴・統計

## ユーザーストーリー

As a **認証ユーザー（プログラミング学習者）**
I want **過去に解いた問題と正誤、所要時間、弱点カテゴリを確認できる**
So that **自分の進捗を把握し、苦手分野を意識的に練習できるようにしたいから**

## 受け入れ条件（Definition of Done）

- [ ] `/me/history` で自分の解答履歴一覧（問題タイトル / 結果 / 所要時間 / 解答日時）が表示される
- [ ] `/me/stats` で正答率・カテゴリ別習熟度（解答数・正解数）が表示される
- [ ] `/me/weakness` で弱点カテゴリ（正答率の低いカテゴリ Top N）が表示される
- [ ] 同一問題に複数回解答した場合、すべての履歴が残る（上書きしない）
- [ ] **他のユーザーの履歴・統計は閲覧不可**（API レベルで `submissions.user_id = currentUser.id` を強制）
- [ ] 履歴・統計は永続保存される（[CLAUDE.md](../../../.claude/CLAUDE.md) の「ハードデリート方針」に従い、ソフトデリートは行わない）
- [ ] 統計の集計は API でリアルタイム計算（MVP は事前集計テーブル不要）

## 概要

ユーザーが自分の学習進捗を可視化するための機能。MVP は単純な集計（正答率・カテゴリ別習熟度・弱点カテゴリ Top N）のみ。R6 以降の「適応型出題」（[F-06](../5-roadmap/01-roadmap.md#f-06-適応型出題)）の前提データとなる。

## ビジネスルール

- **履歴は不可逆に蓄積**：解答送信ごとに 1 レコード作成、削除・上書きしない
- **正答 = 全テストケース通過**（部分点は MVP では考慮しない）
- **弱点カテゴリの定義**：正答率が一定以下（例：50% 未満）かつ解答数が一定以上（例：3 問以上）のカテゴリを抽出
- **習熟度の集計範囲**：全期間（MVP）。期間指定（過去 30 日など）は将来機能
- **問題が削除された場合**：MVP では問題削除機能自体がないため考慮不要
- **ゲストは履歴対象外**：認証必須機能なので未認証ユーザーには履歴が存在しない

## スコープ外（このスプリントでは扱わない）

- 弱点に基づく問題生成（[F-06: 適応型出題](../5-roadmap/01-roadmap.md#f-06-適応型出題)）
- 学習目標の設定（「1 日 3 問」等）
- ストリーク（連続解答日数）・バッジ・ゲーミフィケーション
- 期間指定での集計（直近 30 日など）
- 学習履歴のエクスポート機能
- 他ユーザーの履歴閲覧（プライバシー観点で当面実装しない）
- リアルタイムランキング
- グラフ可視化（MVP はテーブル表示で十分、必要なら別途）

## データモデル

詳細は [3-cross-cutting/01-data-model.md](../3-cross-cutting/01-data-model.md) を参照。

- `submissions`：解答送信ごとに作成（[F-04](./F-04-auto-grading.md) で詳細）。`user_id`, `problem_id`, `status`, `score`, `created_at`, `graded_at` を集計に使用
- `problems`：カテゴリ・難易度を取得する目的で JOIN 対象

集計クエリイメージ（Drizzle 等価）：

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
- **主要コンポーネント**：`<WeaknessList />`、`<PracticeButton />`（[F-06](../5-roadmap/01-roadmap.md#f-06-適応型出題) で問題生成導線、R6 以降）
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

機械可読の最新仕様は OpenAPI（`/api/docs/openapi.json`）が SSoT。

### レスポンス例

`GET /me/stats`：
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

`GET /me/weakness`：
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

サーバ側で必ず `eq(submissions.user_id, currentUser.id)` を WHERE に含める（→ [backend.md: where 条件の必須ルール](../../../.claude/rules/backend.md)）。

## 関連

- **関連機能**：
  - [F-04: 自動採点](./F-04-auto-grading.md)（履歴の元データを生成）
  - [F-06: 適応型出題](../5-roadmap/01-roadmap.md#f-06-適応型出題)（弱点情報を活用）
- **横断要件**：
  - データモデル：[3-cross-cutting/01-data-model.md](../3-cross-cutting/01-data-model.md)
  - API 仕様：[3-cross-cutting/02-api-conventions.md](../3-cross-cutting/02-api-conventions.md#機能別エンドポイント一覧)
  - ハードデリート方針：[backend.md](../../../.claude/rules/backend.md)
- **実装ルール**：[backend.md](../../../.claude/rules/backend.md)

## ステータス

- [ ] 要件定義完了
- [ ] バックエンド実装完了（StatsModule / WeaknessModule または Submissions の拡張）
- [ ] フロントエンド実装完了（履歴一覧 / 統計 / 弱点画面）
- [ ] ユニットテスト完了（集計ロジックの正確性）
- [ ] E2E テスト完了（解答送信 → 履歴反映 → 統計画面表示の主要フロー）
- [ ] 受け入れ条件すべて満たす
- [ ] PR マージ済み

## スプリント情報

- **対象スプリント**：Sprint 4（MVP 仕上げ）
- **ストーリーポイント**：未確定
- **担当**：神保
- **着手日 / 完了日**：未着手 / 未完了
