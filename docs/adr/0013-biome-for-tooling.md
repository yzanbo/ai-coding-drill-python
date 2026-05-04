# 0013. コード品質ツール戦略（言語別、Biome / golangci-lint / ruff を採用）

- **Status**: Accepted
- **Date**: 2026-04-25
- **Decision-makers**: 神保 陽平

## Context（背景・課題）

3 言語（TypeScript / Go / Python）構成のモノレポで、各言語に同等レベルの品質ゲート（フォーマット・リント・型チェック）を整備する必要がある。

- モノレポ規模：MVP で 5〜10 パッケージ、Phase 7 で 8〜12 パッケージ
- 設定ファイル数を最小化したい
- CI 時間を抑えたい
- 各言語のモダンかつ実用的なツールを採用したい
- ポートフォリオで「3 言語に等価な品質ゲートを設計した」と語れる構成にしたい

## Decision（決定内容）

各言語で以下のツールを採用する。

### TypeScript（MVP）
- **Biome**：lint + format（Rust 製、高速、統合）
  - 共有設定：`packages/config/biome-config/`
  - TS で書かれた全アプリ・全パッケージで統一使用
  - ESLint + Prettier の組み合わせは不採用
- **TypeScript（`tsc --noEmit`）**：型チェック（Biome がカバーしないため必須）

### Go（MVP）
- **`gofmt`**：フォーマット（Go 標準）
- **`golangci-lint`**：メタリンター（`govet` / `staticcheck` / `errcheck` / `ineffassign` / `unused` / `gofumpt` / `gosec` 等を有効化）
- 型チェックは Go 言語仕様（`go build`）に内蔵されるため別途不要
- 任意追加：`govulncheck`（脆弱性スキャン）

### Python（Phase 7）
- **`ruff`**：lint + format（Astral 製、Rust、Linter + Formatter 統合）
- **型チェッカーは Phase 7 着手時に再評価**して決定する
  - **第一候補：pyright**（Microsoft、TS 製、実績充分、VS Code/Cursor 標準、`strict` モードで `tsc --noEmit` 相当）
  - **第二候補：ty**（Astral、Rust 製、`ruff` + `uv` と同社統合の美しさあり。2026 年初頭時点で開発中のため成熟度を Phase 7 着手時に再確認する）
  - 代替：mypy（特定プラグイン（`django-stubs` 等）が必要になった場合のみ）
- 選定方針：[ADR 0011: LLM プロバイダ抽象化](./0011-llm-provider-abstraction.md) と同じ「可逆な判断は遅延させ、判断時に最良を選ぶ」原則に従う
- 任意追加：`pip-audit`（脆弱性スキャン）

### MVP では導入しない補完ツール
以下は必要性が確認できた段階で追加する：
- Knip（未使用 export / 依存検出）
- lefthook / husky（Git フック）
- commitlint（コミットメッセージ規約）
- syncpack（依存バージョン整合）
- cspell（スペルチェック）

## Alternatives Considered（検討した代替案）

### TypeScript
| 候補 | 採用しなかった理由 |
|---|---|
| ESLint + Prettier | 設定ファイル乱立、CI が遅い、Biome 比で 25〜100 倍遅い |
| dprint | Linter 機能なし、Biome の方が統合的 |

### Go
| 候補 | 採用しなかった理由 |
|---|---|
| revive のみ | golangci-lint がメタリンターで複数ツール統合、より包括的 |
| 個別ツール手動運用 | 管理コスト高、golangci-lint で 1 コマンド化が定石 |

### Python
| 候補 | 採用しなかった理由（現時点で確定しない） |
|---|---|
| ruff + pyright で確定 | 妥当な選択だが、Phase 7 着手までに ty（Astral）が成熟する可能性があり、その場合 Astral 統合の方が綺麗。確定は時期尚早 |
| ruff + mypy で確定 | mypy は遅く、本プロジェクトでプラグインが必要になる見込みがない |
| ruff + pyrefly で確定 | Meta 製、新興、Astral 統合とはならない |

## Consequences（結果・トレードオフ）

### 得られるもの
- TS / Go / Python のすべてに同等レベルの品質ゲートを設計した、と語れる
- TS は単一ツール（Biome）で設定統合、CI 高速化
- Go は実績ある golangci-lint で網羅的にチェック
- Python は Phase 7 着手時の最良ツールを採用できる柔軟性
- Astral エコシステム（ruff / uv / 将来の ty）への統合余地を残せる

### 失うもの・受容するリスク
- Python の型チェッカーが Phase 7 まで未確定
- 補完ツール（Knip / lefthook / commitlint 等）が当面入らないため、品質保証に手作業が一部残る
- Biome は ESLint プラグインエコシステムを使えない

### 将来の見直しトリガー
- **Phase 7 着手時に Python 型チェッカーを正式決定**（必須）
  - ty が Stable に達していれば ty 採用を検討（Astral 統合）
  - そうでなければ pyright を採用
  - 決定内容を新規 ADR（例：`0015-python-type-checker.md`）として記録
- 未使用コード・依存が増えてきた段階で **Knip** 導入
- モノレポ品質を厳格化したい段階で **lefthook + commitlint** 導入
- 特定 ESLint プラグインが必須となるルールが必要になった場合は ESLint 併用または移行を検討

## References

- [05-runtime-stack.md: コード品質ツール](../requirements/2-foundation/05-runtime-stack.md)
- [ADR 0010: 言語の段階導入](./0010-phased-language-introduction.md)
- [ADR 0011: LLM プロバイダ抽象化（"可逆な判断は遅延させる" 原則）](./0011-llm-provider-abstraction.md)
- [Biome 公式](https://biomejs.dev/)
- [golangci-lint 公式](https://golangci-lint.run/)
- [Astral（ruff / uv / ty）](https://astral.sh/)
