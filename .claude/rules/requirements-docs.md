---
paths:
  - "docs/requirements/**/*"
---

# 要件定義書（`docs/requirements/`）の記述ルール

このプロジェクトでは要件定義書を **5 バケット時系列構造**（[ADR 0019](../../docs/adr/0019-requirements-as-5-buckets.md)）で運用する。本ルールはそのディレクトリ構造下の `.md` を編集するときに従う規約。

---

## 1. 重複記述の禁止（SSoT 原則）

- 同じ情報を複数のファイルに重複して書かない
- 同じ事柄を 2 箇所で説明する必要が生じた場合は、**どちらか 1 箇所を「正」とし、他方からはその箇所へリンクする**
- 修正時に「片方だけ更新して片方が古いまま」になる事故を防ぐため、内容の単一情報源（Single Source of Truth）を徹底する

---

## 2. ディレクトリ構造と守備範囲

要件定義書は **時系列 × 変更頻度** で 5 つのバケットに分かれる：

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

### `docs/adr/` — 設計判断の履歴（参考）

- 重要な技術・設計判断を **1 決定 1 ファイル**で記録（判断更新時は本文を直接書き換え、履歴は git log で辿る）
- 新規決定が発生したら [`docs/adr/template.md`](../../docs/adr/template.md) を元に追加する
- 索引：[`docs/adr/README.md`](../../docs/adr/README.md)

---

## 3. テンプレート

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

---

## 4. 守備範囲の使い分け（最も重複しやすい組）

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

---

## 5. リンクの貼り方

- 関連情報が他ファイルにある場合、該当セクションへ**アンカーリンク**で飛ばす
- リンク先は GitHub Flavored Markdown のスラグルール（小文字化、空白はハイフン、記号は除去）に従う
- 形式：`→ <短い導入> は [<相対パス>: <セクション名>](./<相対パス>#<アンカー>)`
- 例：
  - `→ 採用フレームワーク・ライブラリの詳細は [05-runtime-stack.md: バックエンド API](./05-runtime-stack.md#バックエンド-apinestjs--typescript)`
  - `→ コンポーネントの責務は [02-architecture.md: Backend API](../2-foundation/02-architecture.md#backend-apinestjs)`

---

## 6. 各ファイル冒頭に守備範囲を明記

- 各 `.md` ファイルの先頭に、**自ファイルの守備範囲と、関連トピックの参照先**を引用ブロックで書く
- 例：

```markdown
> **このドキュメントの守備範囲**：システム全体の論理構造、コンポーネントの責務、データ・ジョブの流れ。
> **使うフレームワーク・ライブラリ・サービスの具体名や選定理由**は [05-runtime-stack.md](./05-runtime-stack.md) を参照。
```

---

## 7. 図の表現方法（Mermaid 化推奨）

要件定義書では **GitHub ネイティブサポートの Mermaid 図** を積極的に使う。テキスト擬似図（ASCII アート）は読みにくく、視覚的訴求力で劣るため原則避ける。

### Mermaid 化を **推奨する** ケース

