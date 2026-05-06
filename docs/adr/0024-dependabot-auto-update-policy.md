# 0024. 依存関係の自動更新ポリシー（Dependabot）

- **Status**: Accepted
- **Date**: 2026-05-05
- **Decision-makers**: 神保 陽平

## Context（背景・課題）

R0 の段階で依存関係の更新運用を決める必要がある。本リポジトリには以下の依存が存在する：

- **GitHub Actions**：`.github/workflows/*.yml` および `.github/actions/*/action.yml` 内の `uses:` 参照（外部 Action）
- **npm（pnpm 管理）**：ルートの `pnpm-lock.yaml` 経由で各 workspace の依存ツリー全体

放置すると以下の問題が起きる：

- セキュリティ脆弱性のパッチが適用されない
- メジャーバージョン跨ぎでまとめて移行する羽目になり、移行コストが膨らむ
- GitHub Actions に至っては、同 R0-6 でセット導入する SHA ピン止め（→ [ADR 0026](./0026-github-actions-sha-pinning.md)）と組み合わせると **メンテナが手で SHA を追従するのは現実的に不可能**（40 文字のハッシュを毎週手で書き換えるのは破綻する）

選択肢は以下：

1. **手動更新**：`pnpm up` や `actions` の手書き更新を必要に応じて実施
2. **Renovate**：高機能な自動更新 Bot（OSS、セルフホスト or Mend.io 提供）
3. **Dependabot**：GitHub 標準の自動更新機能（追加インストール不要）

本プロジェクトはポートフォリオ規模（小〜中）であり、運用コストを最小化しつつ「自動更新の仕組みを構造的に持つ」ことが要件。

## Decision（決定内容）

**Dependabot を採用し、`.github/dependabot.yml` で github-actions / npm の週次自動 PR を有効化する。** 以下のポリシーを SSoT として `.github/dependabot.yml` に集約する：

| 項目 | 設定 | 理由 |
|---|---|---|
| 監視対象 | `github-actions` + `npm` | リポジトリ内の依存全種類 |
| 頻度 | `weekly`（月曜 06:00 Asia/Tokyo） | 週初に PR 集約 → 週内レビュー可能 |
| メジャー更新 | `ignore` で除外 | 破壊的変更は人間が判断 |
| グループ化 | `@types/*` / `@biomejs/*` + `biome` / `@commitlint/*` + `commitlint` | 関連パッケージの版ずれを防ぎ PR 数も削減 |
| コミットメッセージ | `prefix: build` + `include: scope` | commitlint 規約（`type(scope): subject`）準拠 |
| PR 上限 | github-actions 5 / npm 10 | グループ外の単発 PR で詰まらない余裕 |
| ラベル | `dependencies` + エコシステム名 | フィルタリング用 |

これに合わせて：

- **`commitlint.config.mjs` の `scope-enum` に `deps-dev` を追加**（既存の `deps` と合わせて、Dependabot が `include: scope` で生成する `(deps)` / `(deps-dev)` の両 scope を許可）
- **`.claude/CLAUDE.md` の scope 表に `deps-dev` を追加**（人間が手動 PR を書く時の参照）

## Why（採用理由）

### Dependabot を選ぶ理由

- **GitHub 標準・追加コストゼロ**：Public/Private 問わず無料、設定 1 ファイル（`.github/dependabot.yml`）で完結。SaaS 連携・OAuth App 認可・サードパーティへの権限委譲が一切不要
- **GitHub Actions エコシステムとネイティブ統合**：`uses:` 参照を直接解析して SHA + バージョンコメントを書き換える PR を作れる。これは Renovate でも可能だが、Dependabot は GitHub 同期が最も確実
- **CodeQL / Secret Scanning と並ぶ「GitHub セキュリティ機能の標準セット」**：監査・面接・採用担当者が見ても「妥当な選択」と即座に判断できる
- **このプロジェクト規模に対して機能十分**：Renovate の高度な機能（カスタム正規表現マネージャ、自動マージのきめ細かい制御等）は中〜大規模リポジトリ向けで、本プロジェクトでは過剰

### 週次（weekly）を選ぶ理由

- **daily**：PR ノイズが多く、レビュー疲労で形骸化しやすい
- **weekly**：月曜朝にまとめて受け取り、週内に確認・マージするリズムが回る
- **monthly**：脆弱性修正の取り込みが遅れる（CVE 公開から 30 日近く放置されうる）

