# 運用 Runbook（プレースホルダ）

このディレクトリは **R4（観測性）以降で整備予定**の運用手順書を配置する場所です。MVP 段階では未整備。

## 整備予定の Runbook

各 Runbook は **症状 → 確認手順 → 対処手順 → エスカレーション先 → 関連リンク** の順で記述する。

| 順次整備 | 内容 |
|---|---|
| `sandbox-slow.md` | サンドボックスが重い時の調査手順 |
| `llm-api-outage.md` | LLM API 障害時のフォールバック手順 |
| `cost-overrun.md` | コスト超過時の緊急停止手順 |
| `job-queue-stuck.md` | ジョブキュー詰まり時の対応（DLQ クリア・スタックジョブ手動回収） |
| `db-redis-connection.md` | DB / Redis 接続エラー時の対応 |
| `oauth-outage.md` | GitHub OAuth ダウン時のフォールバック |
| `suspicious-user-code.md` | 疑わしいユーザーコード検知時のセキュリティ対応 |
| `storage-pressure.md` | ストレージ容量逼迫時の対応 |

## 整備タイミング

- **R4（観測性整備）**：アラート発火 → Runbook 参照という運用ループを成立させるため、観測性ダッシュボード整備と同時に主要 Runbook を整備
- **R5（仕上げ）**：本番デプロイに向けて全項目を埋める
- **以降**：実際にインシデントが発生したら新規 Runbook を追記

## 関連

- [observability](../requirements/2-foundation/04-observability.md) — 監視対象・アラート対象（Runbook の発火条件）
- [roadmap](../requirements/5-roadmap/01-roadmap.md) — R4 のスコープ
