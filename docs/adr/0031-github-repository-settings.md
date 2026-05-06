# 0031. GitHub リポジトリ設定の方針

- **Status**: Accepted
- **Date**: 2026-05-06
- **Decision-makers**: yzanbo

## Context（背景・課題）

このリポジトリは public ポートフォリオとして運用される。GitHub UI / API には**リポジトリ全般の設定項目が散在**しており、デフォルト値のまま放置すると以下のリスクが残る：

- 壊れたコードが main にマージされる（CI 結果と無関係にマージ可能）
- 直接 push や force-push で履歴が破壊される
- マージ済みブランチが残り続ける（リポジトリの見通し悪化）
- 依存関係の脆弱性が見過ごされる
- `GITHUB_TOKEN` が過剰権限で動作する（最小権限原則違反）
- スタック PR でレビューが遅延した時に base が古いまま気付かない

**個別の決定は他 ADR で済んでいる項目もあるが、リポジトリ全体としての設定方針が一覧されておらず、棚卸しされていない**。本 ADR で「デフォルトから変更している項目すべて」と「敢えてデフォルトのままにしている項目」の判断根拠を 1 か所に集約する。

設定の現行値（What）は [07-github-settings.md](../requirements/2-foundation/07-github-settings.md) を参照。本 ADR は **Why** に集中する。

## Decision（決定内容）

