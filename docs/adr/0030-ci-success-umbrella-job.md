# 0030. CI Required status checks を集約ジョブ `ci-success` で 1 本化し全ブランチに適用

- **Status**: Accepted
- **Date**: 2026-05-06
- **Decision-makers**: yzanbo

## Context（背景・課題）

「CI green でないと PR マージ不可」を機械強制したい。背景には独立した 2 つの課題がある。

### 課題 1：Required status checks のメンテ運用負荷

GitHub の保護機能（Repository ruleset）には Required status checks 設定があり、登録したチェックが全部 success にならないと PR マージボタンが押せなくなる。ただし：

- 何も設定していないリポジトリでは、CI が赤でも・実行中でも・未実行でもマージは技術的に可能（status check は情報表示でしかない）
- Required に登録するチェック名は **GitHub Actions のジョブ名（`name:` フィールド）と完全一致**が必要
- ジョブを追加・改名・削除するたびに、Ruleset 側のチェック名リストを更新しないと「保護が緩む」「マージが永遠に通らなくなる」のいずれかの事故が起きる

R0 時点で CI ジョブは `commitlint` / `Biome` / `typecheck` / `syncpack`（ADR 0029）の 4 本があり、今後 R1 以降で `test` / `build` / `e2e` / `security-scan` 等が増えていく見込み（ADR 0022）。**ジョブ追加のたびに GitHub UI 側の Ruleset 編集を求める運用は、漏れる**。

### 課題 2：スタック PR 時の「責任シフト」

main 限定で CI green を強制すると、以下の事故が起きる：

```
main
 └── feature1 ──── PR ──> main      （A さん担当）
       └── feature2 ── PR ──> feature1   （B さん担当）
```

- B さんが feature2 → feature1 を「CI 赤のまま」マージ（中継ブランチには CI 強制が無いため通る）
- 後日、A さんが feature1 → main を PR 化 → CI 赤で main マージ不可
- A さんが**他人（B さん）のバグ**を解読して直す羽目になる

これは「PR を出した本人が CI を直す」という責任の局所性を破壊し、規律を緩める強いディスインセンティブとなる。**main だけでなく全ブランチへのマージで CI green を要求**することで、原因と修正コストの責任主体を一致させる必要がある。

## Decision（決定内容）

以下 2 つを組み合わせて決定する。

### 1. CI 側：集約ジョブ `ci-success` の導入

`.github/workflows/ci.yml` に集約ジョブ `ci-success` を追加し、Ruleset の Required status checks には **`ci-success` 1 つだけ**を登録する。

`ci-success` は実体ジョブを再実行せず、`needs.*.result` を `if: always()` で評価して、いずれかが `failure` / `cancelled` / `skipped` を含めば `exit 1` する。

```yaml
ci-success:
  name: ci-success
  if: always()
  needs: [commitlint, lint, typecheck, syncpack]
  runs-on: ubuntu-latest
  steps:
    - run: |
        if [[ "${{ contains(needs.*.result, 'failure') }}" == "true" ]] \
           || [[ "${{ contains(needs.*.result, 'cancelled') }}" == "true" ]] \
           || [[ "${{ contains(needs.*.result, 'skipped') }}" == "true" ]]; then
          echo "::error::One or more required jobs did not succeed"
          exit 1
        fi
```

新規ジョブ追加時は `ci-success.needs` に 1 行追加するだけで、自動的に Required の網に組み込まれる。Ruleset 側は不変。

### 2. Ruleset 側：`~ALL` ブランチへの適用と責任分離

ルールセットを 2 つに分離して責任範囲を明確にする：

| ルールセット | target | 責任範囲 |
|---|---|---|
| `protect-main`（既存） | `~DEFAULT_BRANCH` | main 固有：直接 push / 削除 / force-push の禁止 |
| `require-ci-pass`（新設） | `~ALL` | 全ブランチ共通：マージ・更新時に `ci-success` 緑強制 |

`require-ci-pass` の中身：

```
target: ~ALL
rules:
  - required_status_checks
      required_status_checks: [{ context: "ci-success" }]
      strict_required_status_checks_policy: false
bypass_actors: なし
enforcement: active
```

これにより：

- 任意のブランチに対する PR マージで `ci-success` 緑が必須となる
- 中継ブランチ（feature1 等）への PR マージでも CI 強制が効くため、責任の局所化が崩れない
- 直接 push についても `ci-success` 緑が要求されるが、これは「赤い commit を共有ブランチに置かない」という規律として歓迎すべき挙動
- `protect-main` は触らないため、main 固有の縛り（直接 push 禁止等）はそのまま維持される

## Why（採用理由）

### 集約ジョブ `ci-success` 採用の理由

- **メンテ単一点**：CI 構成変更が ci.yml 内で完結する。Ruleset（GitHub UI）の更新が不要なので「Ruleset 編集権限を持たないコントリビュータの PR でも、新ジョブが Required の網にちゃんと組み込まれる」状態を維持できる
- **改名耐性**：ジョブ名を変更しても Ruleset 側の status check 名（`ci-success`）は不変
- **skipped 罠の回避**：GitHub Actions では `needs:` のいずれかが失敗すると、後続ジョブはデフォルトで `skipped` になる。`if: always()` を付けないと `ci-success` 自体が skipped → Ruleset 上「未完了」扱いとなり、PR がブロック解除されない／逆に skipped を success と誤認する設定だと素通りする。`always()` で必ず起動させ、結果を明示判定することで両方の事故を防ぐ
- **追加コストが小さい**：実体は 5〜10 秒で終わる結果集約ジョブ。Actions 分数換算で誤差レベル
- **OSS 標準パターン**：Kubernetes / Rust / Bazel など主要 OSS で広く使われている umbrella job / required-checks aggregator パターンと同じ

