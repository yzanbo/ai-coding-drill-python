# 07. GitHub リポジトリ設定

> **このドキュメントの守備範囲**：GitHub リポジトリ側の設定（リポジトリ general / Pull Request 動作 / ブランチ保護 / Actions / Security / Features）の **現行仕様**（What）を一覧する。**選定理由**（Why）は [ADR 0031](../../adr/0031-github-repository-settings.md) を参照。
> **CI/CD のジョブ設計（lint / typecheck / test 等）**は [06-dev-workflow.md](./06-dev-workflow.md) を参照。
> **リポジトリの責務やコード構造**は [02-architecture.md](./02-architecture.md) を参照。

---

## 趣旨

ポートフォリオ用途の public リポジトリとして、**GitHub の UI / API でデフォルトから変更している項目**を一覧化し、設定の意図と現状を明示する。設定変更時は本ファイルと [ADR 0031](../../adr/0031-github-repository-settings.md) の両方を更新する。

`gh` で現行値を読み出すコマンド例は本ファイル末尾の [現状確認コマンド](#現状確認コマンド) を参照。

---

## リポジトリ基本

| 項目 | 値 | デフォルトとの差 |
|---|---|---|
| visibility | `public` | （個人でリポジトリ作成時の選択、変更ではない） |
| default_branch | `main` | デフォルト通り |
| description | "LLM-generated programming problems verified by sandboxed grading. Portfolio project." | 設定済み |
| topics | （未設定） | デフォルト通り（タグ未設定）。検索性向上のため `ai` / `typescript` / `nestjs` / `portfolio` 等の付与は将来検討 |
| Collaborators | `yzanbo`（オーナー）のみ | 招待なし（→ マージ可能者は実質オーナー専有） |

---

## Features（機能のオン/オフ）

| 機能 | 状態 | デフォルトとの差 |
|---|---|---|
| Issues | ✅ 有効 | デフォルト通り |
| Discussions | ❌ 無効 | デフォルト通り（無効） |
| Wiki | ❌ 無効 | **デフォルトから変更**（無効化） |
| Projects | ✅ 有効 | デフォルト通り |
| Allow forking | ✅ 有効 | public リポジトリでは UI トグルが表示されず暗黙に有効。private 時にのみ無効化可能 |

Wiki を無効にしているのは、ドキュメント一元化（`docs/` 配下のリポジトリ内 Markdown）方針のため。

---

## Pull Requests / マージ動作

| 項目 | 値 | デフォルトとの差 |
|---|---|---|
| Allow merge commit | ✅ ON | デフォルト通り |
| Allow squash merging | ✅ ON | デフォルト通り |
| Allow rebase merging | ✅ ON | デフォルト通り |
| **Allow auto-merge** | ✅ ON | **デフォルトから変更**（PR 単位で auto-merge を有効化できるようにする）|
| **Always suggest updating pull request branches** (`allow_update_branch`) | ✅ ON | **デフォルトから変更**（base 更新時に "Update branch" ボタンを表示） |
| **Automatically delete head branches** (`delete_branch_on_merge`) | ✅ ON | **デフォルトから変更**（マージ済み head ブランチを自動削除） |
| Squash merge commit title | `COMMIT_OR_PR_TITLE` | デフォルト |
| Squash merge commit message | `COMMIT_MESSAGES` | デフォルト |
| Merge commit title | `MERGE_MESSAGE` | デフォルト |
| Merge commit message | `PR_TITLE` | デフォルト |
| `web_commit_signoff_required` | ❌ OFF | デフォルト通り |

**運用方針**：

- Auto-merge は**有効化**しているが、**PR ごとに明示的に "Enable auto-merge" を押した PR だけ**が CI 完了後に自動マージされる。デフォルトでは何も自動化されない
- ブランチ自動削除は **GitHub のリモートブランチ**のみ対象。ローカル側は別途 `git fetch -p` + `git branch -D` で掃除する
- 3 種のマージ方式（merge / squash / rebase）すべてを許可しているのは、PR の性格に応じて使い分けるため

---

## ブランチ保護（Repository ruleset `protect-main`）

設計判断・代替案検討は [ADR 0030: ci-success umbrella job で Required status checks を 1 本化](../../adr/0030-ci-success-umbrella-job.md) を参照（リポジトリ全体の設定方針における位置付けは [ADR 0031](../../adr/0031-github-repository-settings.md)）。

| 項目 | 値 |
|---|---|
| name | `protect-main` |
| target | `~DEFAULT_BRANCH`（main のみ） |
| enforcement | `active` |
| bypass_actors | 空（admin も例外なし） |

ルール一覧：

| ルール | 役割 |
|---|---|
| `deletion` | main ブランチの削除を禁止 |
| `non_fast_forward` | main への force-push を禁止 |
| `pull_request` | main への直接 push を禁止し PR 経由を強制（approvals: 0、stale dismiss: on） |
| `required_status_checks` | `ci-success` チェックが緑でないと PR をマージできない |

詳細：

- `pull_request.required_approving_review_count`: 0（1 人運用前提のため）
- `pull_request.dismiss_stale_reviews_on_push`: true
- `pull_request.allowed_merge_methods`: `[merge, squash, rebase]`
- `required_status_checks.strict_required_status_checks_policy`: false（base の最新を取り込まずともマージ可能）
- `required_status_checks.required_status_checks`: `[{ context: "ci-success" }]`（→ ADR 0030）

---

## GitHub Actions

| 項目 | 値 | デフォルトとの差 |
|---|---|---|
| Actions enabled | ✅ true | デフォルト通り |
| `allowed_actions` | `all` | デフォルト通り（任意の action を使用可） |
| `sha_pinning_required`（サーバー側強制） | ❌ false | デフォルト通り。**SHA ピン止めは [ADR 0026](../../adr/0026-github-actions-sha-pinning.md) で慣習化、機械強制ではなく PR レビューで担保** |
| `default_workflow_permissions` | `read` | **デフォルトから変更**（最小権限の原則） |
| `can_approve_pull_request_reviews` | false | デフォルト通り |
| Self-hosted runners | 0 | デフォルト通り |

`default_workflow_permissions: read` は、`GITHUB_TOKEN` の既定スコープを最小化する重要設定。ジョブ単位で必要に応じ `permissions:` ブロックで拡張する方針（→ [.github/workflows/ci.yml](../../../.github/workflows/ci.yml)）。

---

## Security

| 機能 | 状態 | デフォルトとの差 |
|---|---|---|
| **Vulnerability alerts**（Dependabot alerts） | ✅ 有効 | **デフォルトから変更**（脆弱性発見時に通知） |
| **Dependabot security updates**（automated security fixes） | ✅ 有効 | **デフォルトから変更**（脆弱性に対する自動修正 PR） |
| Private vulnerability reporting | ❌ 無効 | デフォルト通り |
| Dependabot version updates | ✅ 有効 | `.github/dependabot.yml` で構成（→ [ADR 0024](../../adr/0024-dependabot-auto-update-policy.md)） |

3 種類の Dependabot 機能の役割整理：

| 機能 | 動作 |
|---|---|
| Dependabot alerts | 既知の脆弱性を Security タブで通知 |
| Dependabot security updates | アラート対象を修正版へ上げる PR を自動作成 |
| Dependabot version updates | 通常のバージョン更新 PR を定期作成（脆弱性とは独立） |

---

## 現状確認コマンド

設定値が文書と乖離していないか確認するためのコマンド集：

```bash
# リポジトリ general / マージ動作
gh api repos/yzanbo/ai-coding-drill | jq '{
  visibility, default_branch, description,
  has_issues, has_discussions, has_wiki, has_projects,
  allow_forking,
  allow_merge_commit, allow_squash_merge, allow_rebase_merge,
  allow_auto_merge, allow_update_branch, delete_branch_on_merge,
  default_workflow_permissions, web_commit_signoff_required
}'

# Ruleset 一覧
gh api repos/yzanbo/ai-coding-drill/rulesets

# Ruleset 詳細（id は上記コマンドで取得）
gh api repos/yzanbo/ai-coding-drill/rulesets/<id>

# Actions 設定
gh api repos/yzanbo/ai-coding-drill/actions/permissions
gh api repos/yzanbo/ai-coding-drill/actions/permissions/workflow

# Security 設定
gh api repos/yzanbo/ai-coding-drill/vulnerability-alerts          # 204 = 有効、404 = 無効
gh api repos/yzanbo/ai-coding-drill/automated-security-fixes      # { enabled, paused }

# Collaborators
gh api repos/yzanbo/ai-coding-drill/collaborators --jq '.[].login'
```

---

## 関連

- [06-dev-workflow.md](./06-dev-workflow.md) — CI/CD のジョブ設計（lint / typecheck / test 等の中身）
- [ADR 0023: CI/CD ツールに GitHub Actions を採用](../../adr/0023-github-actions-as-ci-cd.md)
- [ADR 0024: Dependabot 自動更新ポリシー](../../adr/0024-dependabot-auto-update-policy.md)
- [ADR 0025: コミット scope 規約](../../adr/0025-commit-scope-convention.md)
- [ADR 0026: GitHub Actions のサードパーティアクションを SHA でピン止め](../../adr/0026-github-actions-sha-pinning.md)
- [ADR 0030: ci-success 集約ジョブで Required status checks を 1 本化](../../adr/0030-ci-success-umbrella-job.md)
- [ADR 0031: GitHub リポジトリ設定の方針](../../adr/0031-github-repository-settings.md)
