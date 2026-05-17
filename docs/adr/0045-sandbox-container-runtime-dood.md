# 0045. 採点 Worker のサンドボックスコンテナ起動方式に DooD（ホスト Docker socket 共有）を採用、DinD は不採用

- **Status**: Accepted
- **Date**: 2026-05-17
- **Decision-makers**: 神保

## Context（背景・課題）

採点 Worker は **ユーザーコードを隔離コンテナ内で実行する**（→ [ADR 0009](./0009-disposable-sandbox-container.md)）。Worker 自身もコンテナとしてデプロイされるため、「Worker コンテナがサンドボックスコンテナをどう起動するか」というネスト構造の選択が発生する。

選択肢は概ね 3 系統：

1. **DooD（Docker outside of Docker）**：ホストの `/var/run/docker.sock` を Worker コンテナにマウントし、Worker から **ホスト Docker daemon** に直接 API リクエストを投げる
2. **DinD（Docker in Docker）**：Worker コンテナ内にもう一つ Docker daemon を立て、その中でサンドボックスコンテナを動かす
3. **代替ランタイム**：Podman rootless / gVisor `runsc` / Kata Containers / Firecracker など Docker 以外の runtime を選ぶ

この決定は **セキュリティモデルそのもの**：DooD はホスト Docker socket を Worker に渡すため「Worker = ホスト root と同等の権限」を持つことになり、後から DinD・rootless・gVisor 等に変える際は Worker 内の `sandbox` パッケージ（`apps/workers/grading/internal/sandbox/runner.go`）の I/F まで影響する。

既存の関連 ADR：

- [ADR 0009](./0009-disposable-sandbox-container.md)：採点コンテナを使い捨て方式にする決定。**起動主体（Worker → どの daemon → サンドボックスコンテナ）の選択は未決定**で本 ADR の守備範囲
- [ADR 0016](./0016-go-for-grading-worker.md)：Worker を Go で実装。Docker SDK（`github.com/docker/docker/client`）が成熟していることが採用根拠の一つ
- [.claude/rules/worker.md: Docker クライアント（DooD）](../../.claude/rules/worker.md)：DooD の旨と DinD 不採用を 1 行で記述（採用根拠なし）

## Decision（決定内容）

**採点 Worker はホスト Docker daemon の `/var/run/docker.sock` をコンテナにマウントし、Docker SDK 経由でサンドボックスコンテナを起動する（DooD 方式）。Docker in Docker（DinD）は採用しない。**

### 構成

- Worker コンテナ（`apps/workers/grading`）の `docker run` / Compose / ECS Task Definition で `/var/run/docker.sock:/var/run/docker.sock` をマウント
- Worker は `client.NewClientWithOpts(client.FromEnv, ...)` でホスト Docker に接続
- サンドボックスコンテナは Worker の **兄弟コンテナ**として起動する（親子ではない）。ホスト Docker から見ると Worker と並列の同階層

### ホスト分離（最小権限原則の運用）