### `~ALL` 対象＋ルールセット分離の理由

- **責任の局所化**：スタック PR で「他人のバグを別の人が直す」事故を防ぐ。CI を壊した PR は、その PR のマージ時点で必ず弾かれるため、原因者が修正する以外の選択肢がなくなる
- **規律の一貫性**：「ci 赤の commit を共有ブランチに置かない」運用が機械強制される。main / feature1 / feature2 のいずれにおいても同じ規律が適用される
- **ルールセット責任分離**：「main 固有の縛り」と「全ブランチ共通の CI 縛り」を別ルールに分けることで、片方の変更がもう片方に影響しない。例えば後日「main の PR で approvals: 1 を要求」へ変更する際、`protect-main` だけ触れば済む

## Alternatives Considered（検討した代替案）

### 集約ジョブ vs 個別登録

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| A. ジョブ 1 つずつ Ruleset に直接登録 | `commitlint` / `Biome` / `typecheck` / `syncpack` を Ruleset に個別登録 | ジョブ追加・改名のたびに Ruleset 編集が必要。追従漏れで「Required から外れた状態」になる事故が起きやすい。Ruleset 編集権限と CI 編集権限が分離している場合に致命的 |
| B. Required を設定しない（GitHub デフォルト） | CI 失敗してもマージ可能にする | 「CI green でないとマージ不可」という今回の要求を満たさない |
| C. `ci-success` を実体再実行型にする（`pnpm lint` 等を再度走らせる） | 集約ジョブで lint/typecheck/test を再実行 | CI 時間が約 2 倍になる。本来不要な重複実行 |
| D. ワークフロー単位で Required（`Require workflows to pass`） | Ruleset の別機能でワークフローファイル丸ごと Required 指定 | 実体は内部のジョブ単位で評価されるため、結局 umbrella job が必要。組み合わせる前提なら単独採用の意味は薄い |

### 適用範囲（target）

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| E. main のみ（`~DEFAULT_BRANCH`）に CI 強制 | 既存 `protect-main` に `required_status_checks` を追加するだけで済ませる | スタック PR で「他人の CI 赤を引き継ぐ」責任シフト問題が残る。中継ブランチ（feature1 等）への PR マージで CI 強制が効かないため、原因者と修正者が分離する |
| F. PR 経由のみ全ブランチで強制（`~ALL` + `pull_request` rule） | 全ブランチで直接 push を禁止し PR 経由を強制 | feature ブランチでの WIP 直接 push が一切できなくなり、開発フロー全般を阻害する。1 人運用でも複数人運用でも非実用的 |

### ルールセット分離 vs 単一化

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| G. `protect-main` を拡張し全ルールを 1 本化 | 既存ルールセットを `~ALL` に target 拡張し、main 固有ルール（pull_request 等）と CI 強制を同居させる | main 固有の縛りと全ブランチ共通の縛りが混ざり、後の調整時に「どの target に何が効くか」を毎回読み解く負担が出る。ルールセットの責任範囲は単一目的に保つのが望ましい |

## Consequences（結果・トレードオフ）

### 得られるもの

- CI ジョブ追加時の運用負荷が「ci.yml の `needs:` に 1 行追加」だけになる
- ジョブ名のリネームでも Ruleset 不変
- skipped / cancelled / failure のいずれも一律「失敗」として扱う厳格な判定
- `concurrency: cancel-in-progress: true` でキャンセルされた古い run も `skipped` 経由で正しく失敗扱いになる
- スタック PR でも責任の局所化が崩れず、原因者と修正者が一致する
- `protect-main` と `require-ci-pass` のルールセット分離により、片方の変更が他方に影響しない

### 失うもの・受容するリスク

- **`needs:` への追加忘れリスク**：新ジョブを足したのに `ci-success.needs` への追加を忘れると、そのジョブは「失敗してもマージ可能」のまま。CI ファイル変更時の PR レビューポイントとして意識する必要がある
- **GitHub Actions の `needs.*.result` 仕様への依存**：将来 GitHub 側がこの式評価を変える可能性は理論上あるが、長年安定している API なので低リスク
- **本 ADR の効果は Ruleset 設定とセットでのみ発現**：このファイルを置いただけでは強制されない。**`require-ci-pass` ルールセットを `~ALL` 対象で別途作成し、`ci-success` を Required status checks に登録する作業が必要**
- **WIP 段階の直接 push でも CI 緑が要求される**：feature ブランチに WIP commit を push する際も `ci-success` を緑にしておく必要がある。これは「赤い commit を共有ブランチに置かない」という規律の機械強制であり、欠点ではなく意図的な挙動として受容する

### 将来の見直しトリガー

- GitHub が「すべての status check を自動で Required にする」ネイティブ機能を提供したら本 ADR は不要になる
- GitHub Actions がワークフロー単位での厳密な aggregate 判定機能（skipped を失敗扱いにする組み込みオプション等）を追加した場合は、umbrella job ではなくその機能に乗り換える

## References

- [PR #16 - ci-success 集約ジョブ追加](https://github.com/yzanbo/ai-coding-drill/pull/16)
- [ADR 0022 - GitHub Actions のスコープを段階的に拡張](./0022-github-actions-incremental-scope.md)
- [ADR 0023 - CI/CD ツールに GitHub Actions を採用](./0023-github-actions-as-ci-cd.md)
- [GitHub Docs - About protected branches / Require status checks](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches#require-status-checks-before-merging)
- [GitHub Actions - Defining outputs and conditionals with `needs.*.result`](https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions#jobsjob_idneedsresult)
