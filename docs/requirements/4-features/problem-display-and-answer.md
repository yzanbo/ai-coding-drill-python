# 問題表示・解答入力

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

- **役割**：ゲスト / 認証ユーザー（プログラミング学習者）
- **やりたいこと**：問題一覧から興味のある問題を選び、コードエディタで解答を書いて実行できる
- **得られる価値**：実際にコードを書いてプログラミング能力を試せる

<!-- 複数のロールが関わる場合は同じ 3 行セットを並べてよい -->

## 概要

問題の閲覧と解答入力に特化した画面群。**問題一覧（`/problems`）はゲスト含む全員が閲覧可能**、**問題詳細（`/problems/:id`）と解答送信はログインユーザー専用**。コードエディタはサーバ採点前に**ブラウザ内で型診断・補完**を提供し、UX を向上させる。

## ビジネスルール

- **問題一覧（`/problems`）はゲストでも閲覧可**：ポートフォリオとして「触ってみる」体験を妨げないため
- **問題詳細（`/problems/:id`）と解答送信は認証必須**：解答送信と一体の UX に揃え、未ログインアクセス時は `LoginRequiredMessage` 案内ページを表示する。履歴・統計の前提として認証が必要なため、詳細画面まで踏み込ませる前にログイン誘導する
- **テストケースの一部をマスク**：「入出力例」として一部を見せ、残りは隠す。完全公開すると LLM やコピペで簡単に通せてしまう
- **コードエディタはサーバ採点前にブラウザ内で型診断**：構文エラーレベルのコードがサーバに送られるのを減らし、サンドボックスコストを節約（CodeMirror 6 + `@typescript/vfs`、→ [ADR 0015](../../adr/0015-codemirror-over-monaco.md)）
- **エディタ内容はローカルストレージに自動保存**：誤遷移時の復元（任意機能）

## スコープ外（このスプリントでは扱わない）

