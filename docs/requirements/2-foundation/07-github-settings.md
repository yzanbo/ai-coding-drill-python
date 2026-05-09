# 07. GitHub リポジトリ設定

> **このドキュメントの守備範囲**：GitHub リポジトリ側の設定で**デフォルトから変更している項目**の現行仕様（What）を一覧する。**選定理由**（Why）は [ADR 0032](../../adr/0032-github-repository-settings.md) を参照。
> **CI/CD のジョブ設計（lint / typecheck / test 等）**は [06-dev-workflow.md](./06-dev-workflow.md) を参照。
> **リポジトリの責務やコード構造**は [02-architecture.md](./02-architecture.md) を参照。

---

## 趣旨

GitHub の UI / API で**デフォルト値から変更している設定**のみを記録する。デフォルト通りの項目はノイズになるため記載しない。設定変更時は本ファイルと [ADR 0032](../../adr/0032-github-repository-settings.md) の両方を更新する。

`gh` で現行値を読み出すコマンド例は本ファイル末尾の [現状確認コマンド](#現状確認コマンド) を、新規リポジトリ等に同じ設定を流し込む手順は [適用コマンド](#適用コマンド) を参照。

---

## リポジトリ基本

| 項目 | 値 |
|---|---|
| description | "LLM-generated programming problems verified by sandboxed grading. Portfolio project." |

---

## Features

| 機能 | 状態 | 変更理由 |
|---|---|---|
| Wiki | ❌ 無効化 | ドキュメントは `docs/` 配下の Markdown に一元化（SSoT 原則）し、Wiki との二重管理を避ける |

---

## Pull Requests / マージ動作

| 項目 | 状態 |
|---|---|
| Allow auto-merge | ✅ ON |
| Always suggest updating pull request branches (`allow_update_branch`) | ✅ ON |
| Automatically delete head branches (`delete_branch_on_merge`) | ✅ ON |

**運用方針**：

- Auto-merge は有効化しているが、**PR ごとに明示的に "Enable auto-merge" を押した PR だけ**が CI 完了後に自動マージされる。デフォルトでは何も自動化されない
- ブランチ自動削除は **GitHub のリモートブランチ**のみ対象。ローカル側はリポジトリ提供の **`pnpm g-clean`** で一括掃除する（実体：[scripts/cleanup-merged-branches.sh](../../../scripts/cleanup-merged-branches.sh)）。`[origin/...: gone]` 状態のブランチのみを削除対象とし、未 push のローカル専用ブランチは誤削除されない。現在ブランチが削除対象だった場合は main へ切替・最新化してから削除する

---

## ブランチ保護（Repository ruleset `protect-main`）

設計判断・代替案検討は [ADR 0031](../../adr/0031-ci-success-umbrella-job.md) を参照。

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
| `required_status_checks` | `ci-success` チェックが緑でないと PR をマージできない（→ ADR 0031） |

---

## GitHub Actions

| 項目 | 値 | 変更理由 |
|---|---|---|
| `default_workflow_permissions` | `read` | `GITHUB_TOKEN` の既定スコープを最小化。書き込みが必要なジョブだけ `permissions:` で明示拡張する方針（→ [.github/workflows/ci.yml](../../../.github/workflows/ci.yml)） |

---

## Security

| 機能 | 状態 |
|---|---|
| Vulnerability alerts（Dependabot alerts） | ✅ 有効 |
| Dependabot security updates（automated security fixes） | ✅ 有効 |

`.github/dependabot.yml` で構成する **Dependabot version updates** は [ADR 0028](../../adr/0028-dependabot-auto-update-policy.md) で別途規定済み。

3 種の Dependabot 機能の役割整理：

| 機能 | 動作 |
|---|---|
| Dependabot alerts | 既知脆弱性を Security タブで通知 |
| Dependabot security updates | alerts 対象を修正版へ上げる PR を自動作成 |
| Dependabot version updates | 通常のバージョン更新 PR を定期作成（脆弱性とは独立） |

`.github/dependabot.yml` の `commit-message` / `labels` / `groups` / `ignore` は version updates だけでなく security updates にも継承される。

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

## 適用コマンド

新規リポジトリ・姉妹リポジトリ等に本ファイルの設定を流し込むためのコマンド集。`OWNER` / `REPO` を対象リポジトリ名に書き換えて実行する。各コマンドは冪等（再実行しても同じ結果になる）。

```bash
OWNER=yzanbo
REPO=ai-coding-drill

# 1. リポジトリ基本 + Pull Requests / マージ動作
#   - description は対象リポジトリ固有のため必要に応じて -f description=... を加える
gh api -X PATCH "repos/${OWNER}/${REPO}" \
  -F has_wiki=false \
  -F allow_auto_merge=true \
  -F allow_update_branch=true \
  -F delete_branch_on_merge=true

# 2. GitHub Actions: GITHUB_TOKEN の既定スコープを read に最小化
gh api -X PUT "repos/${OWNER}/${REPO}/actions/permissions/workflow" \
  -F default_workflow_permissions=read \
  -F can_approve_pull_request_reviews=false

# 3. Security: Dependabot alerts + automated security fixes を有効化
gh api -X PUT "repos/${OWNER}/${REPO}/vulnerability-alerts"      # 204 = 成功
gh api -X PUT "repos/${OWNER}/${REPO}/automated-security-fixes"  # 204 = 成功

# 4. ブランチ保護ルールセット protect-main を作成
#   - 既存の同名 ruleset がある場合は先に削除するか PUT /rulesets/<id> で更新する
gh api -X POST "repos/${OWNER}/${REPO}/rulesets" --input - <<'JSON'
{
  "name": "protect-main",
  "target": "branch",
  "enforcement": "active",
  "bypass_actors": [],
  "conditions": {
    "ref_name": {
      "include": ["~DEFAULT_BRANCH"],
      "exclude": []
    }
  },
  "rules": [
    { "type": "deletion" },
    { "type": "non_fast_forward" },
    {
      "type": "pull_request",
      "parameters": {
        "required_approving_review_count": 0,
        "dismiss_stale_reviews_on_push": true,
        "require_code_owner_review": false,
        "require_last_push_approval": false,
        "required_review_thread_resolution": false
      }
    },
    {
      "type": "required_status_checks",
      "parameters": {
        "strict_required_status_checks_policy": false,
        "required_status_checks": [
          { "context": "ci-success" }
        ]
      }
    }
  ]
}
JSON
```

**適用時の注意**：

- 手順 4 の `required_status_checks` は `ci-success` ジョブが存在することを前提とする。CI 未整備のリポジトリに先行投入すると PR がマージ不能になるため、`.github/workflows/ci.yml` の `ci-success` 集約ジョブ（→ [ADR 0031](../../adr/0031-ci-success-umbrella-job.md)）を整備してから流す
- description は本家固有の文言のため上のコマンドからは除外している。姉妹リポジトリで TS 版と同じ description を使うかは個別判断
- `bypass_actors: []` は admin も例外なしを意味する。緊急回避が必要な運用に変える場合は本ファイルと [ADR 0032](../../adr/0032-github-repository-settings.md) の両方を更新する

---

## 関連

- [06-dev-workflow.md](./06-dev-workflow.md) — CI/CD のジョブ設計（lint / typecheck / test 等の中身）
- [ADR 0025: CI/CD ツールに GitHub Actions を採用](../../adr/0025-github-actions-as-ci-cd.md)
- [ADR 0028: Dependabot 自動更新ポリシー](../../adr/0028-dependabot-auto-update-policy.md)
- [ADR 0029: コミット scope 規約](../../adr/0029-commit-scope-convention.md)
- [ADR 0027: GitHub Actions のサードパーティアクションを SHA でピン止め](../../adr/0027-github-actions-sha-pinning.md)
- [ADR 0031: ci-success 集約ジョブで Required status checks を 1 本化](../../adr/0031-ci-success-umbrella-job.md)
- [ADR 0032: GitHub リポジトリ設定の方針](../../adr/0032-github-repository-settings.md)
