# internal/sandbox

## とは何か

採点 / 生成検証用の **使い捨て Docker コンテナ**を Go コードから操作する package。公式 SDK（`github.com/docker/docker/client`）を使ってコンテナを「作る → 動かす → 結果を取る → 壊す」のサイクルを 1 回ずつ繰り返す（[ADR 0009](../../../../docs/adr/0009-disposable-sandbox-container.md)）。

## 両 Worker で同じ image を起動する

- grading: 受験者の解答コードを test と一緒に動かす（vitest run）
- generation: LLM が作った模範解答を sandbox で実行して動作確認する
- どちらも「TS コードを隔離環境で走らせる」用途で同じ `ai-coding-drill-sandbox:latest` image を起動する
- image の Dockerfile を所有しているのは grading 側（[apps/workers/grading/sandbox/Dockerfile](../../sandbox/Dockerfile)）。generation は Docker SDK から同 image 名を起動するだけで、自前の Dockerfile を持たない（重複所有しない、[ADR 0040](../../../../docs/adr/0040-worker-grouping-and-llm-in-worker.md)）

## 役割

- Docker クライアント生成：`client.NewClientWithOpts(client.FromEnv, client.WithAPIVersionNegotiation())`
- コンテナの作成・実行・破棄サイクル
- 隔離設定の強制適用（下記）
- ホストの Docker daemon を `/var/run/docker.sock` 経由で叩く（DooD、[ADR 0045](../../../../docs/adr/0045-sandbox-container-runtime-dood.md)、DinD は使わない）
- 結果パース：vitest の JSON reporter 出力を構造化する（多言語対応時は言語別 adapter で差し替え）

## 採点コンテナの強制制約

すべてのコンテナで以下を必ず設定：

- `--network none`：ネットワーク完全遮断
- `--memory 256m` / `--cpus 0.5`：リソース上限
- `--read-only` + `--tmpfs /tmp:rw,size=64m`：ルート FS は読み取り専用、書き込みは /tmp のみ
- `--user 1000:1000`：非 root 実行
- 実行タイムアウト 5 秒

## やってはいけないこと

- ホストの volume を **生のまま mount**：必ず tmpfs mount + read-only mount を使う（[worker-layers.md §E §10](../../../../docs/requirements/5-roadmap/r0-setup/worker-layers.md)）
- ネットワークを `none` 以外にする：外部 API 呼び出しは Worker プロセス側（`internal/llm/`）で行う、サンドボックス内で行わない
- 同じコンテナを複数ジョブで使い回す：1 ジョブ 1 コンテナ、終わったら必ず `Remove`（漏れると `recover()` 内 / `defer` で回収）
- DinD（Docker in Docker）を使う：パフォーマンス・セキュリティ両面で劣るため不採用（[ADR 0045](../../../../docs/adr/0045-sandbox-container-runtime-dood.md)）
- `apps/workers/generation/sandbox/Dockerfile` を作る：grading の image を共有起動する（[worker-layers.md §E §9](../../../../docs/requirements/5-roadmap/r0-setup/worker-layers.md)）

## SDK 選定（moby/moby/client）

Docker daemon を叩く Go SDK は **`github.com/moby/moby/client`**（v0.4 系）を使う。`github.com/docker/docker/client` は同一コードの旧 module path だが、2026-05 時点で以下 2 件の脆弱性が **全バージョン未修正**（fix は `moby/moby/v2 >= v2.0.0-beta.8` 側へ反映済み、`docker/docker` 側への伝播待ち）のため不採用：

- **GO-2026-4887**：Moby has AuthZ plugin bypass when provided oversized request bodies
- **GO-2026-4883**：Moby has an Off-by-one error in its plugin privilege validation

`moby/moby/client` は別 module で advisory の影響範囲外。API も `NewClientWithOpts` → `New`（deprecated を引き継ぎ）、`ContainerCreate(opts)` の options-struct 化など差分はあるが、本 Worker のユースケース（create / start / wait / logs / stop / remove）ではほぼ等価に書ける。

`docker/docker` への切り戻しは、fix が `docker/docker` 側にも伝播し `mise run worker:grading:audit` で no vulnerabilities が出るバージョンが released されてから検討する。

## 関連

- 規約 SSoT：[.claude/rules/worker.md「サンドボックス操作」セクション](../../../../.claude/rules/worker.md)
- 隔離原則：[ADR 0009](../../../../docs/adr/0009-disposable-sandbox-container.md)
- DooD vs DinD：[ADR 0045](../../../../docs/adr/0045-sandbox-container-runtime-dood.md)
- image 定義：[apps/workers/grading/sandbox/Dockerfile](../../sandbox/Dockerfile)