- 採点ロジック自体（[自動採点](./grading.md)）
- LLM ヒント機能（[LLM ヒント](../5-roadmap/01-roadmap.md#llm-ヒント機能)）
- 解答コードの SNS 共有
- お気に入り問題保存（必要性が出てから検討）
- 多言語対応（MVP は TypeScript のみ。言語アダプタ層で将来拡張）

## 機能一覧

このドメインで提供する操作の全体俯瞰。詳細仕様は下の各 HOW セクション + OpenAPI（`apps/api/openapi.json`）が SSoT。

| 操作 | 対象ロール | 認証 | 概要 | 詳細 |
|---|---|---|---|---|
| 問題一覧表示 | ゲスト / 認証ユーザー | 任意 | `GET /problems` でカテゴリ・難易度フィルタ付きリストを取得 | [#問題一覧画面対象ゲスト--認証ユーザー](#問題一覧画面対象ゲスト--認証ユーザー) |
| 問題詳細表示 | 認証ユーザー | 必須 | `GET /problems/:id` で問題文・入出力例を取得（テストケースの一部はマスク）。未ログインは案内ページ | [#問題詳細解答画面対象認証ユーザー](#問題詳細解答画面対象認証ユーザー) |
| 解答送信（実行ボタン） | 認証ユーザー | 必須 | [`POST /submissions`](./grading.md#post-submissions) で解答を送信 → 採点フローへ（API 詳細は [grading.md](./grading.md#post-submissions) が所有） | [#問題閲覧--解答送信フロー対象認証ユーザー](#問題閲覧--解答送信フロー対象認証ユーザー) |

## データモデル

> **関わるテーブル名の列挙のみ**。カラム定義・関係詳細は書かない（drift 防止）。スキーマの SSoT は SQLAlchemy model（`apps/api/app/models/`、→ [ADR 0037](../../adr/0037-sqlalchemy-alembic-for-database.md)）、全体俯瞰は [3-cross-cutting/01-data-model.md](../3-cross-cutting/01-data-model.md)。

関わるテーブル：`problems` / `submissions`

## 画面

### 問題一覧画面（対象：ゲスト / 認証ユーザー）

- **ルート**：`/problems`
- **目的**：カテゴリ・難易度でフィルタしながら問題を探す
- **使用 API**：
  - `GET /problems?category=...&difficulty=...&page=...` — 一覧取得（フィルタ・ページネーション）
- **主要インタラクション**：
  - フィルタ変更で URL クエリが書き換わり、リロード・共有しても同じ絞り込み結果に戻れる
  - ページ上部に「新規問題を生成」ボタンを常設し、`/problems/new`（[問題生成リクエスト](./problem-generation.md#問題生成画面対象認証ユーザー)）への入口とする。ゲストが押した場合は `/login?next=/problems/new` にリダイレクト

### 問題詳細・解答画面（対象：認証ユーザー）

- **ルート**：`/problems/:id`
- **目的**：問題文・入出力例を読みながらコードを書いて解答送信する
- **認証**：**必須**。未ログインでアクセスした場合は「ログインが必要です」案内ページ
  （`LoginRequiredMessage`）を表示し、`/login?next=/problems/:id` への CTA を提示する。
  問題一覧（`/problems`）はゲストにも見せるが、詳細画面は解答送信と一体のため
  ログインを前提とする UX に揃える。
- **使用 API**：
  - `GET /problems/:id` — 問題詳細取得（テストケース一部マスク）
  - [`POST /submissions`](./grading.md#post-submissions) — 解答送信（[grading.md](./grading.md#post-submissions) が所有）
- **主要インタラクション**：
  - エディタ内容はローカルストレージに自動保存（誤遷移時に復元）
  - ブラウザ内の型診断がインラインに表示される（CodeMirror 6 + `@typescript/vfs`）
  - 「実行」押下時、未認証なら `/login?next=...` にリダイレクトしてから戻る
    （未認証時は本画面自体が出ないため通常は発火しないが、セッション失効中の保険）
  - 採点結果は同画面下部の領域に表示される（[自動採点](./grading.md) のポーリングフロー）
  - テストケースの一部のみ「入出力例」として表示し、残りはレスポンス上もマスクされる

## ユーザーフロー

### 問題閲覧 → 解答送信フロー（対象：認証ユーザー）

線形 + 末尾で分岐するため箇条書きで足りる（→ docs-rules.md §8）：

1. 問題一覧を閲覧 — 問題一覧画面（`/problems`）
2. カテゴリ・難易度でフィルタ — 問題一覧画面
3. 問題行をクリックして詳細画面へ遷移 — 問題詳細・解答画面（`/problems/:id`）
4. 問題文・入出力例を読み、コードエディタで TypeScript コードを書く — 問題詳細・解答画面
5. ブラウザ内型診断で構文・型エラーを修正 — 問題詳細・解答画面（エディタ部分）
6. 「実行」ボタンを押下 — 問題詳細・解答画面
7. `POST /submissions` で解答送信、採点フローへ — Backend（→ [grading.md#post-submissions](./grading.md#post-submissions)）
8. 採点結果をポーリングしながら待つ — 問題詳細・解答画面
9. 結果表示（全通過 = 正解 / 一部失敗 = 失敗ケース表示）— 問題詳細・解答画面

### ゲストが解答送信を試みた場合（対象：ゲスト）

1. 「実行」ボタンを押下 — 問題詳細・解答画面（`/problems/:id`）
2. [`GET /auth/me`](./authentication.md#get-authme) で未認証を確認し、`/login?next=/problems/:id` にリダイレクトされる — ログイン画面
3. ログイン完了後、元の問題画面に戻って解答送信を続行できる — 問題詳細・解答画面

## API

<!--
本セクションは API-first 設計の SSoT（実装前の契約）。以下 4 ステップを必ず意識する：

  1. API 設計：このセクションで API テーブル + JSON 例を先に書く（実装前）
  2. バックエンド実装：/backend-implement が本セクションに沿って Pydantic + FastAPI を実装
  3. API の吐き出し：mise run api:openapi-export で apps/api/openapi.json を出力
  4. API 設計をバックエンド実装に合わせて更新：差分があれば本セクションを追従更新
     （実装が SSoT、本セクションは契約の鏡）

所有権ルール：本ドメインは `/problems` 系（一覧 / 詳細）を所有する。`POST /submissions` は
[grading.md](./grading.md#post-submissions) が所有しており、ここでは参照のみ。
-->

| メソッド | パス | 用途 | 認証 | 詳細 |
|---|---|---|---|---|
| GET | `/problems` | 問題一覧（カテゴリ・難易度フィルタ可） | 任意 | [#get-problems](#get-problems) |
| GET | `/problems/:id` | 問題詳細（テストケースの一部はマスク） | 任意 | [#get-problemsid](#get-problemsid) |

機械可読の最新仕様は OpenAPI（`apps/api/openapi.json`、ランタイムは FastAPI の `/openapi.json`）が SSoT。`POST /submissions` は [grading.md#post-submissions](./grading.md#post-submissions) を参照（本ファイルでは重複させない）。

### JSON 例

#### GET /problems

- 認証：任意（ゲストでも閲覧可）
- 使う feature：[problem-display-and-answer.md](./problem-display-and-answer.md)
- クエリパラメータ：`category` / `difficulty` / `page`（既定 1）
- レスポンス 200:

```json
{
  "items": [
    {
      "id": "<uuid>",
      "title": "配列の合計を返す",
      "category": "array",
      "difficulty": "easy"
    }
  ],
  "page": 1,
  "totalPages": 10
}
```

#### GET /problems/:id

- 認証：任意（ゲストでも閲覧可）
- 使う feature：[problem-display-and-answer.md](./problem-display-and-answer.md)
- レスポンス 200（テストケースは一部のみ `examples` として公開、残りはレスポンス上もマスク）:

```json
{
  "id": "<uuid>",
  "title": "配列の合計を返す",
  "description": "数値配列を受け取り、その合計を返す関数 `solve` を実装してください。",
  "examples": [
    { "input": "[1,2,3]", "output": "6" }
  ],
  "category": "array",
  "difficulty": "easy"
}
```

## 受け入れ条件（Definition of Done）

> **役割**：プロダクトとして "完成した" と言える条件。**ユーザー / API クライアントから観測可能なふるまい** だけに絞る。「DB 上で○○」「Depends で○○」等の実装制約はビジネスルールに書く。
>
> **長期運用**：機能の振る舞い仕様の累積。機能が育つほど条件は**追加されていく**し、既存条件も仕様変更で**更新される**。**変更・追加された条件は再検証が必要なので未チェックに戻す**（既存で変わってない条件はチェック維持、全リセットはしない）。観測可能な振る舞いが変わったらここを直すのが SSoT 更新の第一歩。過去版の履歴は git log で辿る。

- [x] `/problems` で問題一覧（タイトル / カテゴリ / 難易度）が表示される
- [x] カテゴリ・難易度でフィルタした結果が表示される
- [x] ゲストでも問題一覧（`/problems`）を閲覧できる（401 にならない）
- [ ] 未ログインで `/problems/:id` を踏むと「ログインが必要です」案内ページが表示される（問題本文は読めない）
- [x] 一覧画面のヘッダー領域に「新規問題を生成」ボタンがあり、`/problems/new`（[問題生成リクエスト](./problem-generation.md)）に遷移できる（ゲストの場合はログイン経由）
- [x] `/problems/:id` で問題詳細（問題文・入出力例）が表示される
- [x] **問題詳細レスポンスでテストケースの一部はマスクされる**（API レスポンスから完全な test_cases が読み出せないこと）
- [x] コードエディタで TypeScript コードを入力できる
- [ ] エディタにインライン型診断・補完が出る（構文・型エラーがハイライトされる）<!-- R1-4 では構文ハイライトのみ。`@typescript/vfs` を使った型診断・補完は別途実装、→ [5-roadmap/01-roadmap.md: Next バックログ](../5-roadmap/01-roadmap.md#next次スプリント候補すべて-r2) -->
- [x] 「実行」ボタン押下で解答を送信できる<!-- R1-4 で POST /api/submissions の最小実装（status='pending' で 202）まで。jobs INSERT + NOTIFY による採点ジョブ enqueue は R1-5。 -->
- [x] ゲストが `/problems/:id` を直接踏むと案内ページが出て、`/login?next=/problems/:id` の CTA からログインへ進める（「実行」ボタン経由のフォールバックは案内ページが上流で吸収）
- [ ] 解答送信後、同画面で採点結果が表示される（→ [自動採点](./grading.md)）<!-- R1-5 のスコープ。R1-4 では submissionId のフィードバック表示までで止めている。 -->

## ステータス

> **役割**：開発工程としてどこまで進んだかのチェックリスト（"プロダクトの完成条件" は上の受け入れ条件、"リリース単位の進捗" は [01-roadmap.md](../5-roadmap/01-roadmap.md) で管理）。
>
> **長期運用**：機能を再着手・大きく改修するたびに**チェックを外してリセットする**（過去の完了履歴は残さない、履歴は git log と PR で辿る）。常に「この機能の現在の状態」だけを映す鏡として使う。

- [x] バックエンド実装完了（problems ルーター / テストケース マスキングロジック / submissions 最小実装）
- [x] バックエンドユニットテスト完了（pytest、→ [ADR 0038](../../adr/0038-test-frameworks.md)）
- [x] フロントエンド実装完了（一覧 / 詳細・エディタ画面、構文ハイライト + 実行ボタン分岐まで）
- [x] フロントエンドユニットテスト完了（Vitest、→ [ADR 0038](../../adr/0038-test-frameworks.md)）
- [x] E2E テスト完了（一覧 → 詳細 → 解答送信受付までの主要フロー、Playwright、→ [ADR 0038](../../adr/0038-test-frameworks.md)）<!-- 採点結果表示までの "結果表示" 完走は R1-5 で再検証する -->
- [ ] **受け入れ条件すべて満たす**<!-- インライン型診断と採点結果表示の 2 項目が未充足。前者は Next バックログ、後者は R1-5 で潰す。 -->

## 関連

- **関連機能**：
  - [問題生成リクエスト](./problem-generation.md)（ここで生成された問題が一覧に出る）
  - [自動採点](./grading.md)（実行ボタンの先のフロー）
  - [学習履歴](./learning.md)（解答が履歴に記録される）
- **関連 ADR**：
  - [ADR 0015: CodeMirror 6 採用（Monaco 不採用）](../../adr/0015-codemirror-over-monaco.md)
  - [ADR 0034: バックエンドフレームワークに FastAPI](../../adr/0034-fastapi-for-backend.md)
  - [ADR 0036: フロントエンドのみ pnpm workspaces（Turborepo 不採用）](../../adr/0036-frontend-monorepo-pnpm-only.md)
  - [ADR 0042: フロントエンドのデータフェッチ戦略（TanStack Query を本機能着手時に導入）](../../adr/0042-frontend-data-fetching-tanstack-query.md)
- **横断要件**：
  - フロントエンド技術選定：[2-foundation/05-runtime-stack.md](../2-foundation/05-runtime-stack.md#フロントエンド)
  - API 仕様（問題関連）：[3-cross-cutting/02-api-conventions.md](../3-cross-cutting/02-api-conventions.md#機能別エンドポイント一覧)
