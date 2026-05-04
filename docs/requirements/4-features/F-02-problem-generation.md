# F-02: 問題生成リクエスト

## ユーザーストーリー

As a **認証ユーザー（プログラミング学習者）**
I want **カテゴリと難易度を指定して新しい TypeScript 問題を生成リクエストしたい**
So that **既存の問題に縛られず、自分の興味・弱点に応じた練習問題を無限に得られるようにしたいから**

## 受け入れ条件（Definition of Done）

- [ ] 問題生成画面でカテゴリ（文字列処理 / 配列操作 / 再帰 / 非同期処理 / 型パズル 等）と難易度（easy / medium / hard）を選択して送信できる
- [ ] 送信後、API は `202 Accepted` + `requestId` を即座に返す（同期で待たせない）
- [ ] 生成中はステータス画面で「生成中…」と表示され、ポーリングで進捗を取得する
- [ ] 生成成功時：新規作成された問題ページに自動遷移する
- [ ] 生成失敗時（最大 3 回再生成しても全失敗）：失敗ステータスを表示し、再試行ボタンを提供する
- [ ] **サンドボックス検証で模範解答が全テストケースを通過した問題のみ DB に保存される**（→ [03-llm-pipeline.md](../2-foundation/03-llm-pipeline.md)）
- [ ] **LLM-as-a-Judge スコアが閾値以上の問題のみ保存される**（R2 以降）
- [ ] 生成リクエストのコスト（USD）と所要時間が観測ログに記録される（→ [04-observability.md](../2-foundation/04-observability.md)）
- [ ] レート制限：同一ユーザーで `1 分 / 5 回` を超えると `429` を返す（→ [02-api-conventions.md](../3-cross-cutting/02-api-conventions.md#レート制限)）

## 概要

LLM に問題本文・入出力例・テストケース・模範解答を生成させる機能。LLM の出力を信用せず、サンドボックス実行で動作保証してから DB に保存する点が本サービスの差別化軸。

## ビジネスルール

- **LLM の出力をそのまま信用しない**：必ずサンドボックス検証 + Judge を通したものだけを保存（→ [CLAUDE.md](../../../.claude/CLAUDE.md) 設計思想）
- **生成と Judge は別プロバイダ・別モデル**：自己評価バイアス回避（→ [ADR 0009](../../adr/0009-custom-llm-judge.md)）
- **モデル段階利用**：初回は低コスト・高速モデル、再生成時に上位モデル、Judge は中位モデル（→ [03-llm-pipeline.md: コスト最適化](../2-foundation/03-llm-pipeline.md#コスト最適化)）
- **同一プロンプトの結果は Redis キャッシュで再利用**（TTL 7 日、`prompt_hash` をキー）
- **生成ジョブの trace_id はリクエストから採点完了まで連結**（→ [ADR 0017](../../adr/0017-w3c-trace-context-in-job-payload.md)）

## スコープ外（このスプリントでは扱わない）

- 学習履歴・弱点に基づく適応生成（[F-06: 適応型出題](../5-roadmap/01-roadmap.md#f-06-適応型出題) で別途実装）
- ユーザーが独自プロンプトを書ける生成モード（プロンプトインジェクションリスクのため当面実装しない）
- 複数問題のバッチ生成（必要性が出てから検討）
- 問題の差し替え・再生成リクエスト（モデル変更後の品質再評価バッチは R7 で）
- 問題の手動編集機能（管理ダッシュボード [F-08] で扱う）

## データモデル

詳細は [3-cross-cutting/01-data-model.md](../3-cross-cutting/01-data-model.md) を参照。

- `generation_requests`：生成リクエストの状態管理（`requestId`, `category`, `difficulty`, `status`, `produced_problem_id?`）
- `problems`：生成成功した問題（`title`, `description`, `examples`, `test_cases`, `reference_solution`, `judge_scores?`）
- `jobs`：問題生成ジョブのキューイング（`type='generate-problem'`, `payload`, `state`）。詳細は [ADR 0001](../../adr/0001-postgres-as-job-queue.md)

## 画面

### 問題生成画面（対象：認証ユーザー）

- **ルート**：`/problems/new`
- **概要**：カテゴリ・難易度を選択して生成をリクエストする画面
- **主要コンポーネント**：`<GenerateProblemForm />`、`<CategorySelector />`、`<DifficultySelector />`
- **使用 API**：
  - `POST /problems/generate` — 生成リクエスト（202 + requestId）
- **主要インタラクション**：
  - フォーム送信で `requestId` を取得し、生成ステータス画面に遷移

### 生成ステータス画面（対象：認証ユーザー）

- **ルート**：`/problems/generate/:requestId`
- **概要**：非同期生成の進捗を表示し、完了したら問題詳細へ自動遷移
- **主要コンポーネント**：`<GenerationStatus />`（TanStack Query で 1〜2 秒間隔ポーリング）
- **使用 API**：
  - `GET /problems/generate/:requestId` — ステータス取得
- **主要インタラクション**：
  - `status === 'completed'` → `/problems/:problemId` へリダイレクト
  - `status === 'failed'` → エラー表示 + 再試行ボタン

## ユーザーフロー

### 問題生成フロー（対象：認証ユーザー）

1. ユーザーが `/problems/new` でカテゴリ・難易度を選択して送信
2. NestJS が `INSERT INTO generation_requests` + `INSERT INTO jobs (type='generate-problem', ...)` + `NOTIFY new_job` を同一トランザクションで実行
3. NestJS が `202 { requestId, status: 'pending' }` を返す
4. ユーザーは `/problems/generate/:requestId` に遷移、ポーリング開始
5. Go ワーカーが NOTIFY を受信、ジョブ取得
6. ワーカーが LLM 呼び出し（生成プロバイダ） → 構造化出力 → JSON Schema バリデーション
7. 模範解答をサンドボックスで実行 → 全テスト通過確認
8. LLM-as-a-Judge（別プロバイダ）で品質評価 → 閾値クリア
9. 通過したら `INSERT INTO problems` + `UPDATE generation_requests SET status='completed', produced_problem_id=...`
10. ユーザーのポーリングで `status='completed'` を受信 → 問題詳細画面へ自動遷移

失敗系：

- LLM 出力スキーマ違反 / サンドボックス失敗 → 上位モデルで最大 3 回再生成
- Judge スコア不合格 → 上位モデルで再生成
- 全試行失敗 → `status='failed'`、ユーザーに再試行ボタン提示

## API

| メソッド | パス | 用途 | 認証 |
|---|---|---|---|
| POST | `/problems/generate` | 生成リクエスト（202 + requestId 即返） | 必須 |
| GET | `/problems/generate/:requestId` | 生成ステータス取得（ポーリング用） | 必須 |

機械可読の最新仕様は OpenAPI（`/api/docs/openapi.json`）が SSoT。

### リクエスト・レスポンス例

`POST /problems/generate`：
```json
{
  "category": "array",
  "difficulty": "easy"
}
```

レスポンス（202）：
```json
{
  "requestId": "<uuid>",
  "status": "pending"
}
```

`GET /problems/generate/:requestId`：
```json
{
  "requestId": "<uuid>",
  "status": "completed",
  "problemId": "<uuid>"
}
```

## バリデーション

| フィールド | ルール | エラーメッセージ |
|---|---|---|
| `category` | 必須、許可値リスト内 | カテゴリを指定してください |
| `difficulty` | 必須、`easy` / `medium` / `hard` のいずれか | 難易度を指定してください |

## 関連

- **関連機能**：
  - [F-03: 問題表示・解答](./F-03-problem-display-and-answer.md)（生成された問題はここで使われる）
  - [F-04: 自動採点](./F-04-auto-grading.md)（生成時のサンドボックス検証は採点と同じ仕組み）
- **関連 ADR**：
  - [ADR 0001: Postgres ジョブキュー](../../adr/0001-postgres-as-job-queue.md)
  - [ADR 0009: LLM-as-a-Judge を自前実装](../../adr/0009-custom-llm-judge.md)
  - [ADR 0011: LLM プロバイダ抽象化](../../adr/0011-llm-provider-abstraction.md)
  - [ADR 0017: W3C Trace Context をジョブペイロードに埋め込む](../../adr/0017-w3c-trace-context-in-job-payload.md)
- **横断要件**：
  - LLM パイプライン：[2-foundation/03-llm-pipeline.md](../2-foundation/03-llm-pipeline.md)
  - レート制限：[2-foundation/01-non-functional.md](../2-foundation/01-non-functional.md)
  - 観測性：[2-foundation/04-observability.md](../2-foundation/04-observability.md)
- **実装ルール**：[backend.md](../../../.claude/rules/backend.md)、[prompts.md](../../../.claude/rules/prompts.md)

## ステータス

- [ ] 要件定義完了
- [ ] バックエンド実装完了（GenerationModule / LlmProvider 抽象化）
- [ ] ワーカー実装完了（生成ジョブ処理）
- [ ] フロントエンド実装完了（生成画面 / ステータス画面）
- [ ] ユニットテスト完了
- [ ] E2E テスト完了（生成 → 完了 → 問題遷移の主要フロー）
- [ ] 受け入れ条件すべて満たす
- [ ] PR マージ済み

## スプリント情報

- **対象スプリント**：Sprint 2（MVP コア機能）
- **ストーリーポイント**：未確定
- **担当**：神保
- **着手日 / 完了日**：未着手 / 未完了
