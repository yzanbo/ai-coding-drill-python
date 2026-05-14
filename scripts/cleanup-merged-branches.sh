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
# 動作（要約）：
#   1. ステージ（index）+ 作業ツリー + untracked を **すべて** auto-stash
#   2. main へ切替 → `git pull --ff-only` で最新化
#   3. `git fetch --prune` でリモート追跡参照を整理
#   4. `[gone]` 状態のローカルブランチを全列挙して順次削除
#   5. 退避した stash を **main 上で pop**（trap で終了時に必ず実行）
#
# 安全性：
#   - 未コミット変更は失わない：ステージ済 / 未ステージ / untracked のすべてを stash に退避し、
#     終了時（正常 / エラー / Ctrl-C 問わず trap）に必ず pop する
#   - stash pop で競合した場合は変更を stash に残したまま中断（手動解決を促す）
#   - 元ブランチが削除対象だった場合：stash は main 上に復元される（変更は失われない）
#   - upstream を持たないローカル専用ブランチ（ローカル作成のみで未 push）は `[gone]` に
#     ならないため対象外
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

# ── 終了時に必ず stash を復元する trap
#    set -e でエラー終了した場合・Ctrl-C で中断した場合・正常終了した場合
#    のすべてで実行される。
stash_created=false
restore_stash() {
  local exit_code=$?
  if [[ "${stash_created}" == "true" ]]; then
    echo
    echo "退避した変更を復元します（git stash pop）"
    # pop は exit code を維持したいので、ここでは失敗しても元エラーを上書きしない
    if git stash pop; then
      echo "復元しました"
    else
      echo "警告：stash pop で競合 / エラーが発生しました。" >&2
      echo "      変更は stash に残っています。以下で確認・解決してください：" >&2
      echo "        git stash list" >&2
      echo "        git stash show -p stash@{0}" >&2
    fi
  fi
  exit "${exit_code}"
}
trap restore_stash EXIT

# ── ステップ 1：ステージ + 作業ツリー + untracked を auto-stash
#    git stash push -u:
#      - 既定でステージ済（index）と未ステージ（作業ツリー）の両方を stash
#      - -u で untracked ファイルも含める
#      - -m でラベルを付けて後から識別しやすくする
if [[ -n "$(git status --porcelain)" ]]; then
  echo "未コミットの変更を検出。ステージ + 作業ツリー + untracked を stash に退避します"
  git status --short
  echo
  git stash push -u -m "cleanup-merged-branches: auto-stash $(date +%Y%m%d-%H%M%S)"
  stash_created=true
  echo
fi

# ── ステップ 2：main へ切替 + 最新化（変更が無くなった clean な状態で実行）
current_branch=$(git rev-parse --abbrev-ref HEAD)
if [[ "${current_branch}" != "main" ]]; then
  echo "main へ切替します（元ブランチ：${current_branch}）"
  git switch main
fi
echo "最新 main を取得（git pull --ff-only）"
git pull --ff-only

# ── ステップ 3：リモート追跡を整理
echo "リモート追跡参照を整理（git fetch --prune）"
git fetch --prune

# ── ステップ 4：[gone] 状態のローカルブランチを全列挙して削除
gone_branches=$(git for-each-ref --format='%(refname:short) %(upstream:track)' refs/heads \
  | awk '$2 == "[gone]" {print $1}')

if [[ -z "${gone_branches}" ]]; then
  echo
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
# trap EXIT で stash があれば自動 pop される
