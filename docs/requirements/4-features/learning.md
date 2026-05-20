# 学習履歴・統計

<!--
配置先：`docs/requirements/4-features/<name>.md`（フラット配置、数値 ID なし）
新規作成・更新は `/new-requirements` カスタムコマンド経由を推奨。
セクション順序：WHY（ストーリー）→ WHAT（概要 / ビジネスルール / スコープ外）→
              機能一覧（全体俯瞰）→ HOW（データ / 画面 / フロー / API / バリデーション）
              → 完成検証（受入条件）→ 進捗（ステータス）→ 外部参照（関連）

長期運用の原則（このファイルを更新する全タイミングで適用）：
  1. コードや OpenAPI / SQLAlchemy から読み取れる事実は書かない。書くのは "なぜ"（業務理由）と "観測可能な振る舞い" だけ
  2. ファイル長は許容する（行数で分割しない）。分割トリガはドメイン境界のみ
  3. ビジネスルールが 30 行を超えたら H3 サブセクションに割る（壁を防ぐ）
  4. バリデーション節は業務上の理由があるルールのみ書く（必須・長さ等の機械的検証は Pydantic / Zod が SSoT）
  5. **HTML コメント（`<!--` で始まる注釈ブロック）は削除しない**（このコメント自身を含む）。CLAUDE が将来の更新時に運用ルールを再認識するための裏ルールとして埋め込まれているため、本文整理時にまとめて消さない
-->

## ユーザーストーリー

- **役割**：認証ユーザー（プログラミング学習者）
- **やりたいこと**：過去に解いた問題と正誤、所要時間、弱点カテゴリを確認できる
- **得られる価値**：自分の進捗を把握し、苦手分野を意識的に練習できる

<!-- 複数のロールが関わる場合は同じ 3 行セットを並べてよい -->

## 概要

