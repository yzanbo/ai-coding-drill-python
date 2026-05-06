# 0028. 設定ファイル形式の選定方針（TS > JSONC > YAML の優先順位）

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

> ※ 上記テーブルは**本 ADR を起票した時点のスナップショット**である。本 ADR の Decision「即時適用」により、本 PR で `commitlint.config.mjs` は `commitlint.config.ts` に変換され、ADR 0028 の方針が第 1 例として実適用される。詳細は後述の「本 ADR の即時適用」を参照。

ツール側の制約は 3 種類に分けられる：

1. **強制**：その形式しか受け付けない（GitHub Actions / Dependabot / pnpm-workspace）
2. **ecosystem 慣習**：複数受け付けるが公式 / 大多数のユーザが特定形式を使う（Biome の `.jsonc` / Turborepo の `.jsonc` / TypeScript の `tsconfig.json`）
3. **自由選択**：複数形式を等しく受け付け、ユーザに判断が委ねられる（commitlint / syncpack / Vitest 等）

**自由選択のケースで判断軸が明確でないと、人 / LLM ごとに選択が揺れて統一感が損なわれる**。実際、本 ADR の検討中に「commitlint を `.mjs` のまま残すか `.ts` に揃えるか」「syncpack を `.json` / `.cjs` / `.ts` のどれにするか」といった議論が個別に発生した。同じ議論を将来 Knip / Vitest / 他ツール導入時に再発させないため、判断軸を方針として文書化する。

## Decision（決定内容）

### 前提原則：設定ファイルには「なぜ」をインラインコメントで残す

設定ファイルは**規約の SSoT**であり、ルールごとに「なぜこのルールがあるか」をインラインコメントで残すことを基本姿勢とする：

- 「`policy: "sameRange"` を選んだ理由」「`semver` 範囲指定子を `^` 統一する根拠」「特定パッケージを除外する経緯」等を、設定値の隣に書く
- この情報を別ドキュメントに切り出すと SSoT が分裂し、設定変更時にドキュメント側が陳腐化する事故が発生する
- 機械（CI / lint）と人間（レビュアー・LLM）の両方が同じファイルから「設定値」と「設定意図」を読み取れる状態を保つ

この前提から、**コメントを書ける形式を、書けない形式より常に優先する**：

- 純 JSON（コメント書けない）は、JSONC / TS / YAML が同等の選択肢として存在する限り採用しない
- ツール側が JSON しか受け付けないなら、純 JSON で書く（妥協）。ただしその場合は別途 README 等で意図を補完する
- 後述の優先順位（TS > JSONC > YAML）は、すべて**コメントが書ける形式**の中での順序

### 1. ツール強制があればそれに従う

該当ツールが特定形式しか受け付けない場合、形式を選ぶ余地はない：

- GitHub Actions → YAML
- Dependabot → YAML
- pnpm workspace → YAML

### 2. ツール ecosystem 慣習が確立されていればそれに従う

ツールが複数形式を受け付けても、公式 / 大多数のユーザが特定形式を使っている場合はそれに従う。逆らうとドキュメント・StackOverflow 検索・コミュニティ知見との齟齬が発生する：

- Biome → `biome.jsonc`
- Turborepo → `turbo.jsonc`
- TypeScript → `tsconfig.json`（実態は JSONC、後述の例外リスト参照）

#### 拡張子と実態が一致しない例外ファイル

「拡張子は `.json` だが、対応ツールが JSONC として解釈する」ファイルが ecosystem 慣習として存在する。**新規メンバー / LLM が「`.json` だからコメント書けない」と誤認しないよう、リストとして明示する**：

| ファイル | 解釈 | 読むツール | 改名可能性 |
|---|---|---|---|
| `tsconfig.json` | **JSONC**（コメント可） | TypeScript コンパイラ | ❌ 不可（tsc の自動探索が固定名を要求） |
| `.vscode/settings.json` | **JSONC**（コメント可） | VSCode | ❌ 不可（VSCode が固定名を要求） |
| `.vscode/launch.json` | **JSONC**（コメント可） | VSCode | ❌ 不可 |
| `.vscode/tasks.json` | **JSONC**（コメント可） | VSCode | ❌ 不可 |
| `package.json` | **strict JSON**（コメント不可） | npm / pnpm / Node.js | ❌ 不可（標準 `JSON.parse()` で解釈） |
| `package-lock.json` | **strict JSON**（コメント不可） | npm | ❌ 不可（自動生成） |

**運用上の注意**：

- `tsconfig.json` 等の「JSONC として解釈される `.json` ファイル」を編集する際は、**ファイル冒頭に「このファイルは JSONC として扱われる」旨のコメント**を残し、混乱を防ぐ
- `package.json` のように「`.json` 拡張子で実際にもコメント不可」なファイルとは挙動が真逆なので、混同を防ぐ意味でも明記が重要
- VSCode は内部的にファイル名で言語モード（"JSON" vs "JSON with Comments"）を切り替えており、上記のテーブルはその挙動と一致している

#### `tsconfig.json` を `tsconfig.jsonc` にリネームしない理由

「拡張子で実態を表現したい」という発想は健全だが、`tsconfig.json` のリネームは**ツールチェーン全体を破壊する**：

- `tsc` 引数なし起動時の自動探索が `tsconfig.json` を期待
- VSCode / IntelliJ / Vim 等のエディタ統合が固定名を期待
- 周辺ツール（Vite / webpack / Biome / ESLint / Vitest 等）が `tsconfig.json` を直接読む
- `--project` 等の明示パス指定で動作はするが、設定箇所が爆発的に増える

