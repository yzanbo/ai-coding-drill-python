# 0010. W3C Trace Context をジョブペイロードに埋め込んでプロセス境界トレース連携を実現

- **Status**: Accepted
- **Date**: 2026-05-03
- **Decision-makers**: 神保 陽平

## Context（背景・課題）

採点・問題生成のジョブ処理は、複数プロセス・複数言語にまたがって実行される：

```
ブラウザ → NestJS（TS）── Postgres jobs INSERT + NOTIFY ──→ Go ワーカー → サンドボックス
```

OpenTelemetry の自動計装は **同一プロセス内のスパン親子関係**しか自動的には伝播しないため、上記フローでは：

- NestJS のリクエスト処理（`POST /submissions`）と
- Go ワーカーの採点処理（`job.process`）

が **別々の trace_id** として記録され、Tempo / Jaeger 上で連結された 1 本のトレースとして可視化できない。これでは [04-observability.md: 可視化例](../requirements/2-foundation/04-observability.md#可視化例) の「ユーザーリクエストから採点完了までを 1 トレースで追う」が成立しない。

ジョブペイロードのスキーマは R1 で確定し、確定後は JSON Schema を SSoT として TS / Go 両言語の型を自動生成する（→ [ADR 0006](./0006-json-schema-as-single-source-of-truth.md)）。**ペイロード構造を後から変更すると、進行中ジョブのマイグレーションと両言語のコード追従が必要**になるため、R1 着手前にトレース連携の方針を決めておく必要がある。

## Decision（決定内容)

ジョブペイロードに **W3C Trace Context**（[W3C 勧告](https://www.w3.org/TR/trace-context/)）の `traceparent` / `tracestate` を埋め込み、プロセス境界をまたいで OTel Context を伝播する。

### スキーマ・伝播方式

- 全ジョブ種別の JSON Schema に `traceContext` フィールドを **必須**として定義（[01-data-model.md: ジョブペイロードのスキーマ](../requirements/3-cross-cutting/01-data-model.md#ジョブペイロード共通フィールドtracecontext)）
- NestJS（Producer）：ジョブ INSERT 時、現在の OTel Context から `traceparent` / `tracestate` をシリアライズして `payload.traceContext` に格納
- Go ワーカー（Consumer）：ジョブ取得時、`payload.traceContext` から OTel Context を復元し、ワーカー側のスパン（`jobs process`）を NestJS 側の親スパンに **SpanLink** で接続（理由は下記）
- R1 で**最初のジョブ INSERT を書く時点で実装**する（後追加だと進行中ジョブのマイグレーション必要）

### Parent-Child リンク vs SpanLink — SpanLink を採用

[OpenTelemetry Messaging Spans 仕様](https://opentelemetry.io/docs/specs/semconv/messaging/messaging-spans/) によれば、メッセージキュー / ジョブキュー越しの Trace 連携は **「Producer スパンと Consumer スパンの時間関係」** で接続方式を選び分ける：

| 状況 | 接続方式 | 理由 |
|---|---|---|
| 同期処理（Producer 完了直後に Consumer 開始） | **Parent-Child** | 親スパンがまだ open、子として参加できる |
| **非同期処理**（Producer 完了から数秒以上空く） | **SpanLink** | 親スパンが既に close 済みのため、Parent として接続できない |

このプロジェクトでの実態：

- Producer（NestJS の `POST /submissions`）：INSERT 後 ~50ms でレスポンス返却 → スパン close
- Consumer（Go ワーカーの `jobs process`）：数秒〜数十秒後に開始 → 親スパンは既に閉じている
- → **SpanLink を採用**

実装イメージ：

```typescript
// NestJS 側
const carrier: Record<string, string> = {};
otel.propagation.inject(otel.context.active(), carrier);
// carrier.traceparent / carrier.tracestate を payload.traceContext に格納
```

```go
// Go ワーカー側（ジョブ取得時）
carrier := propagation.MapCarrier{
    "traceparent": payload.TraceContext.Traceparent,
    "tracestate":  payload.TraceContext.Tracestate,
}
producerCtx := otel.GetTextMapPropagator().Extract(context.Background(), carrier)
producerSpanCtx := trace.SpanContextFromContext(producerCtx)

// SpanLink として接続
ctx, span := tracer.Start(context.Background(), "jobs process",
    trace.WithLinks(trace.Link{SpanContext: producerSpanCtx}),
    trace.WithSpanKind(trace.SpanKindConsumer),
)
```

### OpenTelemetry Messaging Semantic Conventions への準拠

スパン名・属性は [OTel Messaging Spans](https://opentelemetry.io/docs/specs/semconv/messaging/messaging-spans/) に準拠：

| スパン側 | スパン名 | 必須属性 |
|---|---|---|
| Producer（NestJS） | `jobs send` | `messaging.system="postgresql"`、`messaging.destination.name="jobs"`、`messaging.message.id="<jobId>"`、`messaging.operation="publish"` |
| Consumer（Go ワーカー） | `jobs process` | 上記同属性 + `messaging.operation="process"` |

これにより Tempo / Jaeger 上で「`jobs` キュー全体のスループット」「キューイング遅延分布」「特定 `messaging.message.id` でのジョブ追跡」が可能になる。

### Baggage の使い分け

OTel には Trace Context と並列に伝播される **`baggage`**（ビジネスメタデータ用）がある。本 ADR の伝播対象は **`traceContext`（W3C Trace Context）のみ**で、`baggage` は本 ADR の伝播対象に**含めない**：

| 種別 | 用途 | 例 | 本 ADR での扱い |
|---|---|---|---|
| **`traceContext`（W3C Trace Context）** | trace 親子関係の伝播 **専用** | `traceparent`、`tracestate` | 必須伝播 |
| **`baggage`** | ビジネスメタデータをジョブ全体・スパン全体に自動伝播 | `user.id`、`llm.provider`、`prompt.version` | 本 ADR 範囲外（必要になった時点で payload の別フィールドとして追加検討） |

両者を混同しない。`baggage` 採用時はペイロードの別フィールドに格納し、本 ADR の「将来の見直しトリガー」として再検討する。

## Why（採用理由）

1. **観測性要件（リクエスト → 採点完了の連結可視化）の構造的成立**
   - NestJS リクエストと Go ワーカー処理が別 trace_id だと「採点が遅かった原因を遡る」分析が困難
   - W3C Trace Context をペイロードに埋め込むことで、プロセス・言語境界をまたいだ単一トレース連結が成立する
2. **W3C 標準採用によるベンダ非依存性**
   - Tempo / Jaeger / Datadog / New Relic のいずれでも動作し、観測基盤の差し替え可能性を確保
   - LLM プロバイダ抽象化（→ [ADR 0007](./0007-llm-provider-abstraction.md)）と同じ「ベンダ非依存」哲学と整合
3. **OTel SDK 標準 API（propagator）が使える**
   - TS / Go 両言語で `inject` / `extract` が標準提供され、シリアライズ・デシリアライズの自前実装が不要
   - 自前フォーマットを採用するメリットがない
4. **`trace_id` カラム単独では不十分**
   - スパン ID・サンプリングフラグの伝播には `traceparent` フォーマット全体が必要で、`trace_id` だけでは親スパン情報を復元できない
   - DB スキーマに専用カラムを追加するより、ペイロード JSON の `traceContext` に集約する方がスキーマ進化に強い
5. **遅延の不可逆性（[ADR 0021](./0021-r0-tooling-discipline.md) のメタ方針と整合）**
   - ペイロード構造を後から変更すると進行中ジョブのマイグレーションと両言語のコード追従が必要
   - JSON Schema SSoT（→ [ADR 0006](./0006-json-schema-as-single-source-of-truth.md)）として R1 着手前に確定させる方が後コストを構造的に防げる
   - 「遅延すると将来コストが線形〜超線形に膨張する判断」に YAGNI を適用しないメタ方針の具体例
6. **ペイロードサイズコストが許容範囲**
   - 増加 ~80 バイト × 数百ジョブ/日では実質的に無視できる規模
   - 観測性で得る診断能力の方が遥かに価値が高い

## Alternatives Considered（検討した代替案）

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| **W3C Trace Context をペイロードに埋め込む** | 標準仕様を payload JSON に格納 | （採用） |
| OpenTelemetry Baggage をペイロードに埋め込む | OTel Baggage は Trace Context の上層、ベンダ非依存メタデータ送信にも使える | Trace 親子関係の伝播には Baggage ではなく Trace Context が標準。Baggage は補助的に併用する形が正しい |
| `jobs` テーブルに `trace_id` カラムを追加 | DB スキーマレベルで分離 | スパン ID・サンプリングフラグの伝播には不十分。`trace_id` 単独では親スパン情報を復元できず、不完全な連携しかできない |
| 伝播せず、ジョブ実行を独立トレースとする | 実装が最も簡単 | [04-observability.md: 可視化例](../requirements/2-foundation/04-observability.md#可視化例) のような連結可視化が成立せず、観測性要件を満たさない。「採点が遅かった原因を遡る」分析が困難になる |
| 自前フォーマット（独自 JSON 構造） | 完全な制御 | OTel SDK に組み込まれた `propagator` を使えず、注入・抽出処理を自前実装。標準仕様を逸脱するメリットが無い |

## Consequences（結果・トレードオフ）

### 得られるもの
- **NestJS リクエスト → Go ワーカー処理を単一 trace_id で連結可視化**できる（[04-observability.md: 可視化例](../requirements/2-foundation/04-observability.md#可視化例)）
- **トレース基盤の差し替え可能性**：W3C 標準なので Tempo / Jaeger / Datadog / New Relic 等のいずれでも動作（[ADR 0007](./0007-llm-provider-abstraction.md) と同じ「ベンダ非依存」哲学と整合）
- **OTel SDK 標準の `propagator` API（TS / Go 両方）**を使えるため、シリアライズ・デシリアライズの自前実装不要
- 採点が遅かった原因（DB / LLM / サンドボックス）を 1 トレースで遡れる

### 失うもの・受容するリスク
- **ペイロードサイズが ~80 バイト増える**（`traceparent` 55 バイト + `tracestate` 任意 + JSON 構造）。MVP のジョブ件数（数百/日）規模では無視できる
- **必須フィールド化により、ペイロード生成側の実装ミスでバリデーションエラーになりうる**：NestJS 側の Producer ヘルパー関数を一箇所に集約し、忘れ防止する
- ペイロードに常に Trace Context が含まれるため、**ログ / DB ダンプ時の PII / 機密情報の取り扱いに含める**必要がある（とはいえ Trace Context 自体は機密ではない）

### 将来の見直しトリガー
- OTel が新しい Context Propagation 仕様に移行した場合（W3C Trace Context が後継仕様に置換された場合）
- ジョブが多段階のワーカーを跨ぐようになり、Trace Context だけでは追跡情報が不十分になった場合（Baggage 併用を検討）
- ペイロードサイズ最適化が必要になるレベルのスループットに到達した場合（圧縮 / 別カラム化を検討）

## References

- [04-observability.md: トレース](../requirements/2-foundation/04-observability.md#トレース)
- [04-observability.md: プロセス境界をまたぐトレース連携](../requirements/2-foundation/04-observability.md#プロセス境界をまたぐトレース連携r1-で必須)
- [01-data-model.md: ジョブペイロードのスキーマ](../requirements/3-cross-cutting/01-data-model.md#ジョブペイロード共通フィールドtracecontext)
- [ADR 0004: Postgres をジョブキューに採用](./0004-postgres-as-job-queue.md)
- [ADR 0006: JSON Schema を Single Source of Truth に採用](./0006-json-schema-as-single-source-of-truth.md)
- [W3C Trace Context（公式仕様）](https://www.w3.org/TR/trace-context/)
- [OpenTelemetry: Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/)
- [OpenTelemetry: Messaging Spans Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/messaging/messaging-spans/)
