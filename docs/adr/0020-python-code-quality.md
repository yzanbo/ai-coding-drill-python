# 0020. Python のコード品質ツールに ruff を採用、型チェッカーは R7 着手時に決定

- **Status**: Accepted
- **Date**: 2026-04-25
- **Decision-makers**: 神保 陽平

## Context（背景・課題）

Python は MVP では使わず、R7の分析パイプライン・RAG 関連で導入する予定（→ [ADR 0003: 言語の段階導入](./0003-phased-language-introduction.md)）。R7 着手時に必要となる Python 側のコード品質ツール（フォーマット・lint・型チェック）を **MVP 段階で方針だけ確定**し、確定が困難な部分は判断時まで遅延させる。

- Python は R7以降で利用、MVP では未使用
- 「3 言語に等価な品質ゲートを設計した」と語れる構成にしたい
- 2026 年初頭時点で Astral 製エコシステム（ruff / uv / ty）が急速に整備中
- R7 着手は MVP 完成後のため、確定すべき判断と遅延すべき判断を分離する

関連：

- TS の品質ツール → [ADR 0018](./0018-biome-for-tooling.md)
- Go の品質ツール → [ADR 0019](./0019-go-code-quality.md)
- 「可逆な判断は遅延させる」原則 → [ADR 0007: LLM プロバイダ抽象化](./0007-llm-provider-abstraction.md)

## Decision（決定内容）

- **lint + format に [`ruff`](https://docs.astral.sh/ruff/)** を採用する（Astral 製、Rust、linter + formatter 統合）
- **型チェッカーは R7 着手時に再評価して正式決定**する
  - **第一候補：[pyright](https://github.com/microsoft/pyright)**（Microsoft、TS 製、実績充分、VS Code / Cursor 標準、`strict` モードで `tsc --noEmit` 相当）
  - **第二候補：[ty](https://github.com/astral-sh/ty)**（Astral、Rust 製、`ruff` + `uv` と同社統合の美しさあり。2026 年初頭時点で開発中のため成熟度を R7 着手時に再確認する）
  - **代替：mypy**（特定プラグイン（`django-stubs` 等）が必要になった場合のみ）
- 任意追加：[`pip-audit`](https://github.com/pypa/pip-audit)（脆弱性スキャン）

## Why（採用理由）

### なぜ ruff か（lint + format 統合）

1. **`lint + format` を Rust で統合**
   - Astral 製で `flake8` / `black` / `isort` 等を 1 ツールに置換
   - TS の Biome と対称的な設計思想（Rust 製・統合・高速）で、3 言語横断で「単一ツール統合」哲学が一貫する
2. **CI 高速化**
   - 大規模コードベースで flake8 + black + isort の数十倍速、CI 時間を顕著に短縮
3. **エコシステム集中**
   - ruff 単体で `flake8-bugbear` / `pyupgrade` / `pylint` 系ルール群を吸収、依存ツリーが薄い
4. **Astral エコシステム統合の余地**
   - ruff / uv / ty が同社製で連携する将来性に賭ける（パッケージ管理の `uv` も R7 で採用予定 → [ADR 0023](./0023-turborepo-pnpm-monorepo.md)）

### なぜ型チェッカー選定を R7 まで遅延するか

1. **「可逆な判断は遅延させ、判断時に最良を選ぶ」原則**
   - LLM プロバイダ抽象化（→ [ADR 0007](./0007-llm-provider-abstraction.md)）と同じ原則
   - 型チェッカーは R7 で初めて Python コードが書かれる時点まで「使わない」状態が続く
2. **2026 年初頭時点で ty が成熟途上**
   - ty が Stable に達していれば Astral 統合（ruff / uv / ty）の美しさを採れる
   - 達していなければ実績ある pyright を採れる
   - R7 着手時の状況を見て判断する方が合理的
3. **遅延コストがほぼゼロ**
   - R7 まで Python コードが書かれないため、「決まっていない」ことの実害がない
   - MVP 段階で先取りで決定すると、R7 着手時の選択肢を狭める

## Alternatives Considered（検討した代替案）

### lint + format ツール

| 候補 | 採用しなかった理由 |
|---|---|
| ruff（採用） | — |
| flake8 + black + isort | 3 ツール構成、CI 遅い、設定ファイル乱立、メンテ衰退傾向 |
| pylint | 高機能だが遅く設定が冗長、ruff が pylint 系ルールも順次取り込み中 |

### 型チェッカー（R7 着手時の候補比較）

| 候補 | 概要 | 現時点（2026-04）の判定 |
|---|---|---|
| ty（Astral） | Rust 製、ruff / uv と同社統合 | 成熟途上、R7 着手時に再評価 |
| pyright（Microsoft）| TS 製、実績充分、VS Code / Cursor 標準、`strict` モードで `tsc --noEmit` 相当 | 第一候補（ty が間に合わなかった場合に採用） |
| pyrefly（Meta）| Meta 製、新興 | Astral 統合とはならない、採用優先度低 |
| mypy | 老舗、プラグインエコシステム豊富 | 速度面で劣る、特定プラグイン（`django-stubs` 等）が必要な場合のみ採用検討 |

## Consequences（結果・トレードオフ）

### 得られるもの

- R7 着手時の最良ツールを採用できる柔軟性
- Astral エコシステム（ruff / uv / 将来の ty）への統合余地を残せる
- TS / Go と等価な品質ゲートを最小構成で実現できる見込み
- MVP 期間中に「型チェッカー選定で議論を消費する」コストを回避

### 失うもの・受容するリスク

- 型チェッカーが R7 着手まで未確定（だが R7 まで Python コードが無いため実害なし）
- ty が R7 着手時にも成熟していなかった場合は pyright に倒すことになり、Astral 統合の美しさは諦める
- ruff の rule set 拡充は速いが、特殊なルール（pylint 由来の一部）はカバー外の時期がある

### 将来の見直しトリガー

- **R7 着手時に Python 型チェッカーを正式決定（必須）**
  - ty が Stable に達していれば ty 採用を検討（Astral 統合）
  - そうでなければ pyright を採用
  - 決定内容を新規 ADR として記録（本 ADR を Superseded by する形）
- ruff が衰退・停滞した場合（極めて低確率）→ 個別ツール（black + isort + flake8）併用に戻す検討

## References

- [06-dev-workflow.md: コード品質ツール](../requirements/2-foundation/06-dev-workflow.md#コード品質ツール)
- [ADR 0018: TypeScript のコード品質ツール](./0018-biome-for-tooling.md)
- [ADR 0019: Go のコード品質ツール](./0019-go-code-quality.md)
- [ADR 0003: 言語の段階導入](./0003-phased-language-introduction.md)
- [ADR 0007: LLM プロバイダ抽象化（"可逆な判断は遅延させる" 原則）](./0007-llm-provider-abstraction.md)
- [Astral（ruff / uv / ty）](https://astral.sh/)
- [pyright 公式](https://github.com/microsoft/pyright)