ユーザーが自分の学習進捗を可視化するための機能。MVP は単純な集計（正答率・カテゴリ別習熟度・弱点カテゴリ Top N）のみ。R6 以降の「適応型出題」（[適応型出題](../5-roadmap/01-roadmap.md#適応型出題)）の前提データとなる。

## ビジネスルール

- **履歴は不可逆に蓄積**：解答送信ごとに 1 レコード作成、上書きしない
- **正答 = 全テストケース通過**（部分点は MVP では考慮しない）
- **弱点カテゴリの定義**：正答率が一定以下（例：50% 未満）かつ解答数が一定以上（例：3 問以上）のカテゴリを抽出
- **習熟度の集計範囲**：全期間（MVP）。期間指定（過去 30 日など）は将来機能
- **削除された問題の扱い**：`problems.deleted_at IS NOT NULL` の問題でも、過去の `submissions` 行は履歴として残るため、本人画面では「削除済問題への解答」として参照可能（タイトル表示等は実装時に検討）
- **ゲストは履歴対象外**：認証必須機能なので未認証ユーザーには履歴が存在しない
- **削除方針はソフトデリート**（→ [ADR 0048](../../adr/0048-soft-delete-for-user-facing-tables.md) / [01-data-model.md: 削除方針](../3-cross-cutting/01-data-model.md#削除方針ソフトデリート採用)）：
  - **本人画面（履歴一覧 / 詳細）**：`WHERE submissions.deleted_at IS NULL` を必ず付ける（ユーザーが削除した解答は表示しない）
  - **統計・集計クエリ（me/stats / me/weakness）**：`deleted_at` を**無視して全行を集計**する（削除しても統計に影響しない、履歴永続保存の意図を維持）
  - クエリ呼び出し側がフィルタの有無を選択する規約（暗黙フィルタを置かない）
- **所有権チェックの強制**：サーバ側で必ず `Submission.user_id == current_user.id` を WHERE に含める（実装制約、→ [.claude/rules/backend.md](../../../.claude/rules/backend.md): where 条件の必須ルール）
- **集計はリアルタイム計算**：事前集計テーブル不要（実装方針、MVP 規模では集計クエリで十分）
- **集計対象は採点完了行のみ**：`submissions.status = 'graded'` の行だけを `attempts` / `correct` の母数とする。`pending`（採点中）・`failed`（インフラ起因の失敗）は正答判定ができないためカウントしない
- **弱点抽出のしきい値**：`attempts >= 3` かつ `accuracy < 0.5` のカテゴリを対象とし、`accuracy` 昇順（同率は `attempts` 降順で tie-break）で **Top 5** までを返す

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

| 操作 | 対象ロール | 認証 | 概要 | 詳細 |
|---|---|---|---|---|
| 自分の解答履歴一覧 | 認証ユーザー | 必須 | [`GET /submissions`](./grading.md#get-submissions)`?page=N` でページネーション付き履歴（API 詳細は [grading.md](./grading.md#get-submissions) が所有）| [#学習履歴一覧画面対象認証ユーザー](#学習履歴一覧画面対象認証ユーザー) |
| 全体正答率・カテゴリ別習熟度 | 認証ユーザー | 必須 | `GET /me/stats` で全期間の集計を取得 | [#統計画面対象認証ユーザー](#統計画面対象認証ユーザー) |
| 弱点カテゴリ集計 | 認証ユーザー | 必須 | `GET /me/weakness` で正答率の低いカテゴリ Top N を取得 | [#弱点カテゴリ画面対象認証ユーザー](#弱点カテゴリ画面対象認証ユーザー) |

## データモデル

> **関わるテーブル名の列挙のみ**。カラム定義・関係詳細は書かない（drift 防止）。スキーマの SSoT は SQLAlchemy model（`apps/api/app/models/`、→ [ADR 0037](../../adr/0037-sqlalchemy-alembic-for-database.md)）、全体俯瞰は [3-cross-cutting/01-data-model.md](../3-cross-cutting/01-data-model.md)。

関わるテーブル：`submissions` / `problems`

## 画面

### 学習履歴一覧画面（対象：認証ユーザー）

- **ルート**：`/me/history`
- **目的**：自分の解答履歴を新しい順に一覧表示する
- **使用 API**：
  - [`GET /submissions`](./grading.md#get-submissions)`?page=...` — 自分の解答履歴（[grading.md](./grading.md#get-submissions) が所有）
- **主要インタラクション**：
  - 行クリックで対応する問題詳細（`/problems/:id`）へ遷移
  - 同一問題への複数回解答も独立した行として並ぶ（上書きされない）

### 統計画面（対象：認証ユーザー）

- **ルート**：`/me/stats`
- **目的**：全期間の正答率・カテゴリ別習熟度を表示する
- **使用 API**：
  - `GET /me/stats` — 全期間の正答率・カテゴリ別習熟度
- **主要インタラクション**：
  - 取得時点でリアルタイム集計するため、直前の解答が即時反映される

### 弱点カテゴリ画面（対象：認証ユーザー）

- **ルート**：`/me/weakness`
- **目的**：正答率の低いカテゴリ Top N を表示し、その分野の練習導線を提供する
- **使用 API**：
  - `GET /me/weakness` — 弱点カテゴリ Top N
- **主要インタラクション**：
  - 解答数が少ないカテゴリ（例：3 問未満）は弱点候補に含めない（サンプル不足で誤判定を避けるため）
  - 「練習する」ボタンは [適応型出題](../5-roadmap/01-roadmap.md#適応型出題) で R6 以降に有効化

### マイページ（オプション、対象：認証ユーザー）

- **ルート**：`/me`
- **目的**：上記 3 画面へのナビゲーション + サマリ。MVP では必須ではなく、必要性が出た段階で実装する。

## ユーザーフロー

複雑なフロー無し。メニューから各画面に遷移し、API 呼び出しで集計結果を取得して表示するだけ。

## API

<!--
本セクションは API-first 設計の SSoT（実装前の契約）。以下 4 ステップを必ず意識する：

  1. API 設計：このセクションで API テーブル + JSON 例を先に書く（実装前）
  2. バックエンド実装：/backend-implement が本セクションに沿って Pydantic + FastAPI を実装
  3. API の吐き出し：mise run api:openapi-export で apps/api/openapi.json を出力
  4. API 設計をバックエンド実装に合わせて更新：差分があれば本セクションを追従更新
     （実装が SSoT、本セクションは契約の鏡）

所有権ルール：本ドメインは `/me/*` 系エンドポイントを所有する。`GET /submissions` は
[grading.md](./grading.md#get-submissions) が所有しており、ここでは参照のみ。
-->

| メソッド | パス | 用途 | 認証 | 詳細 |
|---|---|---|---|---|
| GET | `/me/stats` | 自分の正答率・カテゴリ別習熟度 | 必須 | [#get-mestats](#get-mestats) |
| GET | `/me/weakness` | 弱点カテゴリ集計 | 必須 | [#get-meweakness](#get-meweakness) |

> 注記：`GET /submissions`（自分の解答履歴一覧）は [grading.md](./grading.md#get-submissions) が所有。本ファイルからはアンカーリンクで参照するのみ（重複させない）。

機械可読の最新仕様は OpenAPI（`apps/api/openapi.json`、ランタイムは FastAPI の `/openapi.json`）が SSoT。本セクションは API-first 設計の人間可読版 + 契約の鏡。

### JSON 例

#### GET /me/stats

- 認証：必須
- 使う feature：[learning.md](./learning.md)
- レスポンス 200:

```json
{
  "total": 42,
  "correct": 30,
  "accuracy": 0.714,
  "byCategory": [
    { "category": "array", "attempts": 10, "correct": 8, "accuracy": 0.8 },
    { "category": "recursion", "attempts": 5, "correct": 1, "accuracy": 0.2 }
  ]
}
```

#### GET /me/weakness

- 認証：必須
- 使う feature：[learning.md](./learning.md)
- レスポンス 200:

```json
{
  "weakCategories": [
    { "category": "recursion", "attempts": 5, "correct": 1, "accuracy": 0.2 }
  ]
}
```

## 受け入れ条件（Definition of Done）

> **役割**：プロダクトとして "完成した" と言える条件。**ユーザー / API クライアントから観測可能なふるまい** だけに絞る。「DB 上で○○」「Depends で○○」等の実装制約はビジネスルールに書く。
>
> **長期運用**：機能の振る舞い仕様の累積。機能が育つほど条件は**追加されていく**し、既存条件も仕様変更で**更新される**。**変更・追加された条件は再検証が必要なので未チェックに戻す**（既存で変わってない条件はチェック維持、全リセットはしない）。観測可能な振る舞いが変わったらここを直すのが SSoT 更新の第一歩。過去版の履歴は git log で辿る。

- [ ] `/me/history` で自分の解答履歴一覧（問題タイトル / 結果 / 所要時間 / 解答日時）が表示される
- [ ] `/me/stats` で正答率・カテゴリ別習熟度（解答数・正解数）が表示される
- [ ] `/me/weakness` で弱点カテゴリ（正答率の低いカテゴリ Top N）が表示される
- [ ] 同一問題に複数回解答した場合、すべての履歴が一覧に残る（上書きされていない）
- [ ] 他ユーザーの `submissions` / `me/stats` / `me/weakness` には 403 / 404 が返って閲覧不可
- [ ] 統計はリアルタイム計算で取得時点の値が返る（事前集計のキャッシュ古さ問題が発生しない）
- [ ] 履歴ゼロのユーザーが `/me/stats` / `/me/weakness` を叩いても 200 が返り、`total=0` / `byCategory=[]` / `weakCategories=[]` の空集計として表示される

## ステータス

> **役割**：開発工程としてどこまで進んだかのチェックリスト（"プロダクトの完成条件" は上の受け入れ条件、"リリース単位の進捗" は [01-roadmap.md](../5-roadmap/01-roadmap.md) で管理）。
>
> **長期運用**：機能を再着手・大きく改修するたびに**チェックを外してリセットする**（過去の完了履歴は残さない、履歴は git log と PR で辿る）。常に「この機能の現在の状態」だけを映す鏡として使う。

- [x] バックエンド実装完了（me/stats / me/weakness ルーター、または submissions の拡張）
- [ ] バックエンドユニットテスト完了（pytest、集計ロジックの正確性、→ [ADR 0038](../../adr/0038-test-frameworks.md)）
- [ ] フロントエンド実装完了（履歴一覧 / 統計 / 弱点画面）
- [ ] フロントエンドユニットテスト完了（Vitest、→ [ADR 0038](../../adr/0038-test-frameworks.md)）
- [ ] E2E テスト完了（解答送信 → 履歴反映 → 統計画面表示の主要フロー、Playwright、→ [ADR 0038](../../adr/0038-test-frameworks.md)）
- [ ] **受け入れ条件すべて満たす**

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