### メジャーバージョン更新を除外する理由

- 破壊的変更を含むため、リリースノート確認・コード修正・テスト追加が必要
- 機械的に PR 化すると毎週同じ内容で上がり、close する手間がノイズ化する
- 必要なときに人間が `pnpm up <pkg>@latest` で取り込む方針（明示的・意図的な移行）
- minor / patch は引き続き自動 PR 化される（脆弱性修正の追従が止まることはない）

### グループ化する理由

| グループ | 含まれるパッケージ | 束ねる根拠 |
|---|---|---|
| `types` | `@types/*` | 型定義のみで実体コードを含まず、破壊的変更の影響範囲が小さい |
| `biome` | `@biomejs/*` + `biome` | バージョンが揃っていないと lint/format 挙動が一時的に矛盾する |
| `commitlint` | `@commitlint/*` + `commitlint` | サブパッケージ間の API バージョン不一致で commit-msg フックが壊れる |

「単独で更新すると壊れる／意味がない」関係のあるパッケージ群だけをグループ化し、独立性のある依存（例：将来の `react`、`next` 等）は単発 PR を維持する。

### commit-message を commitlint 規約に揃える理由

- このプロジェクトは `commitlint.config.mjs` で **`type-empty` / `type-enum` / `scope-enum` を error (level=2)** にしているため、規約外のコミットは弾かれる
- Dependabot 既定の `Bump foo from X to Y` 形式（type 無し）では `type-empty` で確実に落ちる
- `prefix: build` + `include: scope` を指定することで `build(deps): bump ...` / `build(deps-dev): bump ...` という規約準拠の形式になる
- `scope-enum` に `deps-dev` を追加したのはこのため（grouped PR は `(deps)` 固定だが、グループ外の単発 dev 依存更新は `(deps-dev)` を生成するため）

## Alternatives Considered（検討した代替案）

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| A. 手動更新 | 必要時に `pnpm up` / Action 手書き更新 | 同 R0-6 で導入する SHA ピン止め（→ [ADR 0026](./0026-github-actions-sha-pinning.md)）との組み合わせが破綻（40 文字 SHA を手で追従不可）。脆弱性追従が属人化 |
| B. Renovate | 高機能な自動更新 Bot | このプロジェクト規模では過剰。GitHub App 認可・SaaS 連携が増え、依存先（攻撃面）が拡大する |
| C. **Dependabot（採用）** | GitHub 標準の自動更新 | 設定 1 ファイルで完結、追加依存ゼロ、GitHub セキュリティ機能の標準セットの一部 |
| D. Dependabot（既定設定のまま） | `.github/dependabot.yml` に最小設定だけ書く | コミットメッセージが commitlint 規約に合わず CI で弾かれて自動 PR が機能しない。グループ化なしだと PR 数が爆発する |

## Consequences（結果・トレードオフ）

### 得られるもの

- **脆弱性パッチが構造的に追従される**：CVE 公開から最長 1 週間以内に PR が作られる
- **同 R0-6 でセット導入する SHA ピン止め（→ [ADR 0026](./0026-github-actions-sha-pinning.md)）が実用可能になる**：人間が SHA を追従する負担なしに不変参照を維持できる
- **major 移行が「決断のタイミング」になる**：minor/patch は自動で取り込み、メジャーは人間が意図的にスケジュールできる
- **commitlint 規約と整合**：自動 PR がそのまま CI を通過し、レビュー → マージで完結

### 失うもの・受容するリスク

- **PR レビュー負荷の増加**：週次で複数の自動 PR が立つ。グループ化で緩和するが完全には消えない
- **pnpm-lock.yaml のコンフリクト**：複数の自動 PR が同時に lockfile を書き換えるため、マージ順次第でリベースが必要になる場合がある
- **`open-pull-requests-limit` を超えた更新は次週に持ち越される**：上限を低くしすぎると古い更新が滞留する（npm:10 / github-actions:5 はこのプロジェクト規模に対する目安）
- **`scope-enum` の保守が必要**：Dependabot が生成する scope（`deps` / `deps-dev`）が将来変更された場合、commitlint 設定の追従が必要

### 将来の見直しトリガー

