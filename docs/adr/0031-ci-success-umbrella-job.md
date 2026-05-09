# 0031. CI Required status checks を集約ジョブ `ci-success` で 1 本化し main マージ時に強制

- **Status**: Accepted
- **Date**: 2026-05-06
- **Decision-makers**: 神保 陽平

## Context（背景・課題）

「CI green でないと PR マージ不可」を機械強制したい。背景には独立した 2 つの課題がある。

### 課題 1：Required status checks のメンテ運用負荷

GitHub の保護機能（Repository ruleset）には Required status checks 設定があり、登録したチェックが全部 success にならないと PR マージボタンが押せなくなる。ただし：

- 何も設定していないリポジトリでは、CI が赤でも・実行中でも・未実行でもマージは技術的に可能（status check は情報表示でしかない）
- Required に登録するチェック名は **GitHub Actions のジョブ名（`name:` フィールド）と完全一致**が必要
- ジョブを追加・改名・削除するたびに、Ruleset 側のチェック名リストを更新しないと「保護が緩む」「マージが永遠に通らなくなる」のいずれかの事故が起きる

R0 時点で CI ジョブは `commitlint` / `Biome` / `typecheck` / `syncpack`（ADR 0024）の 4 本があり、今後 R1 以降で `test` / `build` / `e2e` / `security-scan` 等が増えていく見込み（ADR 0026）。**ジョブ追加のたびに GitHub UI 側の Ruleset 編集を求める運用は、漏れる**。

### 課題 2：スタック PR 時の「責任シフト」リスク（受容判断）

main 限定で CI green を強制すると、以下の事故が起きうる：

```
main
 └── feature1 ──── PR ──> main      （A さん担当）
       └── feature2 ── PR ──> feature1   （B さん担当）
```

- B さんが feature2 → feature1 を「CI 赤のまま」マージ（中継ブランチには CI 強制が無いため通る）
- 後日、A さんが feature1 → main を PR 化 → CI 赤で main マージ不可
- A さんが**他人（B さん）のバグ**を解読して直す羽目になる

理屈上は「全ブランチへのマージで CI green を要求」すれば責任の局所化は完璧になるが、後述の **GitHub Ruleset 仕様の制約**（課題 3）により、これは実装上不可能と判明した。本 ADR ではこのリスクを**人間的規律で対処（PR レビュー時に base ブランチの CI 状態を確認）**する判断とする。

### 課題 3：GitHub Ruleset の評価タイミング制約

GitHub の Repository ruleset における `required_status_checks` rule は、**PR マージ時だけでなく直接 push 時にも発動する**。「ref を更新する全イベント」で評価される仕様で、「PR マージのみで評価」というモードは存在しない。

このため、`~ALL` ブランチを target に `required_status_checks` を設定すると、feature ブランチへの直接 push が以下のチキン＆エッグで一切通らなくなる：

1. `git push` → サーバーが新 commit SHA を受信
2. ルールセット評価：「commit SHA に対する `ci-success` 結果は？」→ 未登録（CI 未実行のため）
3. push 拒否（ref 更新せず）
4. CI を起動する `workflow_run` イベントが発火しない
5. → 永久に push できない

WIP commit のバックアップ push、ローカルにしかない作業のリモート同期、stacked PR 開発のいずれも実質不可能になる。実証済み（PR #16 制定中の 6800792 commit が require-ci-pass による `~ALL` 適用で実際に拒否された）。

## Decision（決定内容）

**CI ジョブを集約する umbrella ジョブ `ci-success` を `.github/workflows/ci.yml` に追加し、GitHub Ruleset `protect-main` の Required status checks には `ci-success` 1 つだけを登録する。** 新規 CI ジョブは `ci-success.needs` への 1 行追加で自動的に Required の網に組み込まれる。

