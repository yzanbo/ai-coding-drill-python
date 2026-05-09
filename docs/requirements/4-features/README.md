# 4-features/

**変更頻度：大**（スプリントごとに増える・ステータスが更新される）

---

## このディレクトリの役割

機能（Feature）単位で 1 ファイル 1 機能の要件定義書を配置する。

- 個別機能の **What / 受け入れ条件 / 画面 / API 詳細 / フロー / バリデーション / ステータス**
- 各ファイルは **スプリントの実装単位**

機能横断のアーキテクチャ・非機能・ER 図全体・API 共通仕様は扱わない（[2-foundation/](../2-foundation/) と [3-cross-cutting/](../3-cross-cutting/) を参照）。

---

## ファイル命名

- `F-XX-kebab-case-name.md`（例：`F-01-github-oauth-auth.md`）
- 連番 `XX` は採番順、欠番不可
- 新規作成は [`/new-requirements`](../../../.claude/CLAUDE.md) カスタムコマンド経由を推奨

---

## 機能一覧

### MVP（リリース R1 必須）

| ID | 機能名 | 対象ロール | ステータス |
|---|---|---|---|
| [F-01](./F-01-github-oauth-auth.md) | GitHub OAuth ログイン | ゲスト → 認証ユーザー | 要件定義中 |
| [F-02](./F-02-problem-generation.md) | 問題生成リクエスト | 認証ユーザー | 要件定義中 |
| [F-03](./F-03-problem-display-and-answer.md) | 問題表示・解答入力 | ゲスト / 認証ユーザー | 要件定義中 |
| [F-04](./F-04-auto-grading.md) | 自動採点 | 認証ユーザー | 要件定義中 |
| [F-05](./F-05-learning-history.md) | 学習履歴・統計 | 認証ユーザー | 要件定義中 |

### バックログ（着手時に詳細化）

リリース順。着手時に [_template.md](./_template.md) で詳細化する（現状は概要のみ）：

| ID | 機能名 | リリース |
|---|---|---|
| F-08 | 管理ダッシュボード | R4 |
| F-06 | 適応型出題（弱点に基づく問題生成） | R6 |
| F-07 | LLM ヒント機能 | R6 |

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
