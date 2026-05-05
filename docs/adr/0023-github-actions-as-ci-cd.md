# 0023. CI/CD ツールに GitHub Actions を採用

- **Status**: Accepted
- **Date**: 2026-05-05
- **Decision-makers**: 神保 陽平

## Context（背景・課題）

[ADR 0022](./0022-github-actions-incremental-scope.md) で「CI のスコープを段階拡張する」という方針は決めたが、**そもそもどの CI/CD ツールを採用するか** という選定判断自体は明文化されていない。

CI/CD ツールは大きく以下の三類型に分かれる：

1. **コードホスト統合型**：GitHub Actions / GitLab CI/CD / Bitbucket Pipelines
2. **独立 SaaS 型**：CircleCI / Buildkite / Travis CI / Drone CI / Semaphore / Earthly Cloud / Dagger
3. **セルフホスト型**：Jenkins / Tekton / Argo Workflows / Woodpecker CI / GitHub Actions Self-hosted Runner

このプロジェクトの前提：

- **コードホストは GitHub**（`yzanbo/ai-coding-drill`）
- **個人開発・ポートフォリオ用途**：運用に割けるリソースは最小限
- **想定ピーク負荷は小〜中規模**：日次 PR 数は 1 桁、ビルド対象は TS モノレポ + Go ワーカー
- **クラウドは AWS 単独**（[ADR 0002](./0002-aws-single-cloud.md)）
- **R0〜R2 では Linux ランナーで十分**（macOS / Windows ビルドの予定なし）

## Decision（決定内容）

**CI/CD ツールに GitHub Actions を採用する。** デプロイ（CD）部分も当面は GitHub Actions 上で完結させる。

- ワークフローは `.github/workflows/` 配下に配置し、SSoT は `ci.yml`（[ADR 0022](./0022-github-actions-incremental-scope.md)）
- ランナーは `ubuntu-latest`（GitHub-hosted）を既定とする
- AWS への認証は `aws-actions/configure-aws-credentials` で OIDC を使う（長期 IAM キーをシークレットに保存しない）
- 個別領域で専用ツールに切り出す可能性は将来再評価する（下記「将来の見直しトリガー」）

## Why（採用理由）

- **コードホストとの統合が最強**：PR の Checks タブ・`gh` CLI・Codespaces・Dependabot・Issue / PR の status との連携が GitHub Actions だけでネイティブに動く。他社 SaaS では Webhook 経由で同等のことはできるが、設定とメンテが増える
- **無料枠が個人プロジェクトに十分**：Public リポジトリなら分数無制限、Private でも 2,000 分/月（Linux 換算）で R0〜R2 規模は余裕。CircleCI（6,000 分）の方が分数は多いが、Public で無制限な GitHub Actions が結局有利
- **Marketplace の資産量**：`pnpm/action-setup` / `actions/setup-node` / `aws-actions/configure-aws-credentials` / `docker/build-push-action` 等、必要なものはほぼ公式または広く使われたアクションで揃う。自作のスクリプトを最小化できる
- **YAML 1 セットでロックインが弱い**：移行が必要になっても、ワークフロー定義は CircleCI / GitLab CI 等にほぼ機械的に書き換え可能。可逆な判断
- **採用担当者向けの可視性**：ポートフォリオ用途では PR の Checks がそのまま見られることが副次的価値を持つ
- **OIDC で AWS にキーレス認証可能**：長期シークレットを GitHub に置かずに `sts:AssumeRoleWithWebIdentity` で AWS に入れる。セキュリティ面で他社 SaaS と差はないが、設定の標準化が進んでいる
- **CD も同じ場所で完結する**：個人規模では CI と CD を別ツールに分けるメリット（権限分離・承認フローの厳格化）が運用コストに見合わない

## Alternatives Considered（検討した代替案）

