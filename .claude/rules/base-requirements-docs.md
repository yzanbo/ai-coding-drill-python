# 要件定義書（`docs/requirements/`）の記述ルール

## 1. 重複記述の禁止

- 同じ情報を複数のファイルに重複して書かない
- 同じ事柄を 2 箇所で説明する必要が生じた場合は、**どちらか 1 箇所を「正」とし、他方からはその箇所へリンクする**
- 修正時に「片方だけ更新して片方が古いまま」になる事故を防ぐため、内容の単一情報源（Single Source of Truth）を徹底する

## 2. ディレクトリ構造と守備範囲

要件定義書は **時系列 × 変更頻度**で 5 つのバケットに分かれる：

```
docs/requirements/
├── 1-vision/            ← 変わらない（最初に固める）
├── 2-foundation/        ← 変わりにくい（次に固める）
├── 3-cross-cutting/     ← 機能追加で成長する横断要件
├── 4-features/          ← スプリントで増える個別機能要件
└── 5-roadmap/           ← 計画と進捗（時間軸で動く）
```

各バケットの担当範囲は以下の通り。

### `1-vision/` — ビジョン（変わらない）

| ファイル | 担当範囲 |
|---|---|
| `01-overview.md` | プロジェクト概要・ゴール・差別化軸・スコープ外 |
| `02-personas.md` | ペルソナ A / B / C の定義（属性・利用文脈） |
| `03-user-stories.md` | ペルソナ × 利用状況のユーザーストーリーマトリクス |

### `2-foundation/` — 全体要件（変わりにくい）

| ファイル | 担当範囲 |
|---|---|
| `01-non-functional.md` | 非機能要件（性能・セキュリティ・コスト・可用性等） |
| `02-architecture.md` | システム全体の論理構造、コンポーネントの責務、データ・ジョブの流れ |
| `03-llm-pipeline.md` | LLM 生成・評価パイプライン、品質評価の多層防御 |
| `04-observability.md` | 観測性（ログ・トレース・メトリクス・アラート） |
| `05-runtime-stack.md` | **サービスを動かす実装技術**（FE / BE / ワーカー / DB / LLM / サンドボックス / インフラ / 観測性ツール）+ 選定理由 + コスト試算 |
| `06-dev-workflow.md` | **開発フロー・品質保証技術**（モノレポ / コード品質ツール / 共有型生成 / CI/CD / テストフレームワーク）+ 選定理由 |

### `3-cross-cutting/` — 横断要件（機能追加で成長）

| ファイル | 担当範囲 |
|---|---|
| `01-data-model.md` | ER 図（全体俯瞰）・命名規則・横断方針（ID 戦略・タイムスタンプ・JSON カラム・ジョブペイロード共通フィールド・マイグレーション運用） |
| `02-api-conventions.md` | API 共通仕様（基本方針・認証・エラー形式・ステータスコード・レート制限・OpenAPI 方針） |

**個別テーブルのカラム定義は Drizzle スキーマ、個別エンドポイント詳細は [4-features/](../../docs/requirements/4-features/) + OpenAPI が SSoT**。このディレクトリには横断方針のみを置く。

### `4-features/` — 個別機能要件（実装単位）

- `F-XX-kebab-case-name.md` 形式で 1 機能 1 ファイル
- **個別機能の受け入れ条件・ユーザーストーリー・画面・API 詳細・フロー・バリデーション・ステータスは features/ が SSoT**
- 機能の俯瞰一覧は [`4-features/README.md`](../../docs/requirements/4-features/README.md) と [`1-vision/03-user-stories.md`](../../docs/requirements/1-vision/03-user-stories.md) を参照

### `5-roadmap/` — 計画と進捗（時間軸）

| ファイル | 担当範囲 |
|---|---|
| `01-roadmap.md` | ビジョン・リリース計画（R0〜R9）・プロダクトバックログ（Now / Next / Later / Parked）・スプリント運用（DoR / DoD） |

### `docs/adr/` — 設計判断の履歴

- 重要な技術・設計判断を **1 決定 1 ファイル、Append-only**で記録
- 新規決定が発生したら [`docs/adr/template.md`](../../docs/adr/template.md) を元に追加する

### テンプレート

