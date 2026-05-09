# 03. ユーザーストーリー

> **このドキュメントの守備範囲**：ペルソナ × 利用状況のユーザーストーリーマトリクス。**機能を増やすたびに追記される**（成長するドキュメント）。
> **ペルソナの定義**は [02-personas.md](./02-personas.md)、**機能ごとの受け入れ条件**は [4-features/](../4-features/) 配下の各 .md を参照。

---

## ペルソナ A：プログラミング学習者

`As a` プログラミング学習者
`I want` 〜 `So that` 〜

| 状態 | ストーリー | 関連機能 |
|---|---|---|
| ゲスト時 | サービスにログインする前に問題の雰囲気を眺めたい — どんな問題が出るか試したいから | [F-03](../4-features/F-03-problem-display-and-answer.md) |
| 認証時 | GitHub アカウントだけでログインしたい — 別アカウント登録の手間を省きたいから | [F-01](../4-features/F-01-github-oauth-auth.md) |
| 認証時 | カテゴリ・難易度を選んで新しい問題を生成リクエストしたい — 自分の興味・弱点に応じた練習をしたいから | [F-02](../4-features/F-02-problem-generation.md) |
| 認証時 | コードエディタで型診断を受けながら解答を書きたい — 構文ミスをサーバ採点前に潰したいから | [F-03](../4-features/F-03-problem-display-and-answer.md) |
| 認証時 | 解答を送ると即座に採点結果が返ってきてほしい — 手動レビューを待たず学習効率を最大化したいから | [F-04](../4-features/F-04-auto-grading.md) |
| 認証時 | 過去の解答履歴と弱点カテゴリを確認したい — 進捗と苦手分野を客観的に把握したいから | [F-05](../4-features/F-05-learning-history.md) |
| 認証時（バックログ） | 弱点カテゴリに応じた問題が自動で出題されてほしい — 効率的に苦手を克服したいから | F-06（バックログ、[5-roadmap](../5-roadmap/01-roadmap.md#f-06-適応型出題)） |
| 認証時（バックログ） | 誤答時にヒントを得て自力で解き直したい — 答えを見ずに学習を続けたいから | F-07（バックログ、[5-roadmap](../5-roadmap/01-roadmap.md#f-07-llm-ヒント機能)） |

---

## ペルソナ B：サービス運用者

`As a` サービス運用者
`I want` 〜 `So that` 〜

| ストーリー | 関連機能・横断テーマ |
|---|---|
| 生成成功率・LLM コスト・採点レイテンシをダッシュボードで継続観測したい — サービス品質と運用コストを定量的に把握するため | [F-08（バックログ）](../5-roadmap/01-roadmap.md#f-08-管理ダッシュボード) / [2-foundation/04-observability.md](../2-foundation/04-observability.md) |
| LLM 出力の品質評価（Judge）が機能しているか確認したい — 設計思想が動作で証明されている状態を維持するため | [2-foundation/03-llm-pipeline.md](../2-foundation/03-llm-pipeline.md) |
| アラートが発火したら Runbook に沿って原因切り分けと対応ができるようにしたい — 障害対応の再現性を確保するため | [2-foundation/04-observability.md: Runbook](../2-foundation/04-observability.md#運用-runbook) |
| LLM コストが日次予算を超過した時にすぐ気付きたい — クラウド料金の暴騰を防ぐため | [2-foundation/01-non-functional.md: コスト](../2-foundation/01-non-functional.md#コスト) |
| ジョブキューが詰まった兆候を早期検知したい — 採点遅延がユーザーに波及する前に対処するため | [2-foundation/04-observability.md: ジョブキュー](../2-foundation/04-observability.md#ジョブキューこのプロジェクトの中核) |

---

## ペルソナ C：採用担当者・面接官

`As a` 採用担当者
`I want` 〜 `So that` 〜

| ストーリー | 関連ドキュメント |
|---|---|
| README から設計判断（ADR）を辿って、なぜその技術を選んだか理解したい — 候補者の論理的説明力を評価するため | [README.md](../../../README.md) / [docs/adr/](../../adr/) |
| サービスを実際に触って、問題生成 → 解答 → 採点が一気通貫で動くことを確認したい — ポートフォリオが動作する成果物であることを確認するため | 公開サービス（R5 完了後） |
| ダッシュボードで観測性が機能していることを見たい — 運用設計まで考えられているかを評価するため | [2-foundation/04-observability.md](../2-foundation/04-observability.md) / 公開ダッシュボード |
| プロセス境界を跨ぐトレース連携の設計が見たい — 分散システム設計力を評価するため | [docs/adr/0010-w3c-trace-context-in-job-payload.md](../../adr/0010-w3c-trace-context-in-job-payload.md) |
| サンドボックス隔離の段階的進化（Docker → gVisor → Firecracker）を見たい — セキュリティ設計力を評価するため | [docs/adr/0009-disposable-sandbox-container.md](../../adr/0009-disposable-sandbox-container.md) |

---

## ストーリー追加時のルール

1. **新しい機能を追加する時**は、まずこのファイルにユーザーストーリーを追記してから [4-features/_template.md](../4-features/_template.md) で機能要件を作成する
2. **新しいペルソナが必要になった時**は [02-personas.md](./02-personas.md) に定義を追加してから本ファイルにストーリーを追加
3. ストーリーは `As a / I want / So that` または **「何をしたいか — なぜ」** の形式で記述
4. **観測可能・テスト可能な振る舞い**として書ける粒度を意識する（具体的な受け入れ条件は features/ で詳細化）