| 種類 | 用途 | 例 |
|---|---|---|
| `flowchart` | 複数分岐のフロー / アーキテクチャ全体図 / 物理配置 | [02-architecture.md: 全体構成](../../docs/requirements/2-foundation/02-architecture.md#全体構成概念図) / [03-llm-pipeline.md: 生成フロー](../../docs/requirements/2-foundation/03-llm-pipeline.md#生成フロー) |
| `sequenceDiagram` | 時系列で actor 間のメッセージ交換 | [02-architecture.md: 1 ジョブが流れる完全な経路](../../docs/requirements/2-foundation/02-architecture.md#1-ジョブが流れる完全な経路) |
| `erDiagram` | DB スキーマ・エンティティ関係 | [01-data-model.md: ER 図](../../docs/requirements/3-cross-cutting/01-data-model.md#er-図全体俯瞰) |
| `stateDiagram` | 状態遷移（ジョブ state の遷移等、必要時） | — |

### Mermaid 化を **しなくてよい** ケース

| 種類 | 理由 |
|---|---|
| トレースのスパンツリー（インデント + ms 表示） | Jaeger/Tempo UI 等の業界標準テキスト表現が読みやすい |
| 3 行程度の単純なフロー | Mermaid 化するとノイズが増える |
| コード例・JSON 例・SQL 例 | コードブロックで十分 |
| マイグレーション SQL の例示 | コードブロックで十分 |

### Mermaid の書き方規約

- **GitHub Mermaid サポート**に準拠（リポジトリ上で自動レンダリング）
- ノードに **色分類**を付ける（`classDef`）：典型的には終端（青）/ 判定（橙）/ 処理（緑）/ 失敗（赤）等
- 図の下に **凡例 / 読み方** を必ず添える（実線=同期 / 点線=非同期 等の判別）
- 図の下に **設計判断ポイント表** を併記すると、視覚情報 + テキスト情報で理解度が増す
- 流れの方向：上下なら `flowchart TB`、左右なら `flowchart LR`
- 1 つの図に詰め込みすぎない（**1 図 1 メッセージ**）。情報が多い場合は複数図に分割

### Mermaid アンチパターン（既知のレンダリングエラー）

GitHub Mermaid パーサで実際に落ちた事例。**新規・編集時は GitHub UI 上でレンダリング確認すること**（ローカルで通っても GitHub で落ちることがある）。

- **`participant` エイリアスに `<br/>` を入れない**（sequenceDiagram）：図全体が描画されない。改行は `Note over X` に分離
- **dotted-arrow のラベルに `.` を入れない**（flowchart）：`A -. docker.sock .-> B` は Lexical error。pipe-quoted 形式 `A -.->|"docker.sock"| B` を使う
- **`->>-` / `->>+` 暗黙修飾子を多用しない**（sequenceDiagram）：末尾 `-` は **送信者を** deactivate するため誤用しやすく "Trying to inactivate an inactive participant" で落ちる。複数往復・非対称な活性化は明示的な `activate` / `deactivate` キーワードで書く
- **メッセージ内の特殊文字を避ける**：中括弧 `{}` / シングルクォート `'` / `<br/>` はパーサ依存。丸括弧 `()` と平文に置換

### 既存の Mermaid 図参考（2026-05 時点）

> **注意**：以下は**参考例**であり、新規追加されると陳腐化する。最新状況は各ファイル本体を参照。

| ファイル | 図の数 | 種類 |
|---|---|---|
| [02-architecture.md](../../docs/requirements/2-foundation/02-architecture.md) | 3 | flowchart × 2（論理構成 / 物理配置）+ sequenceDiagram（ジョブフロー） |
| [03-llm-pipeline.md](../../docs/requirements/2-foundation/03-llm-pipeline.md) | 2 | flowchart × 2（生成フロー / 採点フロー） |
| [01-data-model.md](../../docs/requirements/3-cross-cutting/01-data-model.md) | 1 | erDiagram |

新規ファイル作成・既存ファイル編集時にフロー / 関係図 / 構造図 が必要になったら、**まず Mermaid で書けないか検討**する。

---

## 8. 編集時のチェック

要件定義書を編集する際は以下を確認する：

### 内容のチェック

- [ ] 追記する内容が他ファイル・他バケットと重複していないか
- [ ] 重複が発生した場合、片方を「正」として他方をリンクに置き換えたか
- [ ] 各セクション末に必要な相互リンクが貼られているか
- [ ] ファイルごとの守備範囲（§2）から外れた内容を書いていないか
- [ ] 機能個別の話を 1-vision / 2-foundation / 3-cross-cutting に書いていないか（→ 4-features/ に書く）
- [ ] 横断方針を 4-features/ に書いていないか（→ 適切な横断バケット（2-foundation / 3-cross-cutting）に書く）

### 形式のチェック

- [ ] ファイル冒頭に **守備範囲記述（quote ブロック）** があるか（§6）
- [ ] 章番号（`# NN.`）が **ファイル名の連番**と一致しているか
- [ ] 他ファイルへのリンクが正しい相対パスで書かれているか（GitHub レンダリングで切れない）
- [ ] フロー / 関係図 / 構造図 を **Mermaid で書けないか** 検討したか（§7）
- [ ] Mermaid 図を追加・編集した場合、§7 アンチパターン（`<br/>` / dotted-arrow のドット / `->>-` 暗黙修飾子 / 特殊文字）に該当していないか
- [ ] Mermaid 図を追加・編集した場合、**GitHub UI 上でレンダリング確認**を行ったか（ローカルで通っても GitHub で落ちることがある）
- [ ] 重要な設計判断が含まれる場合、対応する **ADR が起票** されているか / 既存 ADR にリンクしているか

---

## 9. 例外

- **概要レベルの一文の引用**（例：「Backend API は NestJS で実装」）は、そのファイルの文脈上必要なら重複可。ただし詳細説明は単一箇所に集約する
- **概念図・全体構成図** に技術名が登場するのは可（図は概観の理解を優先）
- **コード例として技術名を含む断片**（例：`pnpm db:migrate`）は §1 の重複禁止対象外

---

## 10. 関連ルール・ドキュメント

- [docs/requirements/README.md](../../docs/requirements/README.md) — 5 バケット構造の全体マップ・読む順序・書く順序ガイド
- [docs/adr/0019-requirements-as-5-buckets.md](../../docs/adr/0019-requirements-as-5-buckets.md) — 5 バケット構造の設計判断
- [docs/adr/template.md](../../docs/adr/template.md) — ADR 作成時のテンプレ
- 各バケット README — 各 `docs/requirements/<バケット>/README.md`
