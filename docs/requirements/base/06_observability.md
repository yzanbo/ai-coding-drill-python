# 06. 観測性・運用

## ログ

### 構造化ログ
- JSON 形式
- 必須フィールド：`timestamp`, `level`, `trace_id`, `span_id`, `service`, `event`
- LLM 呼び出し時の追加フィールド：`model`, `prompt_version`, `input_tokens`, `output_tokens`, `latency_ms`, `cost_usd`

### 保存先
- ローカル：標準出力
- 本番：Loki（または CloudWatch Logs）

## トレース

### OpenTelemetry
- 全リクエストに trace_id を付与
- 主要スパン：
  - API ハンドラ
  - DB クエリ
  - ジョブエンキュー
  - ワーカー処理（LLM 呼び出し、サンドボックス実行を子スパンに）
- エクスポート先：Tempo または Jaeger

### 可視化例
```
[POST /problems/generate] 1200ms
  ├─ [cache.get] 5ms
  ├─ [llm.generate (haiku)] 800ms
  ├─ [sandbox.run (reference)] 250ms
  └─ [llm.judge (sonnet)] 120ms
```

## メトリクス

### Prometheus + Grafana ダッシュボード
- **生成パイプライン**
  - 生成リクエスト数（rate）
  - 生成成功率
  - 再生成回数分布
  - Judge スコア分布
- **コスト**
  - LLM コスト（モデル別、時間別）
  - キャッシュヒット率
- **サンドボックス**
  - 実行時間分布
  - タイムアウト発生率
  - メモリ使用量
- **API**
  - リクエスト数、P50/P95/P99 レイテンシ、エラー率

## エラー追跡
- Sentry でフロント・バック両方の例外を集約
- LLM のスキーマ違反、サンドボックスのクラッシュを通知

## アラート（最低限）
- LLM コストが日次予算を超過
- 生成成功率が閾値以下（例：< 70%）
- サンドボックスのエラー率急増

## 運用 Runbook（簡易）
- サンドボックスが重い時の調査手順
- LLM API 障害時のフォールバック手順
- コスト超過時の緊急停止手順

これらを `docs/runbook/` に追加予定。
