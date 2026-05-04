# 要件定義書

AI Coding Drill — プログラミング学習サイト（問題自動生成 + サンドボックス検証）の要件定義書群。

---

## 構成の考え方：時系列 × 変更頻度 で物理分離

ディレクトリ番号は **作成順序（時系列）** と **変更頻度** を同時に表現する：

```
docs/requirements/
├── 1-vision/            ← ① 変わらない（最初に固める）
├── 2-foundation/        ← ② 変わりにくい（次に固める）
├── 3-cross-cutting/     ← ③ 機能追加で成長する横断要件
├── 4-features/          ← ④ スプリントで増える個別機能要件
└── 5-roadmap/           ← ⑤ 計画と進捗（時間軸で動く）
```

| バケット | 変更頻度 | 役割 |
|---|---|---|
| **1-vision** | 極小（プロジェクト方針再定義時のみ） | プロジェクトのビジョン・ペルソナ・ユーザーストーリー |
| **2-foundation** | 小（アーキテクチャ刷新時） | 非機能・アーキテクチャ・LLM パイプライン・観測性・技術スタック |
| **3-cross-cutting** | 中（機能追加時に更新） | ER 図・API 共通仕様（複数機能で共有される横断要件） |
| **4-features** | 大（スプリントごと） | 個別機能（F-XX）の詳細仕様 |
| **5-roadmap** | 大（スプリントごと） | ロードマップ・プロダクトバックログ |

---

## 読む順序（採用担当者・新規参画者向け）

```
1-vision/01-overview.md          まずビジョンと差別化軸を把握
  ↓
1-vision/02-personas.md          想定利用者を理解
  ↓
1-vision/03-user-stories.md      何が達成されるべきかを把握
  ↓
2-foundation/02-architecture.md  システム全体構造
  ↓
2-foundation/03-llm-pipeline.md  本サービスの差別化軸（LLM × サンドボックス）
  ↓
4-features/F-01〜F-05            個別機能の詳細
  ↓
5-roadmap/01-roadmap.md          いつ何を作るか
  ↓
docs/adr/                        各種設計判断の根拠
```

---

## 作る順序（新規プロジェクト立ち上げ時）

ディレクトリ番号は **読む順序**（変更頻度低 → 高、抽象 → 具体）を表すが、**書く順序**は番号順ではなくバケット間を行き来する。0 ベースから立ち上げる時は以下の順で書き進める：

| Step | タイミング | 書くファイル | 何を確定させるか |
|---|---|---|---|
| 1 | **Day 1** | [`1-vision/01-overview.md`](./1-vision/01-overview.md) | プロジェクトの存在意義（ビジョン・ゴール・スコープ外） |
| 2 | **Day 2-3** | [`1-vision/02-personas.md`](./1-vision/02-personas.md) | 主要ペルソナと利用文脈 |
| 3 | **Week 1** | [`1-vision/03-user-stories.md`](./1-vision/03-user-stories.md) | ペルソナ × 状況のストーリーマトリクス（MVP 範囲） |
| 4 | **MVP 着手前** | [`2-foundation/02-architecture.md`](./2-foundation/02-architecture.md) | システム全体構造・コンポーネント責務 |
| 5 | **MVP 計画時** | [`5-roadmap/01-roadmap.md`](./5-roadmap/01-roadmap.md) | リリース計画（R0〜R5）+ プロダクトバックログ |
| 6 | **MVP 着手時** | [`4-features/F-01.md`](./4-features/) 〜 | 各機能の受け入れ条件・画面・API |
| 7 | **最初のスキーマ定義時** | [`3-cross-cutting/01-data-model.md`](./3-cross-cutting/01-data-model.md) | ER 図・命名規則・横断方針 |
| 8 | **採用技術が固まった時** | [`2-foundation/05-runtime-stack.md`](./2-foundation/05-runtime-stack.md) | 技術選定 + 選定理由（同時に [`docs/adr/`](../adr/) に判断を記録） |
| 9 | **必要に応じて** | [`2-foundation/01-non-functional.md`](./2-foundation/01-non-functional.md)、[`2-foundation/03-llm-pipeline.md`](./2-foundation/03-llm-pipeline.md)、[`2-foundation/04-observability.md`](./2-foundation/04-observability.md)、[`3-cross-cutting/02-api-conventions.md`](./3-cross-cutting/02-api-conventions.md) 等 | 非機能要件の詳細・LLM パイプライン・観測性・API 共通仕様（実装着手段階で必要が出た時に書く） |

