---
paths:
  - "packages/prompts/**/*"
  - "packages/shared-types/schemas/**/*"
---

# LLM プロンプト管理ルール

`packages/prompts/` 配下で LLM プロンプトを YAML として管理する。プロンプトはコード資産であり、バージョン管理・A/B テスト可能な構造を維持する。

詳細は [03-llm-pipeline.md](../../docs/requirements/2-foundation/03-llm-pipeline.md) と [ADR 0011](../../docs/adr/0011-llm-provider-abstraction.md)。

## ファイル構成

```
packages/prompts/
├── generation/                       # 問題生成プロンプト
│   ├── typescript.v1.yaml            # TS 用汎用（全カテゴリ対応、{{category}} 変数）
│   └── typescript.v2.yaml            # 改善版（追加時）
├── judge/                            # LLM-as-a-Judge プロンプト
│   ├── quality.v1.yaml               # 品質評価（5 軸スコアリング）
│   └── quality.v2.yaml
└── README.md                         # 運用ルール
```

## バージョン管理

### 命名

- `<role>.v<N>.yaml`（例：`typescript.v2.yaml`）
- `v` は小文字、`N` は連番（v1, v2, v3, ...）

### 不変性

- 一度配布した `vN` は**書き換えない**（履歴保持）
- 改善時は `vN+1` を新規作成、本番で A/B テスト → 切替
- 削除しない（旧プロンプトで生成された問題のトレーサビリティ確保）

## YAML スキーマ

### 生成プロンプト（`generation/`）

```yaml
version: v1
language: typescript
model_role: generator

system_prompt: |
  ...

user_template: |
  カテゴリ: {{category}}
  難易度: {{difficulty}}

output_schema_ref: ../../shared-types/schemas/problem.schema.json

few_shot_examples:
  - input: { category: "配列操作", difficulty: "easy" }
    output: { ... }

parameters:
  temperature: 0.7
  max_tokens: 4096

metadata:
  created_at: "YYYY-MM-DD"
  notes: |
    バージョンの意図、変更点、評価結果のメモ
```

### Judge プロンプト（`judge/`）

```yaml
version: v1
model_role: judge

system_prompt: |
  ...

user_template: |
  ===== 問題 =====
  {{problem_json}}

output_schema_ref: ../../shared-types/schemas/judge-result.schema.json

evaluation:
  num_runs: 3            # 同じ問題を複数回評価して平均
  threshold: 20          # 合計スコア閾値（25 点満点中）

parameters:
  temperature: 0.3       # 評価は安定性重視で低め
  max_tokens: 2048

metadata:
  created_at: "YYYY-MM-DD"
  notes: |
    評価軸の意図、人間評価との相関、調整履歴
```

## プロンプトの編集ルール

### 軽微な修正（typo・表現調整）

- `vN` 内で直接修正可能
- ただし**本番リリース後**は不変扱いとし、新バージョンを作る

### ロジック変更（評価軸追加、変数追加、出力スキーマ変更）

- 必ず `vN+1` を新規作成
- A/B テスト：本番で並行稼働、メトリクス（生成成功率、Judge スコア分布、コスト）を比較
- 切替後も旧バージョンは残す

### 出力スキーマの変更

- スキーマ自体は `packages/shared-types/schemas/` で管理（→ [ADR 0014](../../docs/adr/0014-json-schema-as-single-source-of-truth.md)）
- スキーマ変更は破壊的なので、プロンプトと出力スキーマをセットでバージョンアップする

## 変数の埋め込み

- 変数は `{{name}}` 形式（Mustache 風）
- 実装側で安全な置換ライブラリ（例：`mustache`）を使う、文字列置換は使わない（インジェクション対策）
- 変数の必須・任意は `metadata` セクションに記載

## モデル指定の方針

- **プロンプト YAML 自体に具体的なモデル名（claude-haiku-4-5 等）を書かない**
- モデル指定は `LlmProvider` 設定（別 YAML or 環境変数）で行う（→ [ADR 0011](../../docs/adr/0011-llm-provider-abstraction.md)）
- 同じプロンプトを複数モデルで動かせる構造を維持する

## キャッシュキー

LLM レスポンスキャッシュ（Redis）のキーは以下で構成：

```
llm:cache:<sha256(prompt_yaml_content + variables_json + model_id)>
```

- プロンプトファイルの内容そのものをハッシュに含める → バージョンアップ時に自動でキャッシュ無効化
- TTL 7 日

## few-shot examples の管理

- 1 ファイル内に 1〜3 例を埋め込む
- 例が多すぎる場合は別ファイル（`examples/<category>.yaml`）に分離して `extends` で参照
- 例題に**既存問題と紛らわしいもの**を含めない（生成バイアスを避ける）

## メタデータ・ログ

実装側（`apps/api/src/generation/`）はプロンプト読み込み時に以下を OTel スパンに記録：

- `prompt.path`：YAML ファイルパス
- `prompt.version`：v1 / v2 等
- `prompt.role`：generator / judge
- `prompt.hash`：内容の SHA256

これにより「どのプロンプトで生成された問題か」を後から追跡できる。

## 評価・改善サイクル（R2 以降）

1. 本番でプロンプト v1 を稼働
2. メトリクス収集：生成成功率、Judge スコア分布、コスト、ユーザー評価
3. 課題抽出：例「テストケースが甘い」「難易度がブレる」
4. プロンプト v2 を作成（システムプロンプトに制約を追加 等）
5. A/B テスト：v1 と v2 を 50:50 で並行稼働
6. メトリクス比較 → 採用判断
7. 採用後も v1 は保持（履歴・回帰テスト用）

## ライセンス・著作物

- 既存著作物の文章をプロンプト内に埋め込まない（教材引用は R7 の RAG 経路で別途処理）
- few-shot examples のコードは独自に書く、書籍・既存サイトからのコピーは禁止
