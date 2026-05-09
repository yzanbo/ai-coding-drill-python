# 0022. 設定ファイル形式の選定方針（TS > JSONC > YAML の優先順位）

- **Status**: Accepted
- **Date**: 2026-05-06
- **Decision-makers**: 神保 陽平

## Context（背景・課題）

このリポジトリには既に多数の設定ファイルがあり、ツールごとに形式が混在している：

| 既存ファイル | 形式 | 形式選択の根拠 |
|---|---|---|
| `.github/workflows/*.yml` | YAML | GitHub Actions が強制 |
| `.github/dependabot.yml` | YAML | GitHub が強制 |
| `pnpm-workspace.yaml` | YAML | pnpm が強制 |
| `lefthook.yml` | YAML | lefthook の慣習 |
| `tsconfig.json` | JSONC | TypeScript の慣習（拡張子は `.json` だが JSONC 解釈） |
| `biome.jsonc` | JSONC | Biome 公式が推奨 |
| `turbo.jsonc` | JSONC | Turborepo の慣習 |
| `commitlint.config.mjs` ※ | MJS | 自由選択（JS / TS / JSON / YAML 可） |

> ※ 上記テーブルは**本 ADR を起票した時点のスナップショット**である。本 ADR の Decision「即時適用」により、本 PR で `commitlint.config.mjs` は `commitlint.config.ts` に変換され、ADR 0022 の方針が第 1 例として実適用される。詳細は後述の「本 ADR の即時適用」を参照。

ツール側の制約は 3 種類に分けられる：

1. **強制**：その形式しか受け付けない（GitHub Actions / Dependabot / pnpm-workspace）
2. **ecosystem 慣習**：複数受け付けるが公式 / 大多数のユーザが特定形式を使う（Biome の `.jsonc` / Turborepo の `.jsonc` / TypeScript の `tsconfig.json`）
3. **自由選択**：複数形式を等しく受け付け、ユーザに判断が委ねられる（commitlint / syncpack / Vitest 等）

**自由選択のケースで判断軸が明確でないと、人 / LLM ごとに選択が揺れて統一感が損なわれる**。実際、本 ADR の検討中に「commitlint を `.mjs` のまま残すか `.ts` に揃えるか」「syncpack を `.json` / `.cjs` / `.ts` のどれにするか」といった議論が個別に発生した。同じ議論を将来 Knip / Vitest / 他ツール導入時に再発させないため、判断軸を方針として文書化する。

## Decision（決定内容）

**設定ファイルの形式選定は「ツール強制 → ecosystem 慣習 → 自由選択時 TS > JSONC > JS > YAML > JSON」の優先順位で決め、コメントを書ける形式を書けない形式より常に優先する。**

