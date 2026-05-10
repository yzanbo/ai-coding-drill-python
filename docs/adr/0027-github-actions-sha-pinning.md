# 0027. GitHub Actions のサードパーティアクションを SHA でピン止め

- **Status**: Accepted
- **Date**: 2026-05-09 <!-- Python pivot に伴う追加アクション（jdx/mise-action 等）も同方針の対象である旨を明示 -->
- **Decision-makers**: 神保 陽平

## Context（背景・課題）

GitHub Actions の `uses:` 参照は、タグ・ブランチ・コミット SHA のいずれの形式でも書ける：

```yaml
uses: actions/checkout@main                     # ブランチ
uses: actions/checkout@v5                       # メジャータグ（可動）
uses: actions/checkout@v5.0.1                   # 厳密タグ
uses: actions/checkout@93cb6efe...              # SHA（40 文字）
```

このうち**タグとブランチは Git の参照（reference）に過ぎず、メンテナがいつでも別コミットに付け替えられる**。具体的には：

- メンテナ権限を持つアカウント（メンテナ本人 / メンテナの PAT を盗んだ攻撃者 / 信頼を獲得した悪意ある協力者）が `git tag -d v5.0.1 && git tag v5.0.1 <悪意ある SHA> && git push --force` を実行すると、世界中の利用者の CI 設定を一切変えずに**次回ジョブから別コードが実行される**
- メジャータグ `@v5` は仕様上**意図的に動く**（新リリースのたびにメンテナが付け替える）ため、毎回中身が変わる前提で運用されている

実際に発生した事件：

- **2024-03 xz-utils**：2 年かけて信頼を獲得した協力者がメンテナ権限を得て、ビルド時に SSH 認証関数を破壊する backdoor を仕込んだ
- **2025-03 tj-actions/changed-files**：メンテナの PAT 漏洩で複数バージョンタグが同時に書き換えられ、数千リポジトリの CI で `GITHUB_TOKEN` 等のシークレットが漏洩

CI 環境はクラウド認証情報・デプロイキー・パッケージレジストリ書き込み権限などを保持するため、**Action の悪意あるコード 1 回の実行が組織の本番環境への侵入経路を直接渡す**ことになる。サプライチェーン攻撃の中でも特に被害が大きい部類。

GitHub 自身も Security hardening ガイドで以下を明示的に推奨している：

> Pinning an action to a full length commit SHA is currently the only way to use an action as an immutable release.

OpenSSF Scorecard でも `Pinned-Dependencies` 項目で SHA ピン止めを評価対象としている。

本リポジトリは [ADR 0026](./0026-github-actions-incremental-scope.md) で R0 から GitHub Actions を導入し、複数のサードパーティ Action に依存している。Python pivot（[ADR 0033](./0033-backend-language-pivot-to-python.md)）と mise 採用（[ADR 0039](./0039-mise-for-task-runner-and-tool-versions.md)）に伴い対象アクション群が拡大したため、本 ADR の方針で全件カバーする：

| アクション | 用途 | 関連 ADR |
|---|---|---|
| `actions/checkout` | リポジトリのチェックアウト | 横断 |
| `actions/setup-node` | Node.js セットアップ | [0018](./0018-biome-for-tooling.md) |
| `pnpm/action-setup` | pnpm セットアップ | [0036](./0036-frontend-monorepo-pnpm-only.md) |
| `jdx/mise-action` | mise + 全 tool 版数（Python / Go / uv 等）の統合セットアップ | [0039](./0039-mise-for-task-runner-and-tool-versions.md) |
| その他将来追加されるアクション | 例：`docker/build-push-action`、`hashicorp/setup-terraform` 等 | [0026](./0026-github-actions-incremental-scope.md) の段階拡張 |

> **注**：mise 採用後は **Python / Go / uv 等の個別 setup-action（`actions/setup-python` / `actions/setup-go` / `astral-sh/setup-uv`）は使わず**、`jdx/mise-action` 1 つに統合する方針。これにより SHA ピン止め対象アクション数を最小化できる。

## Decision（決定内容）

**サードパーティ Action は全て `<owner>/<repo>@<40 文字 SHA> # <バージョン>` 形式で参照する。** GitHub 公式 Action（`actions/*`）も例外なく対象とする。

```yaml
# Before
- uses: actions/checkout@v5

# After
- uses: actions/checkout@93cb6efe18208431cddfb8368fd83d5badbf9bfd # v5.0.1
```

