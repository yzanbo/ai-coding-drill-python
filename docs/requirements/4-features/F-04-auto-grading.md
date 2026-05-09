# F-04: 自動採点

## ユーザーストーリー

As a **認証ユーザー（プログラミング学習者）**
I want **自分の解答コードを送信すると、自動で実行・採点されて結果が即座に返ってくる**
So that **手動レビューを待たず、即時フィードバックを受けて学習効率を最大化したいから**

## 受け入れ条件（Definition of Done）

- [ ] 「実行」ボタン押下で `POST /submissions` に解答が送信され、`202 Accepted` + `submissionId` が即返る
- [ ] フロントは `GET /submissions/:id` を 1〜2 秒間隔でポーリングし、採点結果を取得する
- [ ] 全テストケース通過 → 「正解」表示 + 通過数 / 全数（例：5/5）
- [ ] 一部失敗 → 失敗したテストケース名・期待値・実際の出力・差分を表示
- [ ] 構文エラー / 実行時例外 → スタックトレースを整形して表示
- [ ] タイムアウト（5 秒超過） → 「タイムアウト」と表示し、無限ループ等のヒントを示唆
- [ ] OOM / メモリ超過 → 「メモリ使用量超過」と表示
- [ ] 型パズル系カテゴリは型チェック（`tsc --noEmit` 想定）の型エラー有無で判定
- [ ] 採点はサンドボックス環境で実行され、ホストやネットワークに影響を与えない（→ [ADR 0009](../../adr/0009-disposable-sandbox-container.md)）
- [ ] サンドボックスは使い捨て（1 ジョブ = 1 コンテナ）
- [ ] 採点ジョブの trace_id がリクエストから採点結果取得まで連結される（→ [ADR 0010](../../adr/0010-w3c-trace-context-in-job-payload.md)）
- [ ] レート制限：同一ユーザーで `1 分 / 30 回` を超えると `429` を返す（→ [3-cross-cutting/02-api-conventions.md](../3-cross-cutting/02-api-conventions.md#レート制限)）
- [ ] 採点結果は `submissions` テーブルに永続保存され、後から `GET /submissions/:id` で再取得可能

## 概要

ユーザーの解答コードをサンドボックスで実行し、生成済みのテストケースで自動採点する機能。本サービスの中核で、**「LLM の出力を信用せず、サンドボックスで動作保証する」設計思想**が最も色濃く出る部分。

## ビジネスルール

- **セキュリティ最優先**：ユーザーが書いたコードは攻撃コードである可能性を前提に扱う
  - ネットワーク遮断（`--network none`）
  - ファイルシステム書き込み制限（`/tmp` のみ）
  - CPU・メモリ制限（cgroups）
  - 非 root 実行
  - 実行時間 5 秒上限
- **使い捨てコンテナ**：前回実行の影響が原理的に残らない（→ [ADR 0009](../../adr/0009-disposable-sandbox-container.md)）
- **隔離レイヤの段階的進化**：Docker → gVisor → Firecracker（→ [2-foundation/05-runtime-stack.md](../2-foundation/05-runtime-stack.md#サンドボックス)）
- **採点失敗ケースは要因別に整形**：「テスト不合格」「構文エラー」「実行時例外」「OOM」「タイムアウト」を区別
- **trace_id の連結**：NestJS リクエスト → ジョブ → ワーカー処理 → 採点結果が単一トレースで追える（→ [ADR 0010](../../adr/0010-w3c-trace-context-in-job-payload.md)）

## スコープ外（このスプリントでは扱わない）

- 解答コードの保存・SNS 共有
- LLM ヒント機能（[F-07](../5-roadmap/01-roadmap.md#f-07-llm-ヒント機能)）
- 複数言語対応（MVP は TypeScript のみ）
- 部分点（テストケース重み付け）：MVP は通過数 / 全数の単純集計
- カスタムジャッジ（競技プログラミング風の特殊判定）
- gVisor / Firecracker への切り替え（R3 / R9）

## データモデル

詳細は [3-cross-cutting/01-data-model.md](../3-cross-cutting/01-data-model.md) を参照。

- `submissions`：解答送信ごとに作成（`id`, `user_id`, `problem_id`, `code`, `status`, `result?`, `score?`, `created_at`, `graded_at?`）
- `jobs`：採点ジョブのキューイング（`type='grade'`, `payload: { traceContext, submissionId, problemId, code, language, timeoutMs }`、→ [3-cross-cutting/01-data-model.md: ジョブペイロード](../3-cross-cutting/01-data-model.md#ジョブペイロード共通フィールドtracecontext)、[ADR 0010](../../adr/0010-w3c-trace-context-in-job-payload.md)）

## 画面

### 採点結果表示（対象：認証ユーザー）

採点結果は専用画面ではなく、[F-03: 問題詳細・解答画面](./F-03-problem-display-and-answer.md) 内の `<GradingResult />` コンポーネントとして表示される。

- **概要**：解答送信後、ポーリングで採点結果を取得し、結果に応じた表示
- **主要コンポーネント**：
  - `<GradingPendingIndicator />`（採点中スピナー）
  - `<GradingResultPass />`（正解：通過数表示・所要時間・お祝いメッセージ）
  - `<GradingResultFail />`（失敗：失敗ケース・期待値・実際の出力・差分）
  - `<GradingResultError />`（実行時エラー / タイムアウト：スタックトレース整形）
- **使用 API**：
  - `POST /submissions` — 解答送信（202 + submissionId）
  - `GET /submissions/:id` — ポーリングで結果取得
- **主要インタラクション**：
  - `status='pending'` / `'running'` の間ポーリング継続
  - `status='graded'` で停止し、結果を表示
  - `status='failed'` で再試行ボタン提示

## ユーザーフロー

### 採点フロー（対象：認証ユーザー）

採点ジョブの完全な経路（ブラウザ → NestJS → Postgres → Go ワーカー → サンドボックス → 結果取得）は **[02-architecture.md: 1 ジョブが流れる完全な経路](../2-foundation/02-architecture.md#1-ジョブが流れる完全な経路)** を参照（Mermaid シーケンス図 + 4 段階の設計ポイント表）。

機能側の補足：

- **trace_id 連結**：`payload.traceContext` から OTel Context を復元し、Go ワーカーのスパンを NestJS 側の親スパンに `SpanLink` で接続（→ [ADR 0010](../../adr/0010-w3c-trace-context-in-job-payload.md)）
- **ポーリング側の挙動**：TanStack Query で 1〜2 秒間隔の指数バックオフ、`status === 'graded' | 'failed'` で停止
- **冪等性**：`UPDATE jobs SET state='done' WHERE id=<jobId>` は ID 指定で安全。重複処理が起きても結果が壊れない

### 失敗系のフロー

- **テスト不合格**：`status='graded'`, `score < totalCount`, `result.testResults` に失敗ケース内訳
- **タイムアウト**：ワーカーが `ContainerWait` のタイムアウト発火 → ContainerKill → `result.failure_type='timeout_killed'`
- **OOM**：Docker が OOM Kill → `result.failure_type='oom_killed'`
- **構文エラー**：トランスパイル失敗 → `result.failure_type='syntax_error'`、stderr 整形して返却
- **再試行可能エラー**：DB 接続一時失敗等 → リトライ（最大 3 回、指数バックオフ）→ 全失敗で `state='dead'`（DLQ）

## API

| メソッド | パス | 用途 | 認証 |
|---|---|---|---|
| POST | `/submissions` | 解答送信 → 採点ジョブ投入 | 必須 |
| GET | `/submissions/:id` | 解答 + 採点結果取得（ポーリング用） | 必須 |
| GET | `/submissions` | 自分の解答履歴一覧 | 必須 |

機械可読の最新仕様は OpenAPI（`/api/docs/openapi.json`）が SSoT。

### リクエスト・レスポンス例

`POST /submissions`：
```json
{
  "problemId": "<uuid>",
  "code": "export function solve(n: number) { ... }"
}
```

レスポンス（202）：
```json
{
  "submissionId": "<uuid>",
  "status": "pending"
}
```

`GET /submissions/:id`（採点完了後）：
```json
{
  "id": "<uuid>",
  "problemId": "<uuid>",
  "status": "graded",
  "score": 5,
  "totalCount": 5,
  "result": {
    "passed": true,
    "durationMs": 1340,
    "testResults": [
      { "name": "case1", "passed": true, "durationMs": 120 }
    ]
  },
  "gradedAt": "2026-04-25T10:00:00Z"
}
```

## バリデーション

| フィールド | ルール | エラーメッセージ |
|---|---|---|
| `problemId` | 必須、UUID、存在する問題 | 問題が存在しません |
| `code` | 必須、64KB 以下 | コードのサイズが上限を超えています |

サーバ側の所有権チェック：

- `GET /submissions/:id`：自分の `submissions.user_id` と一致する場合のみ閲覧可（→ [backend.md](../../../.claude/rules/backend.md)）

## 関連

- **関連機能**：
  - [F-02: 問題生成リクエスト](./F-02-problem-generation.md)（生成時のサンドボックス検証は同じ仕組み）
  - [F-03: 問題表示・解答](./F-03-problem-display-and-answer.md)（解答送信のエントリポイント）
  - [F-05: 学習履歴](./F-05-learning-history.md)（採点結果が履歴に集約される）
- **関連 ADR**：
  - [ADR 0004: Postgres ジョブキュー](../../adr/0004-postgres-as-job-queue.md)
  - [ADR 0016: Go で採点ワーカーを実装](../../adr/0016-go-for-grading-worker.md)
  - [ADR 0009: 使い捨てサンドボックスコンテナ](../../adr/0009-disposable-sandbox-container.md)
  - [ADR 0010: W3C Trace Context をジョブペイロードに埋め込む](../../adr/0010-w3c-trace-context-in-job-payload.md)
- **横断要件**：
  - アーキテクチャ（採点フロー）：[2-foundation/02-architecture.md](../2-foundation/02-architecture.md#1-ジョブが流れる完全な経路)
  - 非機能（性能・セキュリティ）：[2-foundation/01-non-functional.md](../2-foundation/01-non-functional.md)
  - 観測性：[2-foundation/04-observability.md](../2-foundation/04-observability.md)
- **実装ルール**：[backend.md](../../../.claude/rules/backend.md)、[worker.md](../../../.claude/rules/worker.md)

## ステータス

- [ ] 要件定義完了
- [ ] バックエンド実装完了（GradingModule / SubmissionsModule）
- [ ] ワーカー実装完了（Go：ジョブ取得・サンドボックス起動・結果書き戻し）
- [ ] サンドボックス実装完了（Docker + 制限フラグ、R3 で gVisor 切替）
- [ ] フロントエンド実装完了（採点結果表示コンポーネント）
- [ ] ユニットテスト完了（GradingService / SandboxRunner のモックテスト）
- [ ] E2E テスト完了（解答送信 → 採点完了 → 結果表示の主要フロー）
- [ ] 受け入れ条件すべて満たす
- [ ] PR マージ済み

## スプリント情報

- **対象スプリント**：Sprint 3（MVP コア機能 - 採点）
- **ストーリーポイント**：未確定
- **担当**：神保
- **着手日 / 完了日**：未着手 / 未完了
