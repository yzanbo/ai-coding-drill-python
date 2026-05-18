# internal/sandbox

## とは何か

問題生成の**模範解答検証**用に、使い捨て Docker コンテナを Go コードから操作する package。公式 SDK（`github.com/docker/docker/client`）を使ってコンテナを「作る → 動かす → 結果を取る → 壊す」のサイクルを 1 回ずつ繰り返す（[ADR 0009](../../../../docs/adr/0009-disposable-sandbox-container.md)）。

## generation Worker での使い方

- LLM が生成した問題には**模範解答**が付随する
- その模範解答が「実際にテストを通るか」をサンドボックスで実行して確かめる（自分の生成物を自分で検証する多層防御の一環、[03-llm-pipeline.md](../../../../docs/requirements/2-foundation/03-llm-pipeline.md)）
- 失敗したら問題そのものに欠陥があるとみなし、生成をやり直す or 「問題を弾く」判断をする

## grading worker と同じ image を使う

- grading: 受験者の解答コードを test と一緒に動かす（vitest run）
- generation: LLM が作った模範解答を sandbox で実行して動作確認する
- どちらも「TS コードを隔離環境で走らせる」用途で同じ `ai-coding-drill-sandbox:latest` image を起動する
- image の Dockerfile を所有しているのは grading 側（[apps/workers/grading/sandbox/Dockerfile](../../../grading/sandbox/Dockerfile)）。generation は Docker SDK から同 image 名を起動するだけで、自前の Dockerfile を持たない（重複所有しない、[ADR 0040](../../../../docs/adr/0040-worker-grouping-and-llm-in-worker.md)）

## 役割

- Docker クライアント生成：`client.NewClientWithOpts(client.FromEnv, client.WithAPIVersionNegotiation())`
- コンテナの作成・実行・破棄サイクル
- 隔離設定の強制適用（下記）
- ホストの Docker daemon を `/var/run/docker.sock` 経由で叩く（DooD、[ADR 0045](../../../../docs/adr/0045-sandbox-container-runtime-dood.md)、DinD は使わない）
- 結果パース：vitest の JSON reporter 出力を構造化する（多言語対応時は言語別 adapter で差し替え）

## 強制制約

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

## 関連

- 規約 SSoT：[.claude/rules/worker.md「サンドボックス操作」セクション](../../../../.claude/rules/worker.md)
- 隔離原則：[ADR 0009](../../../../docs/adr/0009-disposable-sandbox-container.md)
- DooD vs DinD：[ADR 0045](../../../../docs/adr/0045-sandbox-container-runtime-dood.md)
- image 定義：[apps/workers/grading/sandbox/Dockerfile](../../../grading/sandbox/Dockerfile)（grading 所有、generation も同 image を共有）
