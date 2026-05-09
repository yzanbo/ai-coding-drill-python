# prompts

LLM プロンプト管理ディレクトリ。バージョン管理し、Git 履歴と連動させる。

## 構成

```
prompts/
├── generation/             ← 問題生成プロンプト
│   └── typescript.v1.yaml  ← TS 用汎用（全カテゴリ対応、{{category}} 変数で差し替え）
└── judge/                  ← LLM-as-a-Judge プロンプト
    └── quality.v1.yaml     ← 品質評価（5 軸スコアリング）
```

## バージョン管理ルール

- ファイル名は `<role>.v<N>.yaml`（例：`typescript.v2.yaml`）
- 一度配布した `vN` は**書き換えない**（履歴保持）
- 改善時は `vN+1` を新規作成、本番で A/B テスト → 切替

## 関連
- 出力スキーマ：[../shared-types/schemas/](../shared-types/schemas/)
- 設計方針：[docs/requirements/2-foundation/03-llm-pipeline.md](../../docs/requirements/2-foundation/03-llm-pipeline.md)
- LLM プロバイダ抽象化：[docs/adr/0007-llm-provider-abstraction.md](../../docs/adr/0007-llm-provider-abstraction.md)
