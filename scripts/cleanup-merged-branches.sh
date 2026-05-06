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
#   2. `git fetch --prune` でリモート追跡参照を整理（消えたブランチの追跡先を削除）
#   3. 現在ブランチがリモートで削除済みかを確認
#   4. 削除済みなら main へ切替 → `git pull --ff-only` で最新化
#   5. `[gone]` 状態のローカルブランチを全列挙して順次削除
#
# 安全性：
#   - 未コミット変更がある場合は中断（uncommitted work を強制 stash しない）
#   - upstream を持たないローカル専用ブランチ（例：ローカルで作っただけで未 push）は
#     `[gone]` 状態にならないため対象外。誤削除されない
#   - upstream はあるがリモートにまだ存在するブランチも対象外
#   - 削除した直後でも `git reflog` で 90 日間は復元可能
#   - `--ff-only` により main がローカルで分岐していた場合は中断（事故防止）
#   - `git for-each-ref` ベースで列挙し、`git branch -vv` の現在ブランチ行頭 `*` を
#     値として拾ってしまう罠を回避。`set -f` でグロブ展開も無効化
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
set -f  # グロブ展開を無効化（万一 branch 名に * が混入しても安全）

# ── ステップ 1：未コミットの変更がないか確認
if [[ -n "$(git status --porcelain)" ]]; then
  echo "エラー：未コミットの変更があります。コミットまたは stash してから再実行してください" >&2
  git status --short
  exit 1
fi

# ── ステップ 2：リモート追跡を整理
git fetch --prune

# ── ステップ 3：現在ブランチがリモートで削除済みか確認
current_branch=$(git rev-parse --abbrev-ref HEAD)
current_upstream_track=$(git for-each-ref --format='%(upstream:track)' "refs/heads/${current_branch}")

# ── ステップ 4：削除済みなら main へ切替 + 最新化
if [[ "${current_upstream_track}" == "[gone]" ]]; then
  echo "現在ブランチ「${current_branch}」がリモートで削除済みのため main へ切替します"
  git switch main
  echo "最新 main を取得"
  git pull --ff-only
fi

# ── ステップ 5：[gone] 状態のローカルブランチを全列挙して削除
gone_branches=$(git for-each-ref --format='%(refname:short) %(upstream:track)' refs/heads \
  | awk '$2 == "[gone]" {print $1}')

if [[ -z "${gone_branches}" ]]; then
  echo "削除対象のブランチはありません（マージ済み + リモート削除済みのローカルブランチなし）"
  exit 0
fi

echo
echo "以下のローカルブランチを削除します（リモートが消えています）："
while IFS= read -r br; do
  [[ -z "${br}" ]] && continue
  echo "  - ${br}"
done <<<"${gone_branches}"
echo

count=0
while IFS= read -r br; do
  [[ -z "${br}" ]] && continue
  git branch -D "${br}"
  count=$((count + 1))
done <<<"${gone_branches}"

echo
echo "完了：${count} 件のブランチを削除しました"
