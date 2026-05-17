# 4-features/

**変更頻度：大**（スプリントごとに増える・ステータスが更新される）

---

## このディレクトリの役割

機能（Feature）単位で 1 ファイル 1 機能の要件定義書を配置する。

- 個別機能の **What / 受け入れ条件 / 画面 / API 詳細 / フロー / バリデーション / ステータス**
- 各ファイルは **スプリントの実装単位**

機能横断のアーキテクチャ・非機能・ER 図全体・API 共通仕様は扱わない（[2-foundation/](../2-foundation/) と [3-cross-cutting/](../3-cross-cutting/) を参照）。

---

## 配置とファイル命名

機能はフラット配置 + ドメイン名ベースで管理する（数値 ID は採番しない）。

- **1 ドメイン 1 ファイル**：1 つのドメイン（認証 / 採点 / 学習履歴 等）は 1 ファイルにまとめる（`authentication.md` / `grading.md` / `learning.md`）
- **1 ドメイン内に複数ワークフローがある場合は prefix 付きで分割**：例：問題ドメインは「生成」と「表示・解答入力」が大きく性質が違うため `problem-generation.md` / `problem-display-and-answer.md` の 2 ファイル
- **ファイル名は kebab-case**（例：`authentication.md`、`problem-generation.md`）
- **数値 ID（旧 `F-XX` 形式）は採番しない**：path 自体が安定参照子になる（例：「authentication」「problem-generation」が ID 相当）。詳細な根拠は [.claude/rules/docs-rules.md](../../../.claude/rules/docs-rules.md) §3 を参照
- **alphabetical sort で関連ファイルが並ぶ**：同ドメインの複数ファイルは prefix で集まる（`problem-*` で並ぶ）
- 10+ ドメインに広がってきたらサブディレクトリ復活を検討（現状はフラットで十分）
- 新規作成は [`/new-requirements`](../../../.claude/CLAUDE.md) カスタムコマンド経由を推奨

---

## 機能一覧

### MVP（リリース R1 必須）

> **ステータス凡例**：「要件定義中」= 受け入れ条件確定済みだが未着手。「実装中」= スプリント着手済み。「完了」= DoD 達成。

| ドメイン | 機能 | 対象ロール | ステータス |
|---|---|---|---|
| 認証 | [GitHub OAuth ログイン](./authentication.md) | ゲスト → 認証ユーザー | 要件定義中 |
| 問題 | [問題生成リクエスト](./problem-generation.md) | 認証ユーザー | 要件定義中 |
| 問題 | [問題表示・解答入力](./problem-display-and-answer.md) | ゲスト / 認証ユーザー | 要件定義中 |
| 採点 | [自動採点](./grading.md) | 認証ユーザー | 要件定義中 |
| 学習 | [学習履歴・統計](./learning.md) | 認証ユーザー | 要件定義中 |

### バックログ（着手時に詳細化）

リリース順。着手時に [_template.md](./_template.md) で詳細化する（現状は概要のみ、ファイル未作成）：

| ドメイン（予定） | 機能 | リリース |
|---|---|---|
| 管理 | [管理ダッシュボード](../5-roadmap/01-roadmap.md#管理ダッシュボード) | R4 |
| 問題 | [適応型出題（弱点に基づく問題生成）](../5-roadmap/01-roadmap.md#適応型出題) | R6 |
| ヒント | [LLM ヒント機能](../5-roadmap/01-roadmap.md#llm-ヒント機能) | R6 |

詳細な俯瞰は [1-vision/01-overview.md](../1-vision/01-overview.md) と [5-roadmap/01-roadmap.md](../5-roadmap/01-roadmap.md#later着手未定)。

---

## アジャイル運用上の位置づけ

- 各機能ファイルは **スプリントの実装単位**
- **「受け入れ条件すべて満たす」+ 「PR マージ済み」= スプリント完了の DoD**
- スプリント開始時に該当機能の受け入れ条件を確定 → 実装 → スプリント終了時に「ステータス」をチェック
- 詳細は [5-roadmap/01-roadmap.md](../5-roadmap/01-roadmap.md) を参照

---

## 関連

- [_template.md](./_template.md) — 機能カード新規作成用テンプレ
- [1-vision/03-user-stories.md](../1-vision/03-user-stories.md) — ペルソナ × 状況のストーリーマトリクス
- [3-cross-cutting/](../3-cross-cutting/) — 横断要件（ER 図・API 共通仕様）
- [docs/adr/](../../adr/) — 設計判断の履歴