- **PR 数が週 15 件を超えるようになったら**：グループ化対象を増やすか、`open-pull-requests-limit` を見直す
- **lockfile コンフリクトが頻発するようになったら**：Dependabot の rebase 戦略（`rebase-strategy: auto` 等）を再検討、または `cooldown` で更新タイミングを分散
- **メジャー更新の遅延が問題化したら**：除外を解除し、人間レビュー前提で自動 PR 化する
- **Renovate に移行するメリットが出る規模になったら**：例えばモノレポ workspace が 10 を超え、複雑なグループ化ルールが必要になった時点
- **GitHub の Dependabot 仕様変更**：`include: scope` の挙動変更、新しい update-types の追加等

## 補足（2026-05-05 追加）

初回の Dependabot 自動 PR（PR #11：`actions/checkout` v5.0.1 → v6.0.2）で、メジャーバージョン更新が github-actions エコシステムから自動 PR 化されたことを契機に、**「メジャー更新除外」の適用範囲がエコシステムごとに異なる**ことを明文化する。本 ADR の Decision（Dependabot 採用・週次・グループ化）は維持する。Append-only 原則のため Decision 表・Alternatives 等の本文は書き換えない。

### メジャー更新除外の適用範囲（明確化）

| エコシステム | メジャー更新の自動 PR 化 | 理由 |
|---|---|---|
| `github-actions` | **許可（自動 PR 化される）** | GitHub 公式 Action はメジャー版がリリースされた後、後継版が比較的短い間隔で続くことがある（actions/checkout v5 → v6 が数ヶ月）。メジャー版の変更内容は Node ランタイム要件の更新等が中心で、`with:` 引数の互換性に影響しない範囲に収まることが多い。`ignore` で止めると SHA ピン止めの追従が滞り、ADR 0026 の前提（Dependabot で SHA を更新し続ける）が崩れる。**人間が PR ごとに breaking change の有無を確認・マージ判断する**運用とする |
| `npm` | **除外（自動 PR 化されない）** | アプリケーション本体のランタイム依存はメジャー更新で API 互換性が崩れることが多く、リリースノート確認・コード修正・テスト追加が必要。機械的に PR 化すると毎週同じ内容で上がり close する手間がノイズ化する。必要なときに人間が `pnpm up <pkg>@latest` で取り込む明示的・意図的な移行とする |

`.github/dependabot.yml` の実装はこの方針通り：`github-actions` ブロックには `ignore` を置かず、`npm` ブロックにのみ `version-update:semver-major` を `ignore` で除外する。

### github-actions メジャー更新 PR のレビュー観点

メジャー更新 PR が来た場合に確認すべき項目を、運用の指針として残す：

1. **breaking change の確認**：該当 Action の v(N).0.0 リリースノートと CHANGELOG を読む
2. **`with:` 引数互換性**：本リポジトリで指定している引数（現状はほぼ無し）が継続して有効か
3. **ランタイム要件**：Node.js のバージョン要件等、ランナー側の前提に影響がないか
4. **CI 通過確認**：自動更新 PR の CI が緑であることを確認（commitlint / Biome / typecheck が通れば最低限の動作保証）
5. **SHA とコメントの整合**：`@<sha> # vX.Y.Z` のコメントと SHA が同じバージョンを指しているか（Dependabot は通常正しく更新するが、念のため）

### 将来の見直しトリガー（追加）

- **github-actions のメジャー更新 PR がレビュー負荷になった場合**：Action ごとの `ignore` を個別追加する（例：特定の Action だけ major を止める）
- **特定 Action のメジャー更新で複数回 breaking change が発生した場合**：該当 Action だけ `dependency-name` 単位で `version-update:semver-major` を ignore する

## References

- [.github/dependabot.yml](../../.github/dependabot.yml)：本 ADR の実装（SSoT）
- [commitlint.config.mjs](../../commitlint.config.mjs)：`scope-enum` に `deps` / `deps-dev` を登録
- [.claude/CLAUDE.md](../../.claude/CLAUDE.md)：scope 表（人間が手動 PR を書く時の参照）
- [ADR 0018](./0018-phase-0-tooling-discipline.md)：補完ツールを R0 から導入（Dependabot もこの系譜）
- [ADR 0022](./0022-github-actions-incremental-scope.md)：GitHub Actions の段階拡張（Dependabot は R0 構成の一部）
- [ADR 0023](./0023-github-actions-as-ci-cd.md)：CI/CD ツールに GitHub Actions を採用
- [GitHub Docs: Configuration options for the dependabot.yml file](https://docs.github.com/code-security/dependabot/dependabot-version-updates/configuration-options-for-the-dependabot.yml-file)
