# 04. 観測性・運用

> **このドキュメントの守備範囲**：観測性（ログ・トレース・メトリクス・アラート）の設計、必須フィールド、データ保護方針、運用 Runbook。R1 〜 R4 を射程に含める。
> **採用するツール（Loki / Tempo / Prometheus / Grafana / Sentry 等）と選定理由**は [05-runtime-stack.md: 観測性](./05-runtime-stack.md#観測性) を参照。

## ログ

### 構造化ログ

- **形式**：JSON 形式、1 行 1 イベント
- **必須フィールド**（R1 から実装。**後追加だと過去ログを集計できない**ため最初から固める）：
  - `timestamp`（RFC 3339 / ISO 8601、UTC）
  - `severity_text`（`DEBUG` / `INFO` / `WARN` / `ERROR` / `FATAL`）
  - `severity_number`（OTel semantic conventions 準拠、1〜24）
  - `body`（人間可読のメッセージ本体）
  - `service.name`（`api` / `grading-worker` / `web`）
  - `service.version`（git commit SHA または semver）
  - `deployment.environment`（`local` / `staging` / `production`）
  - `host.name`（ホスト/コンテナ識別子）
  - `process.pid`
  - `trace_id` / `span_id`（OTel コンテキストから自動付与）
  - `request_id`（HTTP リクエスト境界の識別、`trace_id` とは別運用：トレース未連携経路でも追跡可能）
  - `user_id`（認証済みリクエストのみ。**未認証時はキー自体を出さない**）
- **LLM 呼び出し時の追加フィールド**（R1 から記録、後追加だと履歴クエリ不可）：
  - `llm.provider`（`anthropic` / `google` / `openai` / `openrouter` 等。[ADR 0011](../../adr/0011-llm-provider-abstraction.md) の抽象化に対応）
  - `llm.model`（モデル名、例：`claude-3-5-haiku`）
  - `llm.prompt_version`（YAML プロンプトのバージョン）
  - `llm.prompt_hash`（プロンプト本文のハッシュ、重複検出用）
  - `llm.input_tokens` / `llm.output_tokens`
  - `llm.cache_hit`（boolean、Redis キャッシュヒット可視化）
  - `llm.attempt_number`（再生成回数、1 始まり）
  - `llm.finish_reason`（`stop` / `length` / `tool_use` / `content_filter` 等）
  - `llm.latency_ms`（リクエスト送信〜レスポンス受信）
  - `llm.cost_usd`（モデル単価とトークン数から計算）

### ログレベルの方針

| 環境 | 出力レベル | 備考 |
|---|---|---|
| `local` | `DEBUG` 以上 | 開発時の詳細調査用 |
| `staging` | `INFO` 以上 | 本番準拠だが DEBUG 切替可能（環境変数 `LOG_LEVEL`） |
| `production` | `INFO` 以上 | DEBUG は特定 `trace_id` のサンプリングのみ |

LLM 呼び出しは**コスト・品質追跡の中核**のため `INFO` で全件記録（サンプリングしない）。

### 保存先と保持期間

- **ローカル**：標準出力（12-Factor App 原則）
- **本番**：ログ集約基盤に転送（採用先は [05-runtime-stack: 観測性](./05-runtime-stack.md#観測性)）
- **保持期間**（初期値、運用データを見て四半期に 1 回見直す）：
  - ホット（即時検索可）：7 日
  - コールド（圧縮・低頻度アクセス）：30 日
  - LLM コスト関連ログのみ：90 日（月次集計に使用しうるため）

### データ保護（PII / 秘密情報のマスキング）

ログ・トレース・エラー追跡サービスへ送信する前に必ずマスキング・除外する。**R1 から共通 redact ミドルウェアを導入**（後から PII を漏らした履歴を消す方が大変）：

| 種別 | 方針 |
|---|---|
| **ユーザー解答コード（`submissions.code`）** | **ログ・Sentry に送らない**。デバッグが必要な場合のみ `code_hash`（SHA-256）を記録 |
| **メールアドレス・氏名** | `user_id`（UUID）に置き換え、生値は出さない |
| **OAuth トークン・セッション ID** | リクエストヘッダから自動除去（フレームワークの redact 機能を使用） |
| **環境変数・API キー** | スタックトレースから自動除去（Sentry の `beforeSend` フックで `process.env` 由来文字列を redact） |
| **LLM プロンプトに混入しうる PII** | プロンプト本文を直接ログに含めない（`prompt_hash` のみ。本文は別途プロンプトストアに保存） |
| **疑わしい攻撃文字列** | プロンプトインジェクション疑いの**入力文字列は記録**（攻撃調査用、別の `security` ロガー） |

実装：NestJS / Go それぞれで共通の redact ミドルウェアを `observability/` モジュール配下に置く。

---

## トレース

### OpenTelemetry

- **全リクエストに `trace_id` を付与**
- **全リクエスト記録**（MVP 規模ではサンプリングしない、コスト超過時に再評価）
- 採用 SDK・エクスポート先は [05-runtime-stack: 観測性](./05-runtime-stack.md#観測性) を参照

### 主要スパン（インストルメンテーション対象）

- **API ハンドラ**（`http.server`）
- **DB クエリ**（`db.client.operations`、Drizzle 自動計装）
- **トランザクション**（`db.transaction` を親、内部 INSERT/UPDATE を子）
- **キャッシュ操作**（`cache.get` / `cache.set`、Redis）
- **JSON Schema バリデーション**（LLM 出力パース時、Zod）
- **HTTP クライアント**（外部 LLM API 呼び出し自体、`http.client`）
- **ジョブエンキュー**（`job.enqueue`、`INSERT INTO jobs` + `NOTIFY`）
- **ワーカー処理**（`job.process`、Go 側のジョブ取得から完了まで）
  - 子スパン：`llm.generate`、`llm.judge`、`sandbox.run`、`sandbox.create`、`sandbox.cleanup`
- **OAuth フロー**（`auth.github.callback`）

### プロセス境界をまたぐトレース連携（R1 で必須）

NestJS（Producer）→ Postgres `jobs` → Go ワーカー（Consumer）はプロセスが分かれるため、**OTel Context をジョブペイロードに埋め込んで伝播させる**。これがないとユーザーリクエストとワーカー処理が別トレースに分断される。**ペイロードスキーマは R1 で確定するため、この方針も R1 で固める必要がある**。

→ 採用方式・代替案・トレードオフは [ADR 0017: W3C Trace Context をジョブペイロードに埋め込む](../../adr/0017-w3c-trace-context-in-job-payload.md) を参照。

#### 実装方針

1. NestJS でジョブ INSERT 時、現在の OTel Context から **W3C Trace Context** を取り出して `payload.traceContext` に格納
2. Go ワーカーがジョブ取得時に `payload.traceContext` から OTel Context を復元
3. ワーカー側の `job.process` スパンを **NestJS 側の親スパンにリンク**（`SpanLink` または `parent` として接続）

#### ペイロードへの埋め込み

```json
{
  "traceContext": {
    "traceparent": "00-<trace_id>-<span_id>-<flags>",
    "tracestate": "..."
  },
  "submissionId": "...",
  "...": "..."
}
```

→ ジョブペイロード JSON Schema にこのフィールドを必須として定義（[01-data-model.md: ジョブペイロードのスキーマ](../3-cross-cutting/01-data-model.md#ジョブペイロード共通フィールドtracecontext)）。

### 可視化例

```
[POST /problems/generate] 1200ms                       ← NestJS リクエスト
  ├─ [auth.session.verify] 3ms
  ├─ [cache.get] 5ms
  ├─ [llm.generate (provider=anthropic, model=...)] 800ms
  │    └─ [http.client POST api.anthropic.com] 790ms
  ├─ [validate.json_schema] 8ms
  ├─ [sandbox.run (reference)] 250ms
  └─ [llm.judge (provider=google, model=...)] 120ms

[POST /submissions] 45ms                               ← NestJS リクエスト
  ├─ [db.transaction] 30ms
  │    ├─ [db.insert submissions] 8ms
  │    ├─ [db.insert jobs] 6ms
  │    └─ [db.execute NOTIFY] 2ms
  └─ [http.response] 1ms

[job.process (id=42)] 1850ms                            ← Go ワーカー（同一 trace_id で連結）
  ├─ [job.acquire] 12ms
  ├─ [sandbox.create] 200ms
  ├─ [sandbox.run] 1500ms
  ├─ [sandbox.cleanup] 80ms
  └─ [db.update jobs (state=done)] 15ms
```

---

## メトリクス

採用基盤は [05-runtime-stack: 観測性](./05-runtime-stack.md#観測性) を参照。Prometheus 形式でラベル付与し、Grafana で可視化する想定。R4 でダッシュボード構築。

### 生成パイプライン

- 生成リクエスト数（rate、`category` / `difficulty` ラベル）
- **生成成功率**（成功 / 失敗、モデル別ラベル `llm.provider` / `llm.model`）
- **失敗理由の内訳**（`reason="test_failed" | "judge_rejected" | "schema_violation" | "timeout" | "llm_error"`）
- 再生成回数分布（ヒストグラム、最大試行回数到達率）
- Judge スコア分布（軸別、`axis="clarity" | "coverage" | "difficulty" | "educational" | "originality"`）
- **プロンプトバージョン別の成功率**（A/B テスト用、[03-llm-pipeline.md: プロンプト管理](./03-llm-pipeline.md#プロンプト管理) 参照）

### コスト

- LLM コスト（モデル別 / プロバイダ別 / 時間別）
- **生成 1 件あたりコスト**（成功確定問題のみ、効率指標）
- **ユーザー別コスト**（上位 N 名のみ、コスト爆発検知）
- キャッシュヒット率（プロンプトキャッシュ / Redis レスポンスキャッシュ別）

### サンドボックス

- **コンテナ起動時間**（`runtime="docker" | "runsc" | "firecracker"` ラベル付き、[ADR 0008](../../adr/0008-disposable-sandbox-container.md) のベンチマーク継続観測）
- 実行時間分布（ヒストグラム）
- タイムアウト発生率
- メモリ使用量分布
- **失敗種別**（`failure_type="test_failed" | "syntax_error" | "runtime_exception" | "oom_killed" | "timeout_killed"`）
- **コンテナリーク数**（残存している採点コンテナ数。`ContainerRemove` 失敗の検知）

### ジョブキュー（このプロジェクトの中核）

[ADR 0001](../../adr/0001-postgres-as-job-queue.md) と [02-architecture.md: ジョブキュー](./02-architecture.md#ジョブキューpostgres-select-for-update-skip-locked) の運用作法を観測する：

- **キュー深さ**：`SELECT count(*) FROM jobs WHERE state='queued'`（queue 別ラベル）
- **エンキュー → 取得待ち時間**（`run_at` から `locked_at` まで、p50/p95/p99）
- **取得 → 完了時間**（`locked_at` から `state='done'` まで）
- **リトライ回数分布**（`attempts` の値分布）
- **DLQ サイズ**（`state='dead'` の件数）
- **スタックジョブ数**（`locked_at < now() - interval '5 min' AND state='running'` の件数。`reaper` の動作確認）
- **NOTIFY 取りこぼし率**（NOTIFY 受信数とポーリングで初検知した件数の比率）
- **ワーカー稼働数 / 並列実行数**（`locked_by` の DISTINCT 数）

### データベース

- 接続プール使用率（NestJS / Go ワーカー側それぞれ）
- スロークエリ数（閾値：500ms）
- トランザクション数 / 秒
- LISTEN/NOTIFY イベント発火数

### API

- リクエスト数（**エンドポイント別ラベル** `route="/problems/generate"` 等）
- レイテンシ（**エンドポイント別** P50 / P95 / P99）
- HTTP ステータスコード分布（`status_class="2xx" | "4xx" | "5xx"` および詳細コード）
- **レート制限ヒット数**（429 発生数、エンドポイント別。[01-non-functional.md: セキュリティ](./01-non-functional.md#セキュリティ最重要) の Sliding Log 動作確認）
- エラー率（`5xx` の比率）

### ヘルスチェック

[02-api-conventions.md: ヘルスチェック・運用](../3-cross-cutting/02-api-conventions.md#ヘルスチェック運用エンドポイント) のエンドポイントを観測：

- `/healthz`（Liveness）失敗率
- `/readyz`（Readiness）失敗率と内訳（DB 接続失敗 / Redis 接続失敗）
- 連続失敗回数（再起動判断材料）

### ビジネス指標（R4 以降で追加検討）

- DAU / MAU
- 解答送信数 / 日
- 1 ユーザーあたり解答数

---

## エラー追跡

- フロント・バック両方の例外を集約サービスへ送信
- LLM のスキーマ違反、サンドボックスのクラッシュを通知
- **エラーから `trace_id` を介してトレースバックエンドへジャンプ**（Sentry → Tempo の相互リンク）
- **エラーのグルーピング・重複排除**は採用サービスの標準機能を活用
- **PII / 秘密情報のマスキングは「ログ § データ保護」と同じ方針を適用**（`beforeSend` フック）
- **ソースマップ**：フロント JS のスタックトレース解析のためビルド時にアップロード
- 採用サービスは [05-runtime-stack: 観測性](./05-runtime-stack.md#観測性) を参照

---

## アラート

| 事象 | 閾値（初期値） | 通知先 |
|---|---|---|
| LLM コストが日次予算を超過 | `> $30/day`（[01-non-functional.md](./01-non-functional.md#コスト) の上限） | メール |
| LLM コスト時間あたり急増 | 直近 1 時間が直近 24 時間平均の 5 倍超 | メール |
| 生成成功率が閾値以下 | 直近 1 時間で `< 70%` | メール |
| サンドボックスのエラー率急増 | 直近 1 時間で `> 30%` | メール |
| **API 5xx 急増** | 直近 5 分で `> 5%` | メール |
| **キュー深さ閾値超過** | `queued > 100`（ワーカー追従不可の兆候） | メール |
| **DLQ 増加** | `state='dead'` の件数が直近 1 時間で 5 件以上増加 | メール |
| **スタックジョブ蓄積** | `state='running' AND locked_at < now() - 5 min` が 3 件以上 | メール |
| **DB / Redis 接続エラー** | 連続 3 回失敗 | メール |
| **`/readyz` 失敗** | 連続 3 回失敗 | メール |

### 通知先方針（MVP）

- すべて**運用者個人のメール**へ送信（ポートフォリオ規模、24/7 オンコール体制は不要）
- Slack / PagerDuty 連携は R4 以降で必要になったら追加
- アラートが発火したら原則 [docs/runbook/](#運用-runbook) を参照して対応

### 閾値の見直し

- 初期値は本ドキュメントの値で運用
- 月次で誤検知率を確認し、閾値を調整
- 大規模化したら **SLO ベースのバーンレートアラート**（[Google SRE Book](https://sre.google/sre-book/alerting-on-slos/) 方式）への移行を検討

---

## 運用 Runbook

`docs/runbook/` に以下の手順書を配置する（R4 で順次整備）：

- サンドボックスが重い時の調査手順
- LLM API 障害時のフォールバック手順
- コスト超過時の緊急停止手順
- **ジョブキュー詰まり時の対応**（DLQ クリア・スタックジョブの手動回収）
- **DB / Redis 接続エラー時の対応**
- **GitHub OAuth ダウン時のフォールバック**
- **疑わしいユーザーコード検知時のセキュリティ対応**
- **ストレージ容量逼迫時の対応**

各 Runbook は **症状 → 確認手順 → 対処手順 → エスカレーション先 → 関連リンク**の順で記述する。