| 候補 | 種別 | 概要 | 採用しなかった理由 |
|---|---|---|---|
| **CircleCI** | 独立 SaaS | 設定の柔軟性、orbs、Docker レイヤキャッシュが優秀、6,000 分/月 | GitHub Actions との機能差が小さい一方、SaaS が増える運用コストとアカウント分散コストが上回る |
| **GitLab CI/CD** | コードホスト統合 | `.gitlab-ci.yml` 単一ファイル、CI/CD 機能は非常に高い | コードホストが GitHub のため対象外。GitLab に移る理由がない |
| **Bitbucket Pipelines** | コードホスト統合 | Atlassian 統合 | 同上 |
| **Buildkite** | 独立 SaaS（ハイブリッド） | Agent セルフホスト + SaaS コントロールプレーン、大規模並列向け | 個人規模では完全にオーバースペック、無料枠が限定的 |
| **Travis CI** | 独立 SaaS | かつての OSS 標準 | OSS 用途で衰退、後発を選ぶ理由なし |
| **Drone CI / Woodpecker CI** | 独立 SaaS / OSS | Docker ネイティブ、軽量 | セルフホスト前提だと運用コストが見合わない |
| **Earthly Cloud** | 独立 SaaS | `Earthfile` でビルドを宣言、ローカルと CI で同じスクリプト | ビルド再現性は魅力だが、本プロジェクト規模では学習コストが上回る。R3 以降にビルド再現性が課題化したら再評価 |
| **Dagger** | パイプライン記述基盤 | コードでパイプラインを書く（SDK 経由）、CI ツール非依存 | 概念的には正しい方向だが、現時点では学習コストと採用事例の薄さが上回る |
| **Jenkins** | セルフホスト OSS | プラグイン資産膨大、何でもできる | サーバ運用負荷が個人規模に見合わない。プラグイン更新追従コストも高い |
| **Tekton / Argo Workflows** | セルフホスト OSS | k8s ネイティブ | k8s クラスタを採用していない（[ADR 0008](./0008-disposable-sandbox-container.md) では ECS/Fargate 想定）ので前提が成り立たない |
| **GitHub Actions Self-hosted Runner** | セルフホスト | Actions の YAML のまま、ランナーだけ自前 | 無料枠超過の兆候はなく、現時点では運用負荷を負う理由がない |
| **AWS CodePipeline / CodeDeploy（CD のみ切り出し）** | クラウドネイティブ | AWS への ECS / Lambda デプロイ統合 | Actions の `aws-actions/*` でほぼ同等のことが可能。ツール 2 本に分ける運用負荷の方が大きい |
| **Terraform Cloud / Atlantis（CD のうち IaC のみ切り出し）** | IaC 専用 | plan/apply の承認フロー、状態管理 | R3 以降 `infra/` 着手時に再評価する。R0〜R2 の段階で先取りで導入する理由がない |
| **ArgoCD / Flux / Spinnaker** | k8s GitOps | k8s クラスタへの宣言的デプロイ | k8s 不採用のため前提が成り立たない |

## Consequences（結果・トレードオフ）

### 得られるもの

- ワークフロー定義 1 セットで CI/CD を統一管理できる
- PR Checks・`gh` CLI・Dependabot との統合が自動で揃う
- Public リポジトリなら CI コストはゼロ、Private でも無料枠で当面まかなえる
- OIDC で AWS にキーレス認証でき、長期シークレットの管理が不要

### 失うもの・受容するリスク

- **GitHub 障害時に CI/CD が止まる**：コードホストと CI が同一ベンダーなので、GitHub 全体障害の影響を二重に受ける（独立 SaaS 採用なら CI だけは動かせる可能性がある）
- **macOS ランナーは 10 倍、Windows は 2 倍消費**：将来クロスプラットフォームビルドが必要になると分数消費が膨らむ
- **複雑なワークフロー DSL を書きにくい**：YAML ベースなので、条件分岐・再利用が増えると見通しが落ちる（reusable workflows / composite actions で緩和は可能だが限界あり）
- **Self-hosted Runner を使う場合の運用負荷**：将来必要になればその時点で運用コストが発生

### 将来の見直しトリガー

- **macOS / Windows ランナーが恒常的に必要になり、無料枠を圧迫した時点** → Self-hosted Runner / CircleCI を比較検討
- **ワークフローの複雑化が YAML の限界を超えた時点** → Dagger（コードベース記述）を比較検討
- **ビルドのローカル再現性が問題化した時点** → Earthly を比較検討
- **`infra/` 着手時に Terraform の plan/apply 管理を厳格化したくなった時点** → Terraform Cloud / Atlantis を CD レイヤに追加検討
- **GitHub 障害の影響が事業上致命的になった時点**（個人プロジェクトでは想定しないが）→ 独立 SaaS への分離検討

## References

- [ADR 0002](./0002-aws-single-cloud.md)：AWS 単独クラウドの前提
- [ADR 0018](./0018-phase-0-tooling-discipline.md)：補完ツールを R0 から導入
- [ADR 0022](./0022-github-actions-incremental-scope.md)：CI スコープの段階拡張方針（本 ADR の前提）
- [.github/workflows/ci.yml](../../.github/workflows/ci.yml)：本 ADR の実装
- [GitHub Actions の料金体系](https://docs.github.com/ja/billing/managing-billing-for-your-products/managing-billing-for-github-actions/about-billing-for-github-actions)
- [`aws-actions/configure-aws-credentials`（OIDC 連携）](https://github.com/aws-actions/configure-aws-credentials)
