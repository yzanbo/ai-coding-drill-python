# 0041. 観測性スタックに Grafana 系（Loki / Tempo / Prometheus / Grafana）+ Sentry を採用

- **Status**: Accepted
- **Date**: 2026-05-10
- **Decision-makers**: 神保 陽平

## Context（背景・課題）

本プロジェクトは LLM 生成 + サンドボックス採点 + 非同期ジョブ処理という「外部 I/O 遅延・失敗が多発する系」であり、観測性の三本柱（ログ・メトリクス・トレース）を**実装着手時点（R0〜R1）から**揃える必要がある（→ [04-observability.md](../requirements/2-foundation/04-observability.md)）。

特に [ADR 0010](./0010-w3c-trace-context-in-job-payload.md) で W3C Trace Context をジョブペイロードに埋め込む方針を決めた以上、**それを受け取り可視化するトレースバックエンド**の選定が R1 着手前に必要となる。同時に、ログ（Loki / CloudWatch / Datadog 等）とメトリクス（Prometheus / CloudWatch Metrics 等）も並行して選定したほうが、**3 系統が分離して相互リンクできない**事態を構造的に防げる。

選定の制約：

- **コスト**：プロジェクト全体の月額目標 $30 以内（→ [01-non-functional.md: コスト](../requirements/2-foundation/01-non-functional.md#コスト)）。観測性で月数十ドル使う SaaS は採用不可
- **AWS 単独方針**（→ [ADR 0002](./0002-aws-single-cloud.md)）との親和性：ストレージは S3 等の AWS マネージドサービスを活用したい
- **OSS / ベンダ非依存**：[ADR 0007](./0007-llm-provider-abstraction.md) と同じ哲学。1 ベンダロックインを避ける
- **OTel / W3C 標準との整合**：[ADR 0010](./0010-w3c-trace-context-in-job-payload.md) で W3C Trace Context を採用済み。OTLP を素直に受信できることが必須

## Decision（決定内容）

観測性スタックとして以下を採用する：

| 観測対象 | 採用ツール | 役割 |
|---|---|---|
| **ログ** | **Grafana Loki** | 構造化ログの集約・検索 |
| **トレース** | **Grafana Tempo** | 分散トレース（[ADR 0010](./0010-w3c-trace-context-in-job-payload.md) の W3C Trace Context 受信先） |
| **メトリクス** | **Prometheus** | 数値メトリクスの収集・保存・クエリ |
| **可視化 UI** | **Grafana** | 上記 3 系統を 1 画面で統合表示 |
| **エラー追跡** | **Sentry**（無料枠） | フロント / バックのエラー集約・スタックトレース・リリーストラッキング |

ホスティング形態は段階的に進める：

- **R0〜R5**：**Grafana Cloud 無料枠**（Logs 50GB/月・Traces 50GB/月・Metrics 10k series 等）で運用。インフラ運用コストゼロ
- **R6 以降（必要時）**：自前 Grafana + Loki + Tempo + Prometheus を AWS（EC2 / ECS）に構築、ストレージは **S3** を直接使う構成に移行

OTLP Collector（OpenTelemetry Collector）をアプリと Grafana Cloud の間に挟み、出力先設定を Collector に集約する。

→ 実運用詳細（必須フィールド・PII マスキング・アラート対象・サンプリング率等）の SSoT は [04-observability.md](../requirements/2-foundation/04-observability.md) を参照（運用ルール型 ADR、→ [`.claude/rules/docs-rules.md` §2](../../.claude/rules/docs-rules.md#2-adr-の-decision-は-2-通り型を見極めて書き分ける)）。本 ADR は採用根拠（§Why）と代替案（§Alternatives Considered）を扱う。

## Why（採用理由）

### Grafana スタック（Loki / Tempo / Prometheus / Grafana）

1. **3 系統 1 画面統合 = 障害時の追跡導線が短い**
   - Grafana の Explore / Dashboard 上で **trace_id をクリック → 関連ログに飛ぶ / メトリクスのスパイク → 該当時間帯のログを開く** が標準機能
   - Jaeger（トレース単独）や CloudWatch（AWS ロックイン）では達成しづらい
2. **OSS かつ OTLP ネイティブ**
   - Tempo / Loki / Prometheus はすべて OTLP を直接受信可能
   - [ADR 0010](./0010-w3c-trace-context-in-job-payload.md) の W3C Trace Context をそのまま受け取れる
3. **コストが構造的に安い**
   - Grafana Cloud 無料枠で R5 までほぼ運用可能
   - 自前ホスティングに移行する場合も、Tempo / Loki は **S3 等のオブジェクトストレージにスパン・ログを直接保存**できるため、Cassandra / Elasticsearch を伴うバックエンド（Jaeger 標準構成等）より遥かに安価
4. **AWS 親和性**
   - S3 をストレージにそのまま使える（[ADR 0002](./0002-aws-single-cloud.md) AWS 単独方針と整合）
5. **2025〜2026 年時点でのデファクト性**
   - Grafana スタックは OSS 観測性の事実上の標準となっており、採用事例・公式ドキュメント・Helm Chart 等のエコシステムが厚い
   - ポートフォリオ価値（採用面接時の説明力）も高い

### Sentry（エラー追跡）

1. **エラー追跡は Loki のログ集約とは別物**
   - Sentry はスタックトレースの de-duplication / リリーストラッキング / source map 解決 / ユーザー影響範囲集計 が標準機能
   - Loki でログを grep するだけでは到達できない情報粒度
2. **無料枠で十分**（5k errors/month、本プロジェクトのトラフィック規模では超過しない見込み）
3. **OTel Trace との相互リンク**
   - Sentry の event から `trace_id` 経由で Tempo の該当トレースに飛べる（→ [04-observability.md: 観測対象の相互リンク](../requirements/2-foundation/04-observability.md#観測対象の相互リンク)）

## Alternatives Considered（検討した代替案）

### トレースバックエンド

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| **Grafana Tempo** | OSS、Grafana 統合、S3 保存 | （採用） |
| Jaeger | OSS、CNCF 卒業、Uber 発、独立 UI | トレース UI が独立しており、ログ / メトリクスとの相互リンクが手作業。ストレージに Cassandra / Elasticsearch が前提でコスト・運用負荷が高い |
| AWS X-Ray | AWS マネージド | AWS 単独方針には沿うが、X-Ray 独自の伝播フォーマット（SDK 自動切替で W3C 互換は可能）を使うとベンダロックインに傾く。Grafana 系と相互リンクする手間が増える |
| Datadog APM | SaaS、超高機能 | 有償（最低 $15/host/month〜）でコスト目標を超過。個人ポートフォリオでは過剰 |
| New Relic | SaaS、無料枠 100GB/月 | 無料枠は魅力だが 1 ベンダ依存度が高くなり、ログ / メトリクスも New Relic で囲い込まれる構造になりやすい |
| Honeycomb | SaaS、高性能クエリ（BubbleUp 等） | 有償。観測性の高度な分析が主目的でない本プロジェクトには過剰 |

### ログ・メトリクス・UI（スタック全体）

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| **Grafana 系（Loki / Tempo / Prometheus / Grafana）** | OSS オールインワン | （採用） |
| AWS CloudWatch Logs / Metrics + X-Ray | AWS マネージド | AWS 単独方針には沿うが、3 系統の相互リンクが弱い。CloudWatch Logs Insights のクエリ言語が Loki LogQL より学習価値で劣る。コストも従量課金で読みづらい |
| ELK Stack（Elasticsearch + Logstash + Kibana） | 老舗 OSS | Elasticsearch の運用コスト・JVM チューニング負荷が高く、個人プロジェクト規模に合わない |
| SigNoz | OSS、ログ・メトリクス・トレース統合 | オールインワンで魅力的だが、Grafana 系より採用事例・エコシステムが薄い。将来差し替えのリスク |
| Datadog（フル SaaS） | ログ・メトリクス・APM・RUM 一体 | 有償でコスト目標を超過 |

### エラー追跡

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| **Sentry** | SaaS、無料枠 | （採用） |
| Loki のログ集約のみ | 既存スタックで完結 | スタックトレース de-duplication / リリーストラッキング等の機能を自前実装することになり、車輪の再発明 |
| Rollbar / Bugsnag | 競合 SaaS | Sentry と機能差は小さいが、OSS / 採用事例 / OTel 統合で Sentry が優勢 |

## Consequences（結果・トレードオフ）

### 得られるもの
- **3 系統 1 画面統合**：Grafana 上で trace_id 起点にログ・メトリクスへ飛べるため、障害解析の導線が短い
- **R0〜R5 はインフラ運用コストゼロ**（Grafana Cloud 無料枠）
- **将来の自前ホスティング移行が可能**（OSS なので Grafana Cloud 終了・値上げ時のロックイン無し）
- **W3C Trace Context（[ADR 0010](./0010-w3c-trace-context-in-job-payload.md)）をそのまま受信**できる
- **Sentry の無料枠でエラー追跡が即座に立ち上がる**

### 失うもの・受容するリスク
- **ベンダ非依存だが Grafana スタック「内」では一蓮托生**：Loki と Tempo と Prometheus は Grafana UI を前提に統合される。Grafana Labs 全体の方針転換時には影響を受ける（とはいえ全て OSS なのでフォーク継続可能）
- **Grafana Cloud 無料枠を超過した場合の移行作業**：自前ホスティングへの切替は数日〜数週間の作業を要する（R6 以降想定）
- **Sentry 無料枠超過リスク**：5k errors/month を超えるとプラン変更が必要。トラフィック増加時の監視対象とする

### 将来の見直しトリガー
- Grafana Cloud 無料枠を超過し、月額コストが目標予算を圧迫した場合（自前ホスティングへ移行 or バックエンド見直し）
- Sentry 無料枠（5k errors/month）を超過した場合（プラン変更 or Loki ベースの自前エラー追跡へ）
- AWS 側の観測性プロダクトが大幅進化（X-Ray が OTel ネイティブ化 + ログ / メトリクス相互リンク強化等）し、AWS 完結のほうが管理コストが下がる場合
- 採用事例の急減・コミュニティ衰退（Grafana 系が事実上のデファクトでなくなった場合）

## References

- [04-observability.md](../requirements/2-foundation/04-observability.md) — 観測性の設計詳細（必須フィールド・PII マスキング・アラート対象・サンプリング率等の SSoT）
- [05-runtime-stack.md: 観測性](../requirements/2-foundation/05-runtime-stack.md#観測性) — 採用ツール一覧（runtime-stack 側 SSoT）
- [ADR 0002: AWS 単独クラウド](./0002-aws-single-cloud.md)
- [ADR 0007: LLM プロバイダ抽象化戦略](./0007-llm-provider-abstraction.md) — 「ベンダ非依存」哲学
- [ADR 0010: W3C Trace Context をジョブペイロードに埋め込む](./0010-w3c-trace-context-in-job-payload.md) — トレース伝播プロトコル（本 ADR が受信先を確定）
- [Grafana Tempo 公式](https://grafana.com/oss/tempo/)
- [Grafana Loki 公式](https://grafana.com/oss/loki/)
- [Sentry 公式](https://sentry.io/)
- [OpenTelemetry Collector](https://opentelemetry.io/docs/collector/)