### 適用対象

| 対象 | 取り扱い |
|---|---|
| サードパーティ Action（`actions/*` / `pnpm/*` 等） | **SHA ピン止め必須** |
| ローカル Composite Action（`./.github/actions/*`） | ピン止め対象外（リポジトリ自体の git 履歴で完結） |
| Reusable Workflow（`./.github/workflows/*.yml` の自リポジトリ呼び出し） | ピン止め対象外 |

### 運用上のセット要件

SHA ピン止めは **[ADR 0028](./0028-dependabot-auto-update-policy.md) の Dependabot 自動更新と必ずセット**で運用する。Dependabot が新バージョン検出時に SHA とバージョンコメントの両方を自動更新する PR を作成する。**SHA を人間が手で追従するのは現実的に不可能**（40 文字のハッシュを毎週書き換える運用は破綻する）であり、Dependabot 抜きでの SHA ピン止めは禁止とする。

### バージョンコメントの併記

`# v5.0.1` のコメントを SHA の右に必ず併記する。理由：

- SHA だけでは人間がパッと見でバージョンを判別できない
- Dependabot がバージョン文字列も合わせて更新する（コメント付きの慣習）
- レビュー時に「このバージョンは何を含むか」をリリースノートで確認しやすい

## Why（採用理由）

### SHA ピン止めを選ぶ理由