| 用途 | テンプレ |
|---|---|
| 1-vision/01-overview.md を 0 ベースから書く | [`1-vision/_template-01-overview.md`](../../docs/requirements/1-vision/_template-01-overview.md) |
| 1-vision/02-personas.md にペルソナを追加する | [`1-vision/_template-02-personas.md`](../../docs/requirements/1-vision/_template-02-personas.md) |
| 1-vision/03-user-stories.md にストーリーを追加する | [`1-vision/_template-03-user-stories.md`](../../docs/requirements/1-vision/_template-03-user-stories.md) |
| 2-foundation/ に章を追加する | [`2-foundation/_template.md`](../../docs/requirements/2-foundation/_template.md) |
| 3-cross-cutting/ に横断要件を追加する | [`3-cross-cutting/_template.md`](../../docs/requirements/3-cross-cutting/_template.md) |
| 4-features/ に新機能 .md を追加する | [`4-features/_template.md`](../../docs/requirements/4-features/_template.md) |
| ADR を新規起票する | [`docs/adr/template.md`](../../docs/adr/template.md) |

`5-roadmap/` はファイル数が固定的（基本は `01-roadmap.md` 1 ファイル）のため専用テンプレなし。

## 3. 守備範囲の使い分け（最も重複しやすい組）

### 02-architecture と 05-runtime-stack（2-foundation 内）

- **02-architecture**：「何のコンポーネントが、どんな責務を持ち、どう連携するか」を書く。**ライブラリ名・サービス名・選定理由は書かない**
- **05-runtime-stack**：「各レイヤで具体的にどの技術を採用し、なぜそれを選んだか」を書く。**コンポーネントの責務やデータフローは書かない**

### 05-runtime-stack と 06-dev-workflow（実装技術 vs 開発フロー）

- **05-runtime-stack**：**サービスを動かす技術**（FE / BE / ワーカー / DB / LLM / サンドボックス / インフラ等）。エンドユーザーのリクエスト処理に関わる
- **06-dev-workflow**：**開発体験を支える技術**（モノレポ / コード品質ツール / 共有型生成 / CI/CD / テスト）。開発者の生産性・品質保証に関わる

### 3-cross-cutting と 4-features

- **3-cross-cutting/**：機能横断の方針（全体 ER 図・API 共通仕様）。個別テーブル・個別エンドポイントの詳細は書かない
- **4-features/**：機能個別の詳細（受け入れ条件・該当画面・該当 API のリクエスト/レスポンス例）。横断方針は重複させずリンクで誘導

### 1-vision と 4-features

- **1-vision/03-user-stories.md**：ペルソナ × 状況のストーリー全体俯瞰（**追記される**が、機能ファイル並みの詳細は書かない）
- **4-features/F-XX.md**：機能単位のユーザーストーリー + 受け入れ条件 + 画面 + API + フロー（個別機能の SSoT）

## 4. リンクの貼り方

- 関連情報が他ファイルにある場合、該当セクションへ**アンカーリンク**で飛ばす
- リンク先は GitHub Flavored Markdown のスラグルール（小文字化、空白はハイフン、記号は除去）に従う
- 形式：`→ <短い導入> は [<相対パス>: <セクション名>](./<相対パス>#<アンカー>)`
- 例：
  - `→ 採用フレームワーク・ライブラリの詳細は [05-runtime-stack.md: バックエンド API](./05-runtime-stack.md#バックエンド-apinestjs--typescript)`
  - `→ コンポーネントの責務は [02-architecture.md: Backend API](../2-foundation/02-architecture.md#backend-apinestjs)`

## 5. 各ファイル冒頭に守備範囲を明記

- 各 `.md` ファイルの先頭に、**自ファイルの守備範囲と、関連トピックの参照先**を引用ブロックで書く
- 例：

```markdown
> **このドキュメントの守備範囲**：システム全体の論理構造、コンポーネントの責務、データ・ジョブの流れ。
> **使うフレームワーク・ライブラリ・サービスの具体名や選定理由**は [05-runtime-stack.md](./05-runtime-stack.md) を参照。
```

## 6. 編集時のチェック

要件定義書を編集する際は以下を確認する：

- [ ] 追記する内容が他ファイル・他バケットと重複していないか
- [ ] 重複が発生した場合、片方を「正」として他方をリンクに置き換えたか
- [ ] 各セクション末に必要な相互リンクが貼られているか
- [ ] ファイルごとの守備範囲（上記）から外れた内容を書いていないか
- [ ] 機能個別の話を 1-vision/2-foundation/3-cross-cutting に書いていないか（→ 4-features/ に書く）
- [ ] 横断方針を 4-features/ に書いていないか（→ 適切な base 系バケットに書く）

## 7. 例外

- **概要レベルの一文の引用**（例：「Backend API は NestJS で実装」）は、そのファイルの文脈上必要なら重複可。ただし詳細説明は単一箇所に集約する
- **概念図・全体構成図** に技術名が登場するのは可（図は概観の理解を優先）