ecosystem 慣習に逆らう労力 vs 拡張子変更の利点を比較すると、明らかに後者が小さい。Decision 2 の原則通り、ecosystem 慣習に従って `tsconfig.json` 名を維持する。

### 3. 自由選択時の優先順位

ツール強制も ecosystem 慣習も無い場合、以下の優先順で選ぶ：

#### 3-1. **TS（`.ts`）** — ツールが型を公式 export している場合

条件：
- ツールが `RcFile` / `UserConfig` / `defineConfig` 等の型・ヘルパーを公式 export
- syncpack / commitlint（`@commitlint/types` の `UserConfig`）/ Vitest / tsup / Vite 等が該当
- 設定値に union 型 / enum / 文字列リテラル型がある（typo しやすい）

選ぶ理由：
- フィールド名・リテラル値の typo を**保存時に IDE / `tsc` が即時に弾く**
- エディタ補完で候補（`policy: "sameRange" | "sameRangePinned" | ...` 等）が出る
- 本リポジトリは TypeScript 主体（`apps/` / `packages/`）で開発体験が一貫

#### 3-2. **JSONC（`.jsonc` または `.json` で JSONC 解釈されるもの）**

条件：
- 設定がほぼ純データ（ロジック・条件分岐不要）
- ツールが JSONC を native でサポート（`//` コメントを許容する）
- ツールが `$schema` を提供している（IDE 補完が効く）

選ぶ理由：
- データ純度が最高（コードでなくデータ）
- VCS diff が構造的に読める
- ロード速度が最速
- VS Code が `.jsonc` を native 認識

#### 3-3. **JS 系（`.mjs` / `.cjs` / `.js`）** — TS が使えず JSONC も合わない場合の妥協

条件：
- ツールが TS をサポートしない（型を export していない / `.ts` config を読めない）
- かつ JSONC で表現できない（条件分岐 / 環境変数参照 / 動的計算が必要）

選ぶ理由：
- コメントが書ける（前提原則を満たす）
- ロジックが書ける（環境変数から値を導出する等の数少ないユースケース）
- ツールサポートは `.ts` より広い

優先順序（JS 系内部）：
- `.mjs`（ESM）：現代的、`export default` が直接書ける、Node.js の ESM ネイティブ
- `.cjs`（CommonJS）：`module.exports = {...}` 形式、ESM 環境でない場合 / loader が ESM 未対応の場合の選択
- `.js`：拡張子だけでは ESM/CJS 不明（package.json の `"type"` に依存）。曖昧さがあるため**`.mjs` または `.cjs` を明示的に使う**

選ばない理由（TS / JSONC との比較）：
- 型安全がゼロ
- 「設定なのにコード」という違和感（実態としてオブジェクトリテラルしか書かないことが多い）

#### 3-4. **YAML（`.yaml` / `.yml`）** — ツール強制 / 慣習以外で選ぶ理由は無い

選ばない理由：
- インデント事故が発生しやすい（タブ vs スペース）
- 特殊文字を含む文字列のクォート要否が直感に反する（`workspace:*` は要クォート等）
- 型安全がゼロ
- TS / JSONC / JS で書ける場合に YAML を選ぶメリットが薄い

#### 3-5. **JSON（純 `.json`）** — 他形式が一切採れない場合のみ

選ばない理由：
- **コメントが書けない**（前提原則「設定ファイルに『なぜ』をインラインコメントで残す」と矛盾）
- ツールが純 JSON しか受け付けない場合に限り、妥協で採用する。その場合は別途 README / ADR で意図を補完する

### 適用ガイド（フローチャート）

```
新しいツールを導入する／既存ツールの形式を見直す
  │
  ├─ ツールが特定形式を強制？ → その形式を使う（終了）
  │
  ├─ ツール ecosystem 慣習が確立？ → それに従う（終了）
  │
  └─ 自由選択（複数形式を等しく受容）
        │
        ├─ ツールが TS 型を export＆設定値に typo しやすいリテラルあり？ → TS（.ts）
        │
        ├─ 純データ＆JSONC を native 受容＆$schema あり？ → JSONC（.jsonc）
        │
        ├─ ロジック必要 or JSONC 受容なし？ → JS 系（.mjs ＞ .cjs ＞ .js）
        │
        ├─ ツール強制で YAML？ → YAML（.yaml）
        │
        └─ どれも該当しない（純 JSON しか受けない）？ → JSON（妥協、README で意図補完）
```

**前提原則の再確認**：上記すべての分岐は「設定ファイルにコメントで『なぜ』を残せる」を最低ラインとして扱う。コメントが書けない**純 JSON は最終手段**で、ツールが他形式を受容しない場合のみ選ぶ。

### 本 ADR の即時適用：`commitlint.config.mjs` → `commitlint.config.ts`

本方針の適用第 1 例として、`commitlint.config.mjs` を `commitlint.config.ts` に変換する。`@commitlint/types` の `UserConfig` 型を import することで、`type-enum` / `scope-enum` / `level` 等のフィールドと値の typo を config 書き時点で検知できるようになる。

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
- [ADR 0013: Biome を採用](./0013-biome-for-tooling.md)：JSONC を採用した先例
- [ADR 0018: 補完ツールを R0 から導入](./0018-phase-0-tooling-discipline.md)：個別ツール導入の方針
- `commitlint.config.ts`：本 ADR の方針が適用された具体例（本 PR で `.mjs` から変換）
