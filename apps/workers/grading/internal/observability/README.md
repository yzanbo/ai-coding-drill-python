# internal/observability

## とは何か

「何が起きたかを後から追える」ようにするための初期化コードを 1 つの package にまとめた置き場。**ログ / トレース / メトリクス**の 3 つを起動時に同時にセットアップする（[ADR 0041](../../../../docs/adr/0041-observability-stack-grafana-and-sentry.md)）。

## なぜ log / otel を分けず lump（1 package）か

- slog の handler を「trace_id を自動付与する」拡張にするには **OTel API を import する**必要があり、`log/` と `otel/` を分けると `log → otel` 依存が発生して境界が曖昧になる
- 1 package で `observability.Init(ctx, cfg) (logger, shutdown, error)` の **1 関数**にまとまるので main.go が簡潔
- 将来 Prometheus exporter を足す時も同じ package に追加でき、観測 stack が 1 箇所に集まる

## 役割

- `slog`（標準ライブラリ）の JSON handler を初期化し、`slog.SetDefault` でグローバル設定
- OpenTelemetry SDK の TracerProvider / MeterProvider をセットアップし、OTLP exporter 経由で外部（Tempo / Prometheus）へ送る（実装は R4）
- trace_id / span_id を log に自動付与するカスタム handler を提供（context から `trace.SpanContextFromContext(ctx)` で抽出）
- ジョブペイロードの `trace_context` カラムから W3C Trace Context を復元するヘルパ（[ADR 0010](../../../../docs/adr/0010-w3c-trace-context-in-job-payload.md)）
- shutdown 関数：プロセス終了時に buffered span を flush する

## やってはいけないこと

- 業務 package が `internal/observability/` を import する：観測は **context 経由で透過利用**する（`slog.InfoContext(ctx, ...)` / `otel.Tracer("name").Start(ctx, ...)` を直接使う）。`observability` package は main.go からしか参照されない（[worker-layers.md §C 補足](../../../../docs/requirements/5-roadmap/r0-setup/worker-layers.md)）
- ログに**機密値**（API キー / 個人情報）をそのまま入れる：マスキング層は R4 で Sentry / Loki 経路で整備（[ADR 0041](../../../../docs/adr/0041-observability-stack-grafana-and-sentry.md)）
- `panic` をログだけして握りつぶす：パニックは `recover()` で吸収しジョブを `failed` 状態に遷移、Worker 本体は継続稼働（[ADR 0019](../../../../docs/adr/0019-go-code-quality.md)）

## 関連

- 規約 SSoT：[.claude/rules/worker.md「observability」セクション](../../../../.claude/rules/worker.md)
- 観測スタック：[ADR 0041](../../../../docs/adr/0041-observability-stack-grafana-and-sentry.md)（Grafana + Sentry）
- trace 連携：[ADR 0010](../../../../docs/adr/0010-w3c-trace-context-in-job-payload.md)（W3C Trace Context payload）