- 採点 Worker は **専用の EC2 VM**（または ECS タスク）に住み、他アプリ（FastAPI / Frontend / DB）と Docker daemon を共有しない（→ [02-architecture.md: インフラの論理配置](../requirements/2-foundation/02-architecture.md#インフラの論理配置)）
- FastAPI には `docker.sock` を **絶対に渡さない**（API 経由のコード実行を物理的に不可能にする）
- 採点 Worker 専用 VM はサンドボックスコンテナ用の cgroups / seccomp / AppArmor プロファイルを敷く（→ [01-non-functional.md: セキュリティ](../requirements/2-foundation/01-non-functional.md#セキュリティ最重要)）

### 段階的隔離強化との関係

サンドボックス自体の隔離強度は [ADR 0009](./0009-disposable-sandbox-container.md) の段階計画（Docker → gVisor → Firecracker）に従う。**本 ADR は起動主体（DooD vs DinD vs 代替）の選択に閉じ、隔離強度（コンテナ runtime）の選択とは直交**する：

- 段階 1（R1〜R2）：DooD + Docker runc → Worker からホスト Docker でランチ
- 段階 2（R3）：DooD + Docker + gVisor runtime → Worker からホスト Docker（runtime=runsc）でランチ
- 段階 3（R9）：DooD + Firecracker（firecracker-containerd 経由）→ Worker からホスト Docker でランチ

すべての段階で **「Worker は docker.sock を握る、サンドボックスは兄弟コンテナとして launch」** という DooD 方式を維持する。

## Why（採用理由）

### 1. 起動オーバーヘッド最小（DinD の追加レイヤを避ける）

- DinD は Worker コンテナ内に追加で Docker daemon を立てるため、初回起動コスト + 各コンテナ起動時のネスト overhead が乗る
- DooD は **ホスト daemon に直接 API を投げる**ため、コンテナ起動コスト = ホスト Docker の通常コストのみ
- [ADR 0009](./0009-disposable-sandbox-container.md) で「起動 ~200ms（段階 1）→ 段階 2 以降も上限 500ms」を目標としており、ネスト overhead は許容できない

### 2. Storage driver の二重化を避ける

- DinD は **Worker コンテナの overlay 上でさらに overlay** を重ねる構造になり、storage driver の警告・パフォーマンス劣化・カーネル制約（古い overlayfs では nest 不可）が発生しやすい
- DooD はホスト storage driver 1 段のみで、ECS / Fargate / EC2 すべての環境で安定動作する

### 3. オペレーション単純化（Docker daemon が 1 個）

- ログ / メトリクス / イメージキャッシュ / バックグラウンド GC（`docker system prune`）の対象が **ホスト Docker 1 つだけ**で済む
- DinD だと Worker 内 daemon のログ取得・残骸イメージの掃除を Worker 内側で別管理する必要があり、運用負荷が増える
- 1 人運用前提（→ [ADR 0032](./0032-github-repository-settings.md)）と合致

### 4. Go SDK との親和性

- `github.com/docker/docker/client` は `client.FromEnv` でソケット接続を解決し、DooD と相性が良い
- DinD でも動くが、Worker コンテナ内で daemon の起動順序を待つ初期化処理を自前で書く必要があり、本質でない複雑度が増える

### 5. AWS デプロイモデルとの整合

- 採点 Worker は **EC2 Spot Instance 専用 VM**で動かす計画（→ [05-runtime-stack: ホスティング](../requirements/2-foundation/05-runtime-stack.md#ホスティングaws)、[ADR 0002](./0002-aws-single-cloud.md)）。VM 上で Docker Engine が動き、Worker はそのコンテナとして実行されるため、`docker.sock` 共有は AWS 標準パターン
- ECS Fargate は `docker.sock` を許さないため、採点 Worker は Fargate ではなく EC2 を選択（API / 他の Worker は Fargate 可）。この棲み分けは [ADR 0040](./0040-worker-grouping-and-llm-in-worker.md) の Worker 分離方針と整合

### 6. セキュリティリスクは「Worker 専用 VM + API 分離」で受容可能

- DooD の本質的リスク：`docker.sock` を持つプロセス = ホストの root 同等。サンドボックスを脱獄したコードが Worker プロセスを乗っ取ると、ホスト全体を制御できる
- このリスクは以下で受容範囲に収まる：
  - 採点 Worker 専用 VM（FastAPI / Frontend / DB と物理的に分離、データ漏洩面なし）
  - API には `docker.sock` を渡さない（脱獄しても API 経由で他リソースに到達不可）
  - サンドボックス側で `--network none` / `--read-only` / `--cap-drop ALL` / 非 root / seccomp プロファイルで脱獄自体を困難化（→ [.claude/rules/worker.md: 採点コンテナの制約](../../.claude/rules/worker.md)）
  - 段階 2（gVisor）でシステムコール層の追加防御を入れる計画あり（→ [ADR 0009](./0009-disposable-sandbox-container.md)）
- ポートフォリオ規模（個人プロジェクト、外部ユーザーは少数）であり、攻撃面が小さい

## Alternatives Considered（検討した代替案）

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| **DooD（ホスト socket 共有）** | Worker に `docker.sock` をマウント、ホスト Docker daemon に直接 API | （採用） |
| **DinD（Docker in Docker）** | Worker コンテナ内に Docker daemon を内包、サンドボックスを孫コンテナとして起動 | 起動 overhead 増、storage driver 二重化、運用対象 daemon が増える、Go SDK の初期化複雑化 |
| **Podman rootless（DinD 的）** | rootless で動作する Podman を Worker 内に内包 | Podman API は Docker と互換だが Go SDK は `github.com/docker/docker/client` ほど成熟していない、Spot Instance の AMI から Podman セットアップする運用負荷、AWS デフォルトとの非整合 |
| **gVisor runsc を Worker 内 runtime に**（DinD 内に gVisor） | DinD + gVisor runtime | DinD の弱点を引き継ぐ、しかも段階 2 ロードマップ（→ [ADR 0009](./0009-disposable-sandbox-container.md)）は DooD + gVisor で達成可能 |
| **Kata Containers（VM ベース runtime）** | runtime そのものを VM 化 | Spot Instance への VM-in-VM がコスト / 互換性で重く、規模に対して過剰 |
| **Firecracker microVM 直接呼び出し**（Docker を介さない） | firecracker-containerd / ignite | R9 ロードマップ。MVP では DooD + Docker で十分（→ [ADR 0009](./0009-disposable-sandbox-container.md) §将来トリガー） |
| **Sandbox を Lambda で実行**（コンテナ非依存） | サーバレスサンドボックス | Lambda は実行時間 15 分上限・起動コスト大・カスタム runtime 制約があり、採点用途には不適。Worker → Lambda の I/F が Postgres ジョブキューと整合しない |

## Consequences（結果・トレードオフ）

### 得られるもの

- 起動 overhead 最小（ネストなし、Storage driver も 1 段）
- 運用対象 Docker daemon は 1 個のみ（ログ・GC・メトリクスが一元化）
- Go SDK の標準パターン（`client.FromEnv`）で接続でき、Worker コードがシンプル
- ホスト Docker のイメージキャッシュを共有でき、サンドボックスイメージ pull が高速
- AWS EC2 上の Docker daemon と自然に統合（Spot Instance + ECR + AMI で標準デプロイ）
- 段階 2（gVisor）/ 段階 3（Firecracker）への移行時も DooD 方式を維持できる（runtime 層の変更で吸収）

### 失うもの・受容するリスク

- **`docker.sock` を握る Worker は実質ホスト root 同等**：サンドボックスを脱獄したコードが Worker プロセスを取れば、ホスト全体を制御できる
  - **対策**：採点 Worker 専用 VM（他アプリと分離）、API への socket 提供禁止、サンドボックス側の脱獄困難化（`--cap-drop ALL` / 非 root / seccomp / `--network none`）、段階 2 で gVisor 追加防御
- **マルチテナント運用（他プロジェクトと同居）には向かない**：Worker と同じ VM に他人のコードが居る構成は禁止
  - **対策**：採点 Worker 専用 VM を不変条件として運用ドキュメントに明記
- **Worker と DB 接続情報を同じプロセス空間で扱う**ため、Worker 自身の脆弱性は厳重に管理する必要がある
  - **対策**：Worker は HTTP 公開せず（ヘルスチェック程度のみ）、攻撃面を最小化
- **将来 SaaS 化したい場合は本 ADR の見直しが必須**：マルチテナント = DooD は採用不可

### 将来の見直しトリガー

- **採点機能を SaaS として外部公開**：マルチテナント運用が必要になった時点で、DinD + rootless / gVisor を Worker 内 runtime にする方式 / Firecracker microVM への移行を再検討
- **Worker 自身を Fargate に載せたい**：Fargate は `docker.sock` 共有不可なので、Firecracker か Kata + 別 API 経由になる。R5 仕上げ・公開で運用負荷が ECS Fargate 統一の方が安いと判明したら見直し
- **ホスト Docker daemon の脆弱性（CVE）が頻発**：daemon を Worker から分離する別方式（remote Docker / 専用 API ゲートウェイ）を検討
- **マルチテナント化の事業要件発生**：個人ポートフォリオから本格 SaaS にピボットする場合

## References

- [ADR 0002](./0002-aws-single-cloud.md) — AWS 単独クラウド方針
- [ADR 0009](./0009-disposable-sandbox-container.md) — 使い捨てサンドボックス方式（本 ADR と直交、起動主体ではなく寿命の選択）
- [ADR 0016](./0016-go-for-grading-worker.md) — Worker を Go で実装、Docker SDK 採用根拠
- [ADR 0040](./0040-worker-grouping-and-llm-in-worker.md) — Worker のグルーピング、Backend は LLM / Docker 呼ばない
- [02-architecture.md: サンドボックスランナー](../requirements/2-foundation/02-architecture.md#サンドボックスランナーappsworkersgrading-内で実行)
- [02-architecture.md: インフラの論理配置](../requirements/2-foundation/02-architecture.md#インフラの論理配置) — 採点 Worker 専用 VM の根拠
- [01-non-functional.md: セキュリティ](../requirements/2-foundation/01-non-functional.md#セキュリティ最重要)
- [.claude/rules/worker.md: Docker クライアント（DooD）](../../.claude/rules/worker.md) — 実装契約 SSoT
- [Docker docs: Bind mount the docker.sock](https://docs.docker.com/reference/cli/dockerd/) — DooD の正式名称は無く「socket mount」と表現される
