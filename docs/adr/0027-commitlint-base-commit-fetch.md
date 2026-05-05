# 0027. commitlint の base コミット取得を iterative deepen 方式で行う

- **Status**: Accepted
- **Date**: 2026-05-05
- **Decision-makers**: 神保 陽平

## Context（背景・課題）

[ADR 0022](./0022-github-actions-incremental-scope.md) で導入した GitHub Actions 上の commitlint ジョブは、PR / push の **base..head（または before..after）の範囲**でコミットメッセージを検証する。具体的には：

- 経路 A：`pull_request` イベント → `git log <base.sha>..<head.sha>` を commitlint に流す
- 経路 B：`push` イベント → `git log <before>..<after>` を commitlint に流す

CI 時間の最適化として `actions/checkout` の `fetch-depth: 1`（既定値）を選びたい。`fetch-depth: 0`（全履歴取得）はリポジトリ運用期間に比例して遅くなり、累積コミット数が多くなるほど CI が劣化するため避けたい。

しかし `fetch-depth: 1` では **base.sha や PR コミット群の Git オブジェクトが手元に存在しない**ため、`git log base..head` が `fatal: Invalid revision range` で失敗する。base コミットだけ追加取得する仕組みが必要。

### 試した実装と判明した問題

#### 第 1 案：`--shallow-exclude=<base.sha>`（commit `a8d4eea` で導入）

Git の標準機能で「指定 SHA より古い祖先を除外して fetch」する。理屈の上では：

- `git fetch --shallow-exclude=<base.sha> origin <head.sha>` で **PR で追加されたコミット群だけ**を取得
- 続いて `git fetch --depth=1 origin <base.sha>` で base コミット単体を追加
- これで `base..head` の範囲解決が成立し、取得量は「PR コミット数 + 1」に収まる

これがローカル Git（`git daemon` / SSH プロトコル）では動く。**しかし実 CI（GitHub の Git プロトコル）で実行すると以下のエラーで失敗**：

```
fatal: expected 'acknowledgments'
```

調査の結果、**GitHub の smart HTTP Git プロトコル v2 サーバが `--shallow-exclude=<sha>` を発行した際の acknowledgments 応答を返さない**ことが原因と判明。GitHub のフェッチプロトコル実装は OSS Git のフル機能を網羅しておらず、利用者側からは制御不能。

#### 第 2 案：`fetch-depth: 0`

全履歴を取得すれば確実に動くが、`actions/checkout` 公式ドキュメントが明示的に避けるよう推奨している方式。リポジトリのコミット履歴が増えるほど CI 時間が線形に劣化する（数年運用すると 1 ジョブで分単位の差が出る）。

#### 第 3 案：`fetch-depth: 50`（または十分大きい固定値）

「ほとんどの PR は 50 コミット未満だから 50 件取れば足りるはず」という近似。実装は単純だが：

- 50 を超える PR で破綻する（実装が壊れる前提条件が暗黙）
- 取得量が常に最大値で固定される（小さい PR でも 50 コミット分のオブジェクトを引く）
- 「なぜ 50 なのか」の根拠が薄い

## Decision（決定内容）

**`actions/checkout@<sha> # v5.0.1`（depth=1）の後、commitlint ジョブで base.sha が手元に届くまで `--deepen=20` を繰り返す iterative deepen 方式を採用する。**

経路 A / 経路 B 共通のパターン：

```yaml
- name: "[PR] Deepen until base reachable"
  if: github.event_name == 'pull_request'
  run: |
    BASE_SHA="${{ github.event.pull_request.base.sha }}"
    for i in $(seq 1 10); do
      git cat-file -e "${BASE_SHA}^{commit}" 2>/dev/null && exit 0
      git fetch --no-tags --deepen=20 origin
    done
    echo "::error::base.sha (${BASE_SHA}) not reachable after 10 deepen rounds (200 commits)"
    exit 1
```

### 仕組み

1. **到達判定**：`git cat-file -e <sha>^{commit}` で base コミットが手元の Git オブジェクトデータベースに存在するかを確認
2. **未到達なら deepen**：`git fetch --deepen=20 origin` で履歴を 20 コミット分追加取得
3. **到達するまでループ**：通常の PR（1〜5 コミット）は 1 回の deepen で完了。深い PR でも数回で完了
4. **最大 10 回（= 200 コミット）で打ち切り**：それでも届かない場合は明示的にエラー終了し、CI ログで原因を可視化

### 取得量の特性

| シナリオ | 取得コミット数 |
|---|---|
| 1〜20 コミット PR | 20 |
| 21〜40 コミット PR | 40 |
| 100 コミット PR | 100 |
| **リポジトリ全体の累積コミット数** | **取得量とは無関係** |

つまり取得量は「PR の規模 × 20 単位の切り上げ」で決まり、リポジトリ運用期間に依存しない。これは `--shallow-exclude` で得られる特性（ADR 0022 で求めていた性質）と等価。

### 適用箇所

- `.github/workflows/ci.yml` の commitlint ジョブ
- 経路 A（`pull_request`）：base.sha まで deepen
- 経路 B（`push`）：before まで deepen（初回 push の `0000...` の場合は分岐で skip）

## Why（採用理由）

### iterative deepen を選ぶ理由

- **GitHub の Git プロトコル制約を回避できる**：`--deepen=N` はコミット数指定のシンプルな深掘りで、SHA 指定の acknowledgments 機能を必要としない。GitHub サーバ側の対応有無に依存しない原始的な手法
- **リポジトリ運用期間に対する不変性**：取得量が PR 規模で決まるため、累積コミット数が増えても CI 時間が劣化しない（`fetch-depth: 0` 回避の本来の目的を満たす）
- **アルゴリズム的に決定的**：base に到達するまでループするため、PR 規模が事前に分からなくても確実に動く（固定 depth の近似と異なり破綻条件がない）
- **実装が読める**：`until git cat-file -e ...; do git fetch --deepen=20; done` はシェル知識だけで意味を読み取れる。Git のサブコマンド `cat-file -e` も標準機能

