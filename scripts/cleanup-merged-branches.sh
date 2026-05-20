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
#   0. rebase / merge / cherry-pick / revert / bisect の途中なら起動時点で中断
#   1. ステージ（index）+ 作業ツリー + untracked を **すべて** auto-stash
#   2. main へ切替 → `git pull --ff-only` で最新化
#   3. `git fetch --prune` でリモート追跡参照を整理
#   4. `[gone]` 状態のローカルブランチを列挙し、PROTECTED_BRANCHES と
#      他 worktree チェックアウト中のものを除外してから順次削除
#   5. 元ブランチが残っていれば戻る（main / detached HEAD / 削除済みの場合は main に残る）
#   6. 退避した stash を **戻った先のブランチ上で pop**（trap で終了時に必ず実行）
#   7. 削除に失敗したブランチがあれば非ゼロで終了
#
# 安全性：
#   - 未コミット変更は失わない：ステージ済 / 未ステージ / untracked のすべてを stash に退避し、
#     終了時（正常 / エラー / Ctrl-C 問わず trap）に必ず pop する
#   - stash pop で競合した場合は変更を stash に残したまま中断（手動解決を促す）
#   - 元ブランチが削除対象だった場合：main に残ったまま stash 復元（変更は失われない）
#   - 元ブランチが削除対象でなかった場合：元ブランチに戻ってから stash 復元
#   - `PROTECTED_BRANCHES`（main / staging / production）は [gone] でも削除しない
#   - 他の git worktree でチェックアウト中のブランチは自動でスキップ（branch -D 失敗を回避）
#   - rebase / merge / cherry-pick / revert / bisect の途中なら stash 前にエラー終了
#     （これらの最中に stash / switch すると状態が壊れるため事前ガード）
#
# 設計判断：`git branch -D`（force-delete）を使う理由
#   `-d`（safe-delete）はマージされていないブランチで失敗するが、本スクリプトは
#   **リモートが削除されたブランチはローカルでも削除する** という運用方針に基づき
#   `-D` を使用している。GitHub 側で未マージのまま remote が削除されたケース
#   （PR クローズ、手動削除など）でもローカルから消える。これは意図通りの挙動。
#   復元が必要になった場合は 90 日以内なら `git reflog` で救える。
#   - upstream を持たないローカル専用ブランチ（ローカル作成のみで未 push）は `[gone]` に
#     ならないため対象外
#   - upstream はあるがリモートにまだ存在するブランチも対象外
#   - 削除した直後でも `git reflog` で 90 日間は復元可能
#   - `--ff-only` により main がローカルで分岐していた場合は中断（事故防止）
#   - `git for-each-ref` ベースで列挙し、`git branch -vv` の現在ブランチ行頭 `*` を
#     値として拾ってしまう罠を回避。`set -f` でグロブ展開も無効化
#
# 使い方：
#   mise run git:clean
#   （または直接：bash scripts/cleanup-merged-branches.sh）
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

# ── 事前チェック：進行中の rebase / merge / cherry-pick / bisect を検出
#    これらの最中に stash や switch を行うと状態が壊れるため、先に中断させる。
git_dir=$(git rev-parse --git-dir)
if [[ -d "${git_dir}/rebase-merge" ]] \
  || [[ -d "${git_dir}/rebase-apply" ]] \
  || [[ -f "${git_dir}/MERGE_HEAD" ]] \
  || [[ -f "${git_dir}/CHERRY_PICK_HEAD" ]] \
  || [[ -f "${git_dir}/REVERT_HEAD" ]] \
  || [[ -f "${git_dir}/BISECT_LOG" ]]; then
  echo "rebase / merge / cherry-pick / revert / bisect の途中です。" >&2
  echo "完了または中断してから再実行してください。" >&2
  exit 1
fi

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
#    元ブランチは記録しておき、削除されなかった場合は最後に戻る
original_branch=$(git rev-parse --abbrev-ref HEAD)
if [[ "${original_branch}" != "main" ]]; then
  if [[ "${original_branch}" == "HEAD" ]]; then
    echo "main へ切替します（元：detached HEAD）"
  else
    echo "main へ切替します（元ブランチ：${original_branch}）"
  fi
  git switch main
fi
echo "最新 main を取得（git pull --ff-only）"
git pull --ff-only

# ── ステップ 3：リモート追跡を整理
echo "リモート追跡参照を整理（git fetch --prune）"
git fetch --prune

# ── 元ブランチに戻れるなら戻る（main / detached HEAD / 削除済みの場合は main に残る）
#    trap で実行される stash pop は、ここで切り替えたブランチ上で行われる
return_to_original() {
  if [[ "${original_branch}" == "main" || "${original_branch}" == "HEAD" ]]; then
    return
  fi
  if ! git show-ref --verify --quiet "refs/heads/${original_branch}"; then
    echo "元ブランチ ${original_branch} は削除されたため main 上に残ります"
    return
  fi
  echo "元ブランチに戻ります：${original_branch}"
  git switch "${original_branch}"
}