**運用詳細（`ci-success` の YAML 構造 / `protect-main` Ruleset 構造 / CI ジョブ追加時の手順 / ルールセット非分離方針）の SSoT は [06-dev-workflow.md: CI 集約ジョブ（ci-success umbrella）パターン](../requirements/2-foundation/06-dev-workflow.md#ci-集約ジョブci-success-umbrellaパターン) を参照**（運用ルール型 ADR、→ [`.claude/rules/docs-rules.md` §2](../../.claude/rules/docs-rules.md)）。設定実体の SSoT は [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) と GitHub Ruleset `protect-main`。本 ADR は採用根拠（§Why）と代替案（§Alternatives Considered）を扱う。

## Why（採用理由）

### 集約ジョブ `ci-success` 採用の理由

- **メンテ単一点**：CI 構成変更が ci.yml 内で完結する。Ruleset（GitHub UI）の更新が不要なので「Ruleset 編集権限を持たないコントリビュータの PR でも、新ジョブが Required の網にちゃんと組み込まれる」状態を維持できる
- **改名耐性**：ジョブ名を変更しても Ruleset 側の status check 名（`ci-success`）は不変
- **skipped 罠の回避**：GitHub Actions では `needs:` のいずれかが失敗すると、後続ジョブはデフォルトで `skipped` になる。`if: always()` を付けないと `ci-success` 自体が skipped → Ruleset 上「未完了」扱いとなり、PR がブロック解除されない／逆に skipped を success と誤認する設定だと素通りする。`always()` で必ず起動させ、結果を明示判定することで両方の事故を防ぐ
- **追加コストが小さい**：実体は 5〜10 秒で終わる結果集約ジョブ。Actions 分数換算で誤差レベル
- **OSS 標準パターン**：Kubernetes / Rust / Bazel など主要 OSS で広く使われている umbrella job / required-checks aggregator パターンと同じ

### main のみに CI 強制を限定した理由

- **チキン＆エッグの回避**（決定的）：GitHub Ruleset の `required_status_checks` rule は ref 更新時に評価されるため、`~ALL` 適用すると feature ブランチの直接 push が永久にブロックされる（課題 3）。実装上、main 限定以外の選択肢が現実的に存在しない
- **main が最終ゲートとして機能十分**：このプロジェクトの全コードは最終的に main にマージされるため、main マージ時点で CI green が要求されれば「壊れたコードが main に入らない」という最重要要件は満たされる
- **feature ブランチの開発自由度を保つ**：WIP commit のバックアップ push、stacked PR 中継ブランチ運用、ローカル作業のリモート同期がいずれも従来通り可能

### スタック PR の責任シフト問題は人間的規律で対処する判断

理論上は `~ALL` 対象で CI 強制すれば責任の局所化が完璧になるが、上記の通り実装不能。代替として：

- PR レビュー時に base ブランチの CI 状態を確認することを慣行化
- スタック PR で base 側に CI エラーが残っている場合は、まず base 側を直してから head の PR を出す運用とする
- 1 人運用の現状では責任シフト自体が発生しないため、当面は実害なし。複数人運用に移行する際に再検討する（後述の「将来の見直しトリガー」）

## Alternatives Considered（検討した代替案）

### 集約ジョブ vs 個別登録

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| A. ジョブ 1 つずつ Ruleset に直接登録 | `commitlint` / `Biome` / `typecheck` / `syncpack` を Ruleset に個別登録 | ジョブ追加・改名のたびに Ruleset 編集が必要。追従漏れで「Required から外れた状態」になる事故が起きやすい。Ruleset 編集権限と CI 編集権限が分離している場合に致命的 |
| B. Required を設定しない（GitHub デフォルト） | CI 失敗してもマージ可能にする | 「CI green でないとマージ不可」という今回の要求を満たさない |
| C. `ci-success` を実体再実行型にする（`pnpm lint` 等を再度走らせる） | 集約ジョブで lint/typecheck/test を再実行 | CI 時間が約 2 倍になる。本来不要な重複実行 |
| D. ワークフロー単位で Required（`Require workflows to pass`） | Ruleset の別機能でワークフローファイル丸ごと Required 指定 | 実体は内部のジョブ単位で評価されるため、結局 umbrella job が必要。組み合わせる前提なら単独採用の意味は薄い |

### 適用範囲（target）

| 候補 | 概要 | 採用 / 不採用 |
|---|---|---|
| **E. main のみ（`~DEFAULT_BRANCH`）に CI 強制** | `protect-main` に `required_status_checks` を追加 | **採用**。チキン＆エッグ問題（課題 3）を回避できる唯一の現実解 |
| F. `~ALL` ブランチに CI 強制 | 全ブランチへの ref 更新で `ci-success` 緑必須 | **不採用**。GitHub Ruleset の評価タイミング仕様により、feature ブランチへの直接 push 全般が永続ブロックされる。実証済み（課題 3 の事例） |
| G. `~ALL` + admin bypass `always` | F と同じだが admin (1 人運用なら自分) を bypass_actors に always で追加し回避 | **不採用**。1 人運用では bypass が「実質全 push 素通り」となりルールが装飾化する。複数人運用想定では検討余地あり |
| H. `~ALL` + `pull_request` rule | 全ブランチで直接 push を禁止し PR 経由を強制 | **不採用**。feature ブランチでの WIP 直接 push が一切できなくなり、stacked 開発を含む全フローが破綻する |

### ルールセット分離 vs 単一化

| 候補 | 概要 | 採用 / 不採用 |
|---|---|---|
| **I. `protect-main` 1 ルールセットに統合** | main 保護に関する全ルール（削除禁止 / force-push 禁止 / PR 必須 / CI 緑必須）を 1 つにまとめる | **採用**。target がいずれも `~DEFAULT_BRANCH` に収束したため分離の意味がない |
| J. `protect-main`（構造的縛り）と `require-ci-pass`（CI 縛り）に分離 | 機能カテゴリ別にルールセットを分ける | **不採用**。target が同じになる以上、視認性が下がるだけで利点なし。「片方を ~ALL にしたい場合に分離が活きる」という当初の動機が消失したため |

## Consequences（結果・トレードオフ）

### 得られるもの

- CI ジョブ追加時の運用負荷が「ci.yml の `needs:` に 1 行追加」だけになる
- ジョブ名のリネームでも Ruleset 不変
- skipped / cancelled / failure のいずれも一律「失敗」として扱う厳格な判定
- `concurrency: cancel-in-progress: true` でキャンセルされた古い run も `skipped` 経由で正しく失敗扱いになる
- main マージ時点で CI green が機械強制される（最重要要件）
- feature ブランチでの WIP 直接 push / stacked PR 開発の自由度を維持

### 失うもの・受容するリスク

- **`needs:` への追加忘れリスク**：新ジョブを足したのに `ci-success.needs` への追加を忘れると、そのジョブは「失敗してもマージ可能」のまま。CI ファイル変更時の PR レビューポイントとして意識する必要がある
- **GitHub Actions の `needs.*.result` 仕様への依存**：将来 GitHub 側がこの式評価を変える可能性は理論上あるが、長年安定している API なので低リスク
- **本 ADR の効果は Ruleset 設定とセットでのみ発現**：このファイルを置いただけでは強制されない。**`protect-main` ルールセットの `required_status_checks` rule に `ci-success` を登録する作業が必要**
- **スタック PR の責任シフトリスク**：中継ブランチ（feature1 等）への PR マージで CI 強制が効かないため、B さんの CI 赤を A さんが直す事故が理論上起こりうる。1 人運用の現状では発生しないため許容。複数人運用移行時は PR レビュー慣行で対処
- **CI ファイル自体が壊れた場合の救出経路**：`.github/workflows/ci.yml` に YAML 構文エラー等が混入してワークフローが起動できなくなると、`ci-success` チェックが登録されないまま `protect-main` の Required status checks が「未完了」と判定し、PR が永久にマージ不能になる。復旧には Ruleset の一時無効化または admin bypass の追加が必要。CI ファイル変更時は構文を慎重に確認する

### 将来の見直しトリガー

- GitHub が「すべての status check を自動で Required にする」ネイティブ機能を提供したら集約ジョブ設計は不要になる
- GitHub Actions がワークフロー単位での厳密な aggregate 判定機能（skipped を失敗扱いにする組み込みオプション等）を追加した場合は、umbrella job ではなくその機能に乗り換える
- GitHub Ruleset に「PR マージ時のみ評価」モードが追加された場合、`~ALL` 対象で CI 強制を再検討する（責任の局所化を完璧にするため）
- 複数人運用に移行する場合、スタック PR の責任シフト問題が顕在化するため、CODEOWNERS / PR レビュー必須化等の追加対策を検討する

## References

- [PR #16 - ci-success 集約ジョブ追加](https://github.com/yzanbo/ai-coding-drill/pull/16)
- [ADR 0026 - GitHub Actions のスコープを段階的に拡張](./0026-github-actions-incremental-scope.md)
- [ADR 0025 - CI/CD ツールに GitHub Actions を採用](./0025-github-actions-as-ci-cd.md)
- [GitHub Docs - About rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets)
- [GitHub Docs - Available rules for rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets#require-status-checks-to-pass-before-merging)
- [GitHub Actions - Defining outputs and conditionals with `needs.*.result`](https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions#jobsjob_idneedsresult)