GitHub リポジトリ設定を 5 つの領域で構成する。各設定の値（What）は [07-github-settings.md](../requirements/2-foundation/07-github-settings.md) を参照、選定理由は次節 [Why](#why採用理由) に集約する。

1. **ブランチ保護**：Repository ruleset `protect-main` を main 単独に適用。`deletion` / `non_fast_forward` / `pull_request` / `required_status_checks` の 4 ルール、bypass_actors は空。詳細仕様と判断経緯は [ADR 0030](./0030-ci-success-umbrella-job.md) に集約
2. **Pull Request / マージ動作**：3 種のマージ方式（merge / squash / rebase）すべて許可。auto-merge / Always suggest update / Auto delete head branches を有効化。DCO 署名強制（`web_commit_signoff_required`）は無効
3. **GitHub Actions**：`default_workflow_permissions: read`（最小権限）、サードパーティアクション利用は無制限許可（SHA ピン止めを慣習で担保）、Actions による PR approve は無効
4. **Security（Dependabot）**：alerts / security updates / version updates の 3 機能すべて有効、Private vulnerability reporting は無効
5. **Features**：Issues / Projects 有効、Wiki / Discussions 無効、Allow forking はデフォルト維持

## Why（採用理由）

### 全体方針

- **デフォルト値の責任を引き受ける**：GitHub のデフォルトはあらゆるユースケースに無難な妥協値であり、特定プロジェクトの最適とは限らない。**変更している項目を ADR に列挙し、変更していない項目も「敢えて変えていない」と棚卸しする**ことで、「気付いていなかった」事故を防ぐ
- **機械強制を最大化**：人間の規律に頼る前に、機械（Ruleset / required checks / Dependabot）に強制させる。1 人運用の現状でも自分の不注意から守る
- **オプトイン機能の有効化は害なし**：auto-merge / always-suggest-update のように「明示的に使った時だけ動く」機能は、有効化しても副作用がない。将来の運用幅を残す観点で ON

### 1. ブランチ保護

詳細は [ADR 0030](./0030-ci-success-umbrella-job.md) に集約。本 ADR の文脈では「main への直接 push / force-push / 削除 / CI 失敗マージのいずれも機械的に阻止される」状態が確立していることを確認するに留める。

### 2. Pull Request / マージ動作

- **3 種のマージ方式を全許可**：PR の性格（複数 commit / 単発 / リベース運用）に応じて使い分けたい。マージ方式を 1 つに絞ると、WIP commit を意味のある単位で残したい PR で対応できなくなる
- **Allow auto-merge を ON**：PR 単位で**明示的に有効化した PR のみ**自動マージされるオプトイン機能。デフォルトは何も自動化されないため害なし。Dependabot の小修正 PR を CI 通過後に放置で回せる将来運用を見越して有効化
- **Always suggest updating PR branches を ON**：base が更新されたら "Update branch" ボタンを PR ページに表示するだけの「気付きの機会増」。スタック PR で base 側の修正に追従し損ねる事故を減らす
- **Automatically delete head branches を ON**：マージ済み head ブランチを自動削除し、リポジトリのブランチ一覧の見通しを保つ。誤削除時は GitHub UI から復元可能（リスク低）
- **DCO 署名強制を OFF**：OSS 標準仕様だがポートフォリオ規模では運用負荷が割に合わない

### 3. GitHub Actions

- **`default_workflow_permissions: read`**：`GITHUB_TOKEN` の既定スコープを最小化。書き込みが必要なジョブだけ `permissions:` ブロックで明示拡張する方針（→ [.github/workflows/ci.yml](../../.github/workflows/ci.yml)）
- **`allowed_actions: all`**：サードパーティアクションの利用を許可しつつ、**SHA ピン止めで攻撃面を絞る**（→ [ADR 0026](./0026-github-actions-sha-pinning.md)）。許可リスト方式にすると Dependabot 自動 PR の運用が回らなくなる
- **`sha_pinning_required` のサーバー側強制を OFF**：サーバー側で機械強制すると Dependabot の自動 PR が SHA 形式チェックに引っかかって壊れる可能性がある。慣習を PR レビューで担保する方針
- **`can_approve_pull_request_reviews` を OFF**：GitHub Actions が PR を approve できないようにし、自動承認による迂回経路を塞ぐ

### 4. Security（Dependabot）

- **alerts / security updates をともに有効化**：public リポジトリで脆弱性を放置することはリスクとリピュテーションの両面で割に合わない。alerts は通知を出すだけ、security updates はそれに対する修正 PR を自動生成。両者は依存関係で、alerts なしでは security updates も動かない
- **version updates は ADR 0024 で導入済み**。本 ADR ではその前提で「3 機能の役割が直交していること」と「`.github/dependabot.yml` の `commit-message` / `labels` / `groups` / `ignore` が security updates にも継承されること」を再確認する
- **Private vulnerability reporting を OFF**：外部報告者から非公開で脆弱性報告を受ける窓口。ポートフォリオ規模では運用が回らない

### 5. Features

- **Wiki を無効化**：`docs/` 配下の Markdown でドキュメント一元化（SSoT 原則）。Wiki は PR レビュー対象外なので品質も担保できない
- **Discussions を無効化**：ポートフォリオ規模では Issues で十分、運用負荷だけ増える
- **Issues / Projects は有効**：フィードバックとタスク管理の窓口として残す
- **Allow forking はデフォルト維持**：public リポジトリでは Allow forking トグルが UI に表示されず暗黙に有効（private 限定の設定）。維持以外の選択肢なし

### 1 人運用前提との整合

- **Collaborator 0 人**：オーナー（yzanbo）のみ。個人リポジトリの Collaborator は Write 権限固定で、招待するとマージ可能者が増えるため、現状はオーナー専有
- **approvals: 0**：「他人」が存在しないため approval 必須化は機能しない（自分の PR は自分で approve できない GitHub 仕様）
- **bypass_actors 空**：自分を bypass に含めると保護が装飾化する。緊急時は Ruleset 一時無効化で対処
- 複数人運用に移行する際は本 ADR と [ADR 0030](./0030-ci-success-umbrella-job.md) の「将来の見直しトリガー」条項を参照

## Alternatives Considered（検討した代替案）

### Wiki と Discussions の扱い

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| A. Wiki を有効化してリポジトリ外ドキュメントを置く | GitHub Wiki にチュートリアル等を集約 | ドキュメントが `docs/` と Wiki に分散、SSoT 原則に反する。Wiki は PR レビューの対象外なので品質も担保できない |
| B. Discussions を有効化 | Issue と分離してフリーフォーマットの議論場を持つ | ポートフォリオ規模では Issue で十分、運用負荷だけ増える |

### Auto-merge

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| C. Auto-merge を OFF | 「使わない機能はオフ」の規律 | 明示有効化型（オプトイン）なので副作用なし、将来 Dependabot 自動マージ等で使う場面が出る |

### マージ方式の制限

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| D. Squash merge のみ許可 | 1 PR = 1 commit を main に強制し履歴を綺麗に保つ | WIP commit を意味のある単位で残したい PR で対応できない。本プロジェクトでは PR 単位の commit 設計を尊重するため 3 種許可 |
| E. Merge commit のみ許可 | 履歴を線形にせず全 PR commit を残す | 些末な fix-up commit が main 履歴を埋めるため可読性低下 |

### Vulnerability alerts / security updates

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| F. Dependabot version updates のみで脆弱性通知は無効 | 通知ノイズを避ける | 公開リポジトリでの脆弱性放置はリスクとリピュテーションの両面で割に合わない |

### Ruleset の bypass

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| G. admin（自分）を bypass_actors に always で追加 | 緊急時の自分救済経路を確保 | 1 人運用では「自分の bypass = 全員 bypass」となり保護が装飾化する。緊急時は Ruleset を一時無効化する明示的手段で対処 |

## Consequences（結果・トレードオフ）

### 得られるもの

- リポジトリ設定の現状（What）と理由（Why）が要件定義書 + ADR の 2 層で参照可能になる
- 設定項目の漏れ・退行に対するチェックリストが揃う
- 1 人運用 → 複数人運用移行時の見直し範囲が明確（本 ADR と [ADR 0030](./0030-ci-success-umbrella-job.md) の Alternatives / 見直しトリガー）
- 機械強制で守られる主要シナリオ：
  - main 直接 push 阻止（Ruleset `pull_request`）
  - main force-push 阻止（Ruleset `non_fast_forward`）
  - main 削除阻止（Ruleset `deletion`）
  - 壊れた CI のままマージ阻止（Ruleset `required_status_checks: ci-success`）
  - 脆弱性放置阻止（Dependabot alerts + security updates）
  - 過剰権限のジョブ実行阻止（`default_workflow_permissions: read`）

### 失うもの・受容するリスク

- **設定項目の追従責任**：GitHub の UI は予告なく項目名・配置が変わる。本 ADR と要件定義書の記述が古くなる可能性。**設定変更時は両方を同期更新する運用ルールが必要**（→ 要件定義書冒頭で SSoT 確認）
- **bypass を持たないことによる緊急時の対応コスト**：CI が壊れた場合、Ruleset を一時的に無効化する明示的操作が必要（admin 権限で UI から `enforcement: disabled` にトグル）
- **Dependabot security updates の `ignore` 継承**：`.github/dependabot.yml` の `ignore`（`semver-major` 除外）が security updates にも継承される。メジャー更新でしか直らない CVE が来た場合は手動対応が必要

### 将来の見直しトリガー

- **複数人運用への移行**：approvals: 0 を見直し、CODEOWNERS の導入と PR レビュー必須化を検討
- **Organization への移管**：Triage / Maintain 等の細かい権限ロールが使えるようになる
- **OSS リポジトリ化（外部コントリビューションを積極的に受ける運用）**：DCO 署名強制（`web_commit_signoff_required`）と Private vulnerability reporting の有効化を検討
- **Dependabot security updates の自動マージ運用導入**：auto-merge の本格活用、必要なら ADR を別途起票

## References

- [07-github-settings.md](../requirements/2-foundation/07-github-settings.md) — GitHub 設定の現行仕様（What）
- [ADR 0024: Dependabot 自動更新ポリシー](./0024-dependabot-auto-update-policy.md)
- [ADR 0025: コミット scope 規約](./0025-commit-scope-convention.md)
- [ADR 0026: GitHub Actions のサードパーティアクションを SHA でピン止め](./0026-github-actions-sha-pinning.md)
- [ADR 0030: ci-success umbrella job で Required status checks を 1 本化](./0030-ci-success-umbrella-job.md)
- [GitHub Docs - About rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets)
- [GitHub Docs - About Dependabot alerts](https://docs.github.com/en/code-security/dependabot/dependabot-alerts/about-dependabot-alerts)
- [GitHub Docs - Managing security and analysis settings](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-security-and-analysis-settings-for-your-repository)