# ── ステップ 4：[gone] 状態のローカルブランチを全列挙して削除
#    PROTECTED_BRANCHES は誤削除事故を防ぐためのセーフティネット。
#
#    GitHub 側の Ruleset で deletion / non_fast_forward が active になっており
#    （`Protect branches` ruleset が main / staging / production を対象に設定済み）、
#    通常運用ではこれらのリモート参照が消えて [gone] になることはない。
#    したがって、このローカルガードに到達することは現実にはほぼ起こらない。
#
#    それでも残しているのは「保険の保険」として以下のシナリオに備えるため：
#      - ブランチ改名（例: master → main、main → trunk 等）で旧名が一斉に [gone] になる
#      - admin が Ruleset を一時解除した直後に誤操作 / 誤削除が発生する
#      - リポジトリ移行や upstream 設定の事故でローカル参照が孤立する
#    削除されると影響が大きいブランチに対する、コスト ~0 の defense-in-depth。
PROTECTED_BRANCHES=("main" "staging" "production")

is_protected() {
  local target="$1"
  local p
  for p in "${PROTECTED_BRANCHES[@]}"; do
    if [[ "${target}" == "${p}" ]]; then
      return 0
    fi
  done
  return 1
}

all_gone=$(git for-each-ref --format='%(refname:short) %(upstream:track)' refs/heads \
  | awk '$2 == "[gone]" {print $1}')

gone_branches=""
skipped_branches=""
while IFS= read -r br; do
  [[ -z "${br}" ]] && continue
  if is_protected "${br}"; then
    skipped_branches+="${br}"$'\n'
  else
    gone_branches+="${br}"$'\n'
  fi
done <<<"${all_gone}"
gone_branches="${gone_branches%$'\n'}"
skipped_branches="${skipped_branches%$'\n'}"

if [[ -n "${skipped_branches}" ]]; then
  echo
  echo "保護対象のため削除をスキップします（PROTECTED_BRANCHES）："
  while IFS= read -r br; do
    [[ -z "${br}" ]] && continue
    echo "  - ${br}"
  done <<<"${skipped_branches}"
fi

# ── 他の worktree でチェックアウト中のブランチは削除候補から外す
#    `git branch -D` は別 worktree で使用中のブランチに対しては失敗する。
#    `set -e` の下でループが途中で死ぬと一部だけ削除された中途半端な状態で
#    trap に入ってしまうため、実際の削除に進む前にここで除外する。
#    また「削除します」一覧に紛れて表示されるのを防ぎ、ユーザーに正確な
#    候補のみを提示するためにも先に分離する。
worktree_branches=$(git worktree list --porcelain \
  | awk '/^branch / {sub(/^refs\/heads\//, "", $2); print $2}')

to_delete_branches=""
worktree_skipped=""
while IFS= read -r br; do
  [[ -z "${br}" ]] && continue
  if [[ -n "${worktree_branches}" ]] \
    && grep -Fxq "${br}" <<<"${worktree_branches}"; then
    worktree_skipped+="${br}"$'\n'
  else
    to_delete_branches+="${br}"$'\n'
  fi
done <<<"${gone_branches}"
to_delete_branches="${to_delete_branches%$'\n'}"
worktree_skipped="${worktree_skipped%$'\n'}"

if [[ -n "${worktree_skipped}" ]]; then
  echo
  echo "他の worktree でチェックアウト中のためスキップ："
  while IFS= read -r br; do
    [[ -z "${br}" ]] && continue
    echo "  - ${br}"
  done <<<"${worktree_skipped}"
fi

if [[ -z "${to_delete_branches}" ]]; then
  echo
  echo "削除対象のブランチはありません（マージ済み + リモート削除済みのローカルブランチなし）"
  return_to_original
  exit 0
fi

echo
echo "以下のローカルブランチを削除します（リモートが消えています）："
while IFS= read -r br; do
  [[ -z "${br}" ]] && continue
  echo "  - ${br}"
done <<<"${to_delete_branches}"
echo

count=0
failed_branches=""
while IFS= read -r br; do
  [[ -z "${br}" ]] && continue
  # 個別の失敗で全体を止めないよう if で受ける（残りのブランチも処理する）
  if git branch -D "${br}"; then
    count=$((count + 1))
  else
    failed_branches+="${br}"$'\n'
  fi
done <<<"${to_delete_branches}"

if [[ -n "${failed_branches}" ]]; then
  echo
  echo "削除に失敗したブランチ（手動確認が必要）：" >&2
  while IFS= read -r br; do
    [[ -z "${br}" ]] && continue
    echo "  - ${br}" >&2
  done <<<"${failed_branches%$'\n'}"
fi

echo
echo "完了：${count} 件のブランチを削除しました"
return_to_original
# trap EXIT で stash があれば自動 pop される（戻った先のブランチ上で pop される）

# 削除に失敗したブランチが 1 件でもあれば非ゼロで終了（CI / 自動化向け）
if [[ -n "${failed_branches}" ]]; then
  exit 1
fi