- **Git のオブジェクトモデル上、SHA は不変**：ハッシュ値はコミット内容そのものに対する数学的指紋であり、中身を 1 バイトでも変えると別の SHA になる。**フォースプッシュでも書き換えられない**（タグは指す先を変えられるが、SHA はその概念に該当しない）
- **fail-closed の防御**：攻撃者がタグを書き換えた場合、SHA ピン止めしている CI は「古い（安全な）コミットを引き続けるか、コミットが GC で消えていれば 404 で停止する」のいずれかになる。**悪意あるコードが実行される状態には絶対にならない**。一方タグ参照は最初から最後まで攻撃コードを実行し続ける
- **GitHub 公式の推奨**：[Security hardening for GitHub Actions](https://docs.github.com/en/actions/security-guides/security-hardening-for-github-actions#using-third-party-actions) が明示的に SHA ピン止めを唯一の不変参照手段として推奨
- **OpenSSF Scorecard 準拠**：OSS プロジェクトの健全性指標として確立されており、ポートフォリオとして見たときの説得力が高い
- **再現性・監査可能性**：「うちの CI で実行されているコードはこの SHA」と明示でき、SBOM・セキュリティレビュー時に追跡可能。1 年前のジョブを再実行しても同じバイナリ・同じ挙動

### GitHub 公式 Action（`actions/*`）も例外にしない理由

- **メンテナ権限の奪取は GitHub 社内アカウントでも起こり得る**：内部脅威・PAT 漏洩・乗っ取りリスクは GitHub 公式リポジトリでもゼロではない
- **規約に例外を作ると形骸化する**：「公式は OK、サードパーティは SHA」というルールは、新規メンバーが入った時に判断ぶれが出る。**全サードパーティ Action 一律 SHA**の方が記憶も適用も簡単
- **Dependabot は両方を等しく自動更新する**：例外を作らない方が運用コストも下がる

### Dependabot を前提とする理由

- **人間は 40 文字 SHA を覚えられない・更新できない**：手動運用すると数ヶ月で古い SHA が放置される
- **Dependabot は SHA とバージョンコメントを正しく書き換える**：自動 PR は CI 通過 → レビュー → マージで完結
- **SHA ピン止めだけ入れて Dependabot を入れないのは最悪**：脆弱性パッチが取り込めず、古い不変参照に閉じ込められる

### ローカル Action / Reusable Workflow を対象外とする理由

- **同一リポジトリ内なので git 履歴で完結**：`./.github/actions/setup-node-pnpm` のようなローカル参照は、CI ジョブの `actions/checkout` で取得したコミット（PR の HEAD ）と同じ参照を持つ
- **タグ書き換え攻撃の経路が存在しない**：自リポジトリのコードは PR レビューを経て main に入るため、外部メンテナによる差し替えが起きない

## Alternatives Considered（検討した代替案）

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| A. ブランチ参照（`@main`） | 常に最新を引く | 毎回中身が変わるため再現性なし。攻撃者が main に push すれば即座に汚染 |
| B. メジャータグ（`@v5`） | v5 系の最新 | 仕様上**意図的に動く**可動参照。書き換え攻撃にも完全に無防備 |
| C. 厳密タグ（`@v5.0.1`） | バージョン固定 | タグはフォースプッシュで書き換え可能。tj-actions 事件の被害形態そのもの |
| D. SHA ピン止め + 手動更新 | SHA で固定し、人間が定期的に更新 | 40 文字 SHA を毎週手で追従するのは現実的に不可能。古い SHA が放置されて脆弱性が残る |
| E. **SHA ピン止め + Dependabot（採用）** | SHA で固定、Dependabot が自動更新 PR 作成 | 不変参照と更新追従の両立、運用コスト最小 |
| F. Tag protection rules に依存 | サードパーティ側のタグ保護に期待 | オプトイン機能で利用者側からは検証不能。メンテナ権限奪取時には保護も無効化される |

## Consequences（結果・トレードオフ）

### 得られるもの

- **サプライチェーン攻撃耐性**：タグ書き換え攻撃を構造的に無効化（fail-closed）
- **再現性**：1 年前のジョブを再実行しても同じコードが動く
- **監査可能性**：実行コードが SHA で一意に特定できる
- **OpenSSF Scorecard の `Pinned-Dependencies` を満たす**：OSS としての健全性指標を満たす
- **ポートフォリオ価値**：採用担当者・面接官に対して「サプライチェーン攻撃の脅威モデルを理解している」ことを示せる

### 失うもの・受容するリスク

- **可読性低下**：`@v5` より `@93cb6efe... # v5.0.1` の方が一目でバージョンが分からない（バージョンコメントで緩和）
- **Dependabot への依存**：Dependabot が止まると SHA が古いまま放置される。逆に言うと Dependabot の継続運用が前提条件
- **PR ノイズの増加**：[ADR 0028](./0028-dependabot-auto-update-policy.md) で受容済みだが、SHA 更新 PR が定期的に上がる
- **`uses:` の SHA 取得手間**：新しい Action を追加する時に GitHub のリリースページから SHA をコピーする手作業が発生（初回のみ、以降は Dependabot が更新）
- **GC によるコミット消失リスク**：タグ書き換えで参照が外れた古いコミットは GitHub の GC で 90 日後を目安に消える。Dependabot で定期更新していれば消える前に追従可能だが、放置すると CI が 404 で停止する（fail-closed の副作用）

### 将来の見直しトリガー

- **GitHub が Sigstore / Artifact Attestation 等の新しい不変参照手段を提供したら**：SHA より検証性の高い手段が出れば移行検討
- **Renovate に移行する場合**（[ADR 0028](./0028-dependabot-auto-update-policy.md) と連動）：Renovate も同様に SHA ピン止めをサポートするので方針自体は維持
- **Tag protection rules + immutable releases が GitHub で標準化された場合**：それでも SHA ピン止めの方が防御として強いため、原則維持
- **依存する Action 数が増えて Dependabot PR が捌けなくなった場合**：グループ化や `cooldown` 設定で対応

## References

- [.github/workflows/ci.yml](../../.github/workflows/ci.yml)：本 ADR の実装
- `.github/actions/setup-node-pnpm/action.yml`：本 ADR の実装（CI 整備時に composite action として投入予定）
- [ADR 0026: GitHub Actions の段階拡張](./0026-github-actions-incremental-scope.md)（SHA ピン止めはこの一部）
- [ADR 0028: Dependabot 自動更新ポリシー](./0028-dependabot-auto-update-policy.md)（SHA ピン止めの運用前提）
- [ADR 0039: タスクランナー兼 tool 版数管理に mise を採用](./0039-mise-for-task-runner-and-tool-versions.md)（jdx/mise-action 採用の根拠）
- [ADR 0033: バックエンドを Python に pivot](./0033-backend-language-pivot-to-python.md)（対象アクション拡張の契機）
- [GitHub Docs: Security hardening for GitHub Actions](https://docs.github.com/en/actions/security-guides/security-hardening-for-github-actions#using-third-party-actions)
- [OpenSSF Scorecard: Pinned-Dependencies](https://github.com/ossf/scorecard/blob/main/docs/checks.md#pinned-dependencies)
- [tj-actions/changed-files supply chain attack（2025-03）](https://www.stepsecurity.io/blog/harden-runner-detection-tj-actions-changed-files-action-is-compromised)：実例
