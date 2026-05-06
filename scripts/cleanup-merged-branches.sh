#!/usr/bin/env bash
# ======================================================================
# マージ済みブランチのローカル掃除スクリプト
# ======================================================================
#
# 役割：
#   GitHub 側でマージ + 自動削除されたブランチに対応する「ローカルブランチ」を
#   一括削除する。リポジトリ設定 delete_branch_on_merge: true（→ ADR 0031）と
#   組み合わせる前提。
#
# 動作：
#   1. 未コミットの変更がないことを確認（あれば中断、誤って失わないため）
#   2. `git fetch -p` でリモート追跡参照を整理（消えたブランチの追跡先を削除）
#   3. `[origin/...: gone]` 状態のローカルブランチを検出（= マージ済みブランチ）
#   4a. 現在ブランチが削除対象に含まれる場合：
#        main へ切替 → `git pull --ff-only` で最新化 → 削除
#   4b. 現在ブランチが削除対象に含まれない場合：
#        現在ブランチに留まったまま削除（main へは移動しない）
#
# 安全性：
#   - 未コミット変更がある場合は中断（uncommitted work を強制 stash しない）
#   - upstream を持たないローカル専用ブランチ（例：ローカルで作っただけで未 push）は
#     `[gone]` 状態にならないため対象外。誤削除されない
#   - upstream はあるがリモートにまだ存在するブランチも対象外
#   - 削除した直後でも `git reflog` で 90 日間は復元可能
#   - `--ff-only` により main がローカルで分岐していた場合は中断（事故防止）
#
# 使い方：
#   pnpm g-clean
#
# 備考：
#   `xargs -r` は GNU xargs 専用フラグ（BSD xargs では未対応の OS バージョンあり）、
#   `mapfile` は bash 4+ 専用（macOS 既定の bash 3.2 では未対応）のため、
#   両者に依存しないポータブルな実装としている。
# ----------------------------------------------------------------------

set -euo pipefail

# ── ステップ 1：未コミットの変更がないか確認
if [[ -n "$(git status --porcelain)" ]]; then
  echo "エラー：未コミットの変更があります。コミットまたは stash してから再実行してください" >&2
  git status --short
  exit 1
fi

# ── ステップ 2：リモート追跡を整理
git fetch --prune

# ── ステップ 3：[gone] 状態のローカルブランチを検出
gone_branches=$(git branch -vv | awk '/: gone]/{print $1}')

if [[ -z "${gone_branches}" ]]; then
  echo "削除対象のブランチはありません（マージ済み + リモート削除済みのローカルブランチなし）"
  exit 0
fi

# ── ステップ 4：現在ブランチが削除対象に含まれるか判定
current_branch=$(git rev-parse --abbrev-ref HEAD)
current_is_gone=false
while IFS= read -r br; do
  [[ -z "${br}" ]] && continue
  if [[ "${br}" == "${current_branch}" ]]; then
    current_is_gone=true
    break
  fi
done <<<"${gone_branches}"

# ── ステップ 4a：現在ブランチが削除対象 → main へ切替 + 最新化
if [[ "${current_is_gone}" == "true" ]]; then
  echo "現在ブランチ「${current_branch}」が削除対象のため main へ切替します"
  git switch main
  echo "最新 main を取得"
  git pull --ff-only
fi

# ── ステップ 5：削除対象を表示して順次削除
echo
echo "以下のローカルブランチを削除します（リモートが消えています）："
printf "  - %s\n" ${gone_branches}
echo

count=0
while IFS= read -r br; do
  [[ -z "${br}" ]] && continue
  git branch -D "${br}"
  count=$((count + 1))
done <<<"${gone_branches}"

echo
echo "完了：${count} 件のブランチを削除しました"