### この順序の根拠

- **ビジョン → ペルソナ → ストーリー**（Step 1〜3）：誰が何を達成したいかを最初に固める。これがないと以降の判断軸がぶれる
- **アーキ → ロードマップ → 機能**（Step 4〜6）：全体構造を先に決め、リリース計画でスコープを区切ってから個別機能に降りる
- **データモデル → 技術選定**（Step 7〜8）：機能から必要なデータ・API が見えてから横断方針を確定。技術選定は最も**可逆な判断は遅延**できる領域なので最後寄り（→ [CLAUDE.md](../../.claude/CLAUDE.md) 設計原則）
- **非機能・観測性等は遅延**（Step 9）：MVP 段階で必要になった時に書けば十分。先取りで詳細化しない（YAGNI）

### 実装スプリント開始後

スプリントごとに以下を**追記**する：

- [`4-features/`](./4-features/)：新機能 .md を [_template.md](./4-features/_template.md) から作成
- [`1-vision/03-user-stories.md`](./1-vision/03-user-stories.md)：新機能のユーザーストーリーを追加
- [`3-cross-cutting/01-data-model.md`](./3-cross-cutting/01-data-model.md)：新規エンティティが ER 図に増えたら更新
- [`5-roadmap/01-roadmap.md`](./5-roadmap/01-roadmap.md)：バックログ進捗・ステータスを更新
- [`docs/adr/`](../adr/)：重要な設計判断が発生したら新規 ADR を起票

[`2-foundation/`](./2-foundation/) の章はスプリント中はあまり更新されない（土台が固まっているため）。

### 注意：書く順序はプロジェクトに応じて調整可能

上記は **「個人開発・MVP 立ち上げ」**を想定した順序。以下のケースでは順序が変わる：

- **既存サービスの機能追加**：1-vision は既に固まっているので Step 6（features）から開始
- **大規模設計先行プロジェクト**：Step 4（architecture）と Step 8（runtime-stack）を Step 5（roadmap）より先に詳細化
- **受託開発**：Step 1〜3（vision）を顧客と合意してから Step 6（features）へ直行

順序は固定ルールではなく、**「どこから書き始めれば判断軸がブレないか」のガイド**として参考にする。

---

## ディレクトリ別 README

| ディレクトリ | README |
|---|---|
| 1-vision | [README.md](./1-vision/README.md) |
| 2-foundation | [README.md](./2-foundation/README.md) |
| 3-cross-cutting | [README.md](./3-cross-cutting/README.md) |
| 4-features | [README.md](./4-features/README.md) |
| 5-roadmap | [README.md](./5-roadmap/README.md) |

---

## テンプレート

新規ファイル / 既存ファイルへの追記に使う雛形：

| ディレクトリ | テンプレート | 用途 |
|---|---|---|
| 1-vision | [`_template-01-overview.md`](./1-vision/_template-01-overview.md) / [`_template-02-personas.md`](./1-vision/_template-02-personas.md) / [`_template-03-user-stories.md`](./1-vision/_template-03-user-stories.md) | ファイル別の専用テンプレ（overview / persona / user story それぞれ） |
| 2-foundation | [`_template.md`](./2-foundation/_template.md) | 横断テーマ章の追加用 |
| 3-cross-cutting | [`_template.md`](./3-cross-cutting/_template.md) | 横断的成長要件の追加用 |
| 4-features | [`_template.md`](./4-features/_template.md) | 機能カード（F-XX）の追加用 |

`5-roadmap/` はファイル数が固定的（基本は `01-roadmap.md` 1 ファイル）のため専用テンプレなし。

---

## 関連ドキュメント

- [docs/adr/](../adr/) — Architecture Decision Records（設計判断の履歴、Append-only）
- [docs/runbook/](../runbook/) — 運用 Runbook（R4 以降で整備）
- [README.md](../../README.md) — リポジトリ TOP

---

## 編集ルール

- **重複記述の禁止**：同じ情報は 1 箇所に集約し、他はリンクで誘導
- **守備範囲の遵守**：各ディレクトリ・ファイルの担当を超えない
- **冒頭に守備範囲を明記**：各ファイル先頭に「このドキュメントの守備範囲」と「関連トピックの参照先」を引用ブロックで宣言

詳細は [.claude/rules/requirements-docs.md](../../.claude/rules/requirements-docs.md) を参照。