### `--deepen=20` のチャンクサイズを選ぶ理由

- **PR の中央値（数コミット〜十数コミット）を 1 fetch で吸収できる大きさ**：典型的な PR が 1 ループで完了する
- **大きすぎない**：1 単位で 100 や 200 にすると、小さい PR でも過剰取得になる
- **小さすぎない**：1 単位で 5 にすると、深い PR で fetch ラウンドトリップが増えて遅くなる
- **20 という具体値の根拠は近似的**：将来 PR の典型サイズが変わったら再調整するチューニングパラメータ

### 経路 A と経路 B で同じパターンを使う理由

- **コードの均質性**：PR 経路と push 経路で実装パターンが揃うとレビュアー・保守者の認知負荷が下がる
- **トラブルシュート時の再現性**：どちらかで問題が起きた場合に、もう一方で同じ修正が利く
- **fetch コマンドの差を最小化**：`base.sha` か `before` かの違いだけで、構造は同一

## Alternatives Considered（検討した代替案）

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| A. `fetch-depth: 0` | 全履歴を取得 | リポジトリ運用期間に比例して劣化（[ADR 0022](./0022-github-actions-incremental-scope.md) の「累積コミット数に依存しない」目標に反する） |
| B. `fetch-depth: 50` 等の固定値 | 大きめの定数で取得 | 50 を超える PR で破綻、根拠が薄い、小さい PR でも過剰取得 |
| C. `--shallow-exclude=<sha>` | SHA 指定で境界 fetch | **GitHub Git プロトコル v2 で acknowledgments 機能が未対応**、`fatal: expected 'acknowledgments'` で実 CI 落ち（commit `a8d4eea` で実装、`e6757f2` で撤去） |
| D. **iterative deepen（採用）** | base 到達まで `--deepen=20` ループ + 最大 10 回の安全弁 | プロトコル依存なし、規模に応じた取得量、決定的 |
| E. ローカル `git fetch` を使わず GitHub API で base..head を取得 | `gh api` 等でメッセージ列を直接取得 | commitlint は git ログを期待する設計、API 経由は変換層が必要で複雑化 |

## Consequences（結果・トレードオフ）

### 得られるもの

- **GitHub Git プロトコル制約への耐性**：実 CI で確実に動作
- **CI 時間がリポジトリ運用期間に依存しない**：累積コミット数に比例した劣化が起きない
- **PR 規模に応じた取得量**：小さい PR は速く、大きい PR は必要分だけ
- **実装の素直さ**：シェル + Git 標準機能のみ、特殊オプションへの依存なし

### 失うもの・受容するリスク

- **fetch ラウンドトリップが複数回発生する可能性**：21〜40 コミット PR は 2 回、41〜60 は 3 回 fetch。1 回完結の `--shallow-exclude` よりはネットワーク往復が増える（ただし通常 PR は 1 回で完了）
- **`--deepen=20` のチューニング負債**：将来 PR の典型サイズが大きく変わったら 20 を見直す必要（コードコメントで明記済み）
- **`git cat-file -e` の挙動依存**：`<sha>^{commit}` 構文と存在チェック挙動は Git 1.x 時代から安定だが、Git の挙動仕様の一部であることを認識しておく
- **ループの上限を 10 回（= 200 コミット深掘り）に制限**：理論上 `git fetch` が永遠に何も追加しない場合の無限ループに対する fail-fast 安全弁。10 回到達しても base が見えなければエラーで停止し、CI が無音で詰まることを防ぐ。これを超える深さの PR は実用上ほぼ存在しない（あるなら `--deepen` のチャンクサイズ自体を見直すべき）
- **GitHub の Git プロトコル仕様変更時の脆さ**：将来 GitHub が `--shallow-exclude` の SHA 対応を実装したら、より単純な書き方に戻せる可能性がある（その時は ADR を新規起票して切り替え判断）

### 将来の見直しトリガー

- **PR の典型サイズが変化**：例えば 50 コミット超の PR が常態化したら `--deepen=50` 等に調整
- **GitHub Git プロトコルが `--shallow-exclude=<sha>` 対応**：戻すかは比較検討
- **CI 実行時間が問題化**：commitlint ジョブ単独の所要時間を測定し、deepen 回数の中央値からチューニング
- **既設の最大ループ回数（10 回 = 200 コミット）に到達するケースが発生**：チャンクサイズ（`--deepen=20`）の見直し、または上限値の引き上げを検討
- **GitHub Actions 側で base コミットを直接渡す API が出る**：`pull_request_target` の派生など、新しい仕組みがあれば移行検討

## References

- [.github/workflows/ci.yml](../../.github/workflows/ci.yml)：本 ADR の実装
- [commit `e6757f2`](https://github.com/yzanbo/ai-coding-drill/commit/e6757f2)：iterative deepen に切り替えた fix コミット
- [commit `a8d4eea`](https://github.com/yzanbo/ai-coding-drill/commit/a8d4eea)：先行実装（`--shallow-exclude` 方式、撤去済み）
- [ADR 0022](./0022-github-actions-incremental-scope.md)：GitHub Actions 段階拡張（commitlint ジョブの所属 ADR）
- [ADR 0023](./0023-github-actions-as-ci-cd.md)：GitHub Actions を CI/CD として採用
- [Git Documentation: `git-fetch --deepen`](https://git-scm.com/docs/git-fetch)