**運用詳細（前提原則 / 優先順位の Tier 表 / JSONC として扱われる `.json` 例外リスト / 適用フローチャート）の SSoT は [06-dev-workflow.md: 設定ファイル形式の優先順位](../requirements/2-foundation/06-dev-workflow.md#設定ファイル形式の優先順位) を参照**（運用ルール型 ADR、→ [`.claude/rules/docs-rules.md` §2](../../.claude/rules/docs-rules.md)）。本 ADR は採用根拠（§Why）と代替案（§Alternatives Considered）を扱う。

### 本 ADR の即時適用：`commitlint.config.mjs` → `commitlint.config.ts`（適用済み）

本方針の適用第 1 例として、本 ADR と同じ PR で `commitlint.config.mjs` を `commitlint.config.ts` に変換した。`@commitlint/types` の `UserConfig` 型を import することで、`type-enum` / `scope-enum` / `level` 等のフィールドと値の typo を config 書き時点で検知できる。

## Why（採用理由）

### 完全統一しない（柔軟な優先順位を採用する）理由

- **YAML 強制ツール（CI / Dependabot）に逆らえない**：「全部 TS にする」は GitHub Actions で破綻する
- **ecosystem 慣習に逆らう価値が薄い**：Biome を `biome.json`（拡張子なし）にしても何も得ない。むしろ Biome の最新ドキュメント・サンプルとの齟齬が発生
- **形式の選択は「ツールに対する最適解」**：プロジェクトの一貫性のために妥協する価値が薄い

### 自由選択時に TS を最優先する理由

- 本リポジトリは TS 主体で、設定だけ JS / JSON にする一貫性の損失を避ける
- ツールが型を export している＝**作者が TS 利用を想定して保守している**証拠で、型の正確性が信頼できる
- typo を実行時に発見すると CI 失敗で気付くが、保存時に弾けば書き終える前に修正できる
- 補完候補（union 型のリテラル値）が出ることで設定書き手の認知負荷が下がる

### JSONC を 2 番目にする理由

- データ純度が高く、「設定はデータ」の思想と整合
- `$schema` で IDE 補完が成立すれば、TS と同等の DX を得られる場面もある
- TS が使えない場合の最良の選択肢

### YAML を最低優先にする理由

- インデント事故・クォート事故の経験則
- 型安全がゼロで、IDE 補完も YAML language server に依存
- 強制される場合の代替手段がない時のみ採用

## Alternatives Considered（検討した代替案）

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| A. 完全統一（全部 TS） | プロジェクト全 config を TS で揃える | YAML 強制ツール（CI / Dependabot）で破綻。Biome / Turborepo の ecosystem 慣習にも逆らうことになる |
| B. 完全統一（全部 JSONC） | プロジェクト全 config を JSONC で揃える | YAML 強制ツールで破綻。型安全のメリットを捨てる |
| C. 個別判断・規範なし | ファイルごとに最適解を選び、統一規範は設けない | 将来追加するツールごとに「TS / JSONC / YAML どれにする？」の議論が再発、判断ぶれが累積 |
| D. **自由選択時の優先順位だけ統一（採用）** | 強制 / 慣習があればそれに従い、自由選択時のみ TS > JSONC > YAML の優先順を適用 | ツールへの最適化と判断軸の統一を両立 |

## Consequences（結果・トレードオフ）

### 得られるもの

- **将来ツール追加時の判断コスト削減**：「TS / JSONC / YAML どれ？」の議論が初動で終わる
- **設定ファイル全体の選択ロジックが説明可能**：新規メンバー・LLM が「なぜこの形式？」と問われたら本 ADR を参照できる
- **TS 化できる config は型安全の恩恵を受ける**：`commitlint.config.ts` で `UserConfig` 型を活用、本 PR で実適用
- **強制 / 慣習を尊重**：GitHub Actions / Biome / Turborepo 等のドキュメント・サンプルとの整合が保たれる

### 失うもの・受容するリスク

- **TS 化に伴う TS loader への間接依存**：cosmiconfig 経由の TS loader（`tsx` / `jiti` 等）が間に入る。loader 側のバグ・互換性問題に間接的に影響を受ける
- **ツールが将来型 export をやめた場合の追従**：TS で書いた config が型推論できなくなる可能性。実務上はまれ
- **既存 `.mjs` などの形式を即時に置き換える義務はない**：本方針は「強制」ではなく「自由選択時の指針」。既に動作している MJS / JSON 等を機械的に書き換える必要はなく、ツール置き換えや大幅修正のタイミングで適用する

### 将来の見直しトリガー

- **新しい設定ファイル形式が普及した場合**（例：TOML が広く使われるようになった等）
- **TS loader の標準化**：cosmiconfig 等が TS をデフォルトでネイティブサポートするようになった場合、判断はさらに TS 寄りに
- **YAML を強制するツールが減った場合**：強制比率が下がれば、自由選択優先順位の YAML の位置はさらに下がる
- **追加ツール（Knip / Vitest 等）の導入時に本方針が機能するか検証**：方針通りに選べない事例が複数出たら、フローチャートを再検討
- **TypeScript が `tsconfig.jsonc` を auto-discovery 対象に追加した場合**：拡張子で実態を表現できるようになるので、リネーム検討の余地が出る（上記「例外ファイル」セクションを更新）

## References

- [.claude/CLAUDE.md](../../.claude/CLAUDE.md)：本方針の運用ガイド（簡潔版）
- [docs/requirements/2-foundation/06-dev-workflow.md](../requirements/2-foundation/06-dev-workflow.md)：開発フロー・品質保証技術の俯瞰
- [ADR 0018: Biome を採用](./0018-biome-for-tooling.md)：JSONC を採用した先例
- [ADR 0021: 補完ツールを R0 から導入](./0021-r0-tooling-discipline.md)：個別ツール導入の方針
- `commitlint.config.ts`：本 ADR の方針が適用された具体例（本 PR で `.mjs` から変換）
