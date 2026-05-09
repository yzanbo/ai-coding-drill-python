# 0040. Worker を apps/workers/<name>/ 配下にグループ化し、LLM 呼び出しを Worker に集約する

- **Status**: Accepted
- **Date**: 2026-05-09
- **Decision-makers**: 神保 陽平

## Context（背景・課題）

[ADR 0003](./0003-phased-language-introduction.md) で 3 層ポリグロット構成（Python Backend / TS Frontend / Go Worker）を確定し、[ADR 0016](./0016-go-for-grading-worker.md) で採点ワーカーを Go で実装する判断を行った。当初の設計（Python pivot 前後とも）は **採点ワーカー 1 個（grading-worker）のみ**で、LLM 呼び出しは Backend（apps/api）が同期的に行う想定だった。

実装着手段階で以下の課題が顕在化：

1. **LLM 呼び出しの同期 API 配置の問題**：
   - 問題生成（problem generation）は LLM 呼び出しで数秒〜数十秒かかる
   - API リクエストとして同期処理すると HTTP タイムアウト（cloudflare / ALB のデフォルト 30〜60 秒）に抵触するリスク
   - フロントエンドの UX：ユーザがリクエスト後ただ待機する、進捗表示が困難
   - LLM 失敗時のリトライ戦略が API 同期では実装が複雑（リクエスト本体を再試行する必要）

2. **採点との一貫性**：
   - 採点ジョブは [ADR 0004](./0004-postgres-as-job-queue.md) のジョブキュー（SKIP LOCKED）+ Worker パターンで非同期実行している
   - 採点は LLM-as-a-Judge（[ADR 0008](./0008-custom-llm-judge.md)）で LLM を呼び、サンドボックス実行（[ADR 0009](./0009-disposable-sandbox-container.md)）で Docker を起動する
   - **採点も問題生成も「外部 I/O が支配的、数秒〜数十秒、リトライ可能」という同じ性質**を持つ
   - 同じ非同期ジョブパターンを適用するのが自然

3. **Worker 単一前提の限界**：
   - `apps/grading-worker/` の単一 Go module 構成は、種別の異なる Worker（採点 / 問題生成 / 将来の分析パイプライン等）を追加する場合の構造が未確定
   - 種別ごとに依存パッケージが異なる可能性があり、単一 module で全部を抱えると不要な依存巻き込みが起きる
   - Worker のディレクトリ命名規則（`grading-worker` / `generation-worker` 等のフラット配置 vs グループ配下）を決めておく必要

4. **LLM プロンプトの所在**：
   - 旧設計：`packages/prompts/`（generation + judge を共有パッケージ化）
   - 「**そのプロンプトを実際に LLM 呼び出しに使うのは誰か**」という観点では、generation も judge も Worker が消費者になる（本 ADR の決定後）
   - 共有パッケージとして root に置くより、消費する Worker 内に閉じるほうが自然

## Decision（決定内容）

### 1. Worker のディレクトリ構造を `apps/workers/<name>/` グループ配下に変更

```
apps/
├── api/                   Python（FastAPI、auth / CRUD / job enqueue のみ）
├── web/                   TypeScript（Next.js）
└── workers/
    ├── grading/           Go（採点 + judge LLM、ADR 0016 を継承）
    │   ├── go.mod
    │   ├── cmd/
    │   ├── internal/
    │   └── prompts/
    │       └── judge/
    │           └── quality.v1.yaml
    └── generation/        Go（問題生成 LLM、本 ADR で新設）
        ├── go.mod
        ├── cmd/
        ├── internal/
        └── prompts/
            └── generation/
                └── typescript.v1.yaml
```

- 各 Worker は **独立した Go module**（`go.mod` を個別に持つ）
- `apps/grading-worker/` という旧名称は廃止し、`apps/workers/grading/` にリネーム
- 将来の Worker 追加（分析パイプライン、ベンチマーク実行等）も同じ `apps/workers/<name>/` パターンで追加

### 2. LLM 呼び出しを全て Worker 側に集約

- **問題生成（generation）**：API は `POST /problems/generate` でジョブ enqueue のみ → `apps/workers/generation/` が LLM 呼び出し（Pydantic で定義された generation job payload を読み取り）
- **採点 LLM-as-a-Judge（judge）**：従来通り `apps/workers/grading/` 内で LLM 呼び出し（[ADR 0008](./0008-custom-llm-judge.md)）
- **API（apps/api/）の責務から LLM 呼び出しを除外**：CRUD / 認証 / ジョブ enqueue のみに絞る
- LLM プロバイダ抽象化（[ADR 0007](./0007-llm-provider-abstraction.md)）は Worker 側で実装、API 側は不要

### 3. プロンプトを Worker 内に閉じる

- 旧：`packages/prompts/generation/` + `packages/prompts/judge/`（root 共有パッケージ）
- 新：
  - `apps/workers/generation/prompts/generation/` ← generation worker 内
  - `apps/workers/grading/prompts/judge/` ← grading worker 内
- バージョン管理ルール（`<role>.v<N>.yaml` / 一度配布した vN は書き換えない）は維持（旧 `packages/prompts/README.md` の運用ルールを各 Worker 配下の prompts/ ディレクトリに継承）
- `packages/prompts/` ディレクトリは廃止済み、各 Worker 着手時に該当 Worker 内 prompts/ で運用

### 4. ジョブパターンの拡張

- 既存：`grading_job` テーブル（採点ジョブ）
- 追加：`generation_job` テーブル（問題生成ジョブ）
- いずれも [ADR 0004](./0004-postgres-as-job-queue.md) の SKIP LOCKED + LISTEN/NOTIFY パターンに従う
- 共通ジョブ型は Pydantic で `apps/api/app/schemas/` 内に定義（→ [ADR 0006](./0006-json-schema-as-single-source-of-truth.md) の SSoT 設計）。Pydantic から個別 JSON Schema を `apps/api/job-schemas/` に出力し、quicktype `--src-lang schema` で各 Worker（Go）に struct 生成（Job キュー境界の伝送路）

## Why（採用理由）

### 1. UX とスケール特性の両立

- **同期 API 待機の解消**：ユーザは「生成中」「採点中」の状態をフロントで即時確認、ポーリング / SSE / WebSocket で完了通知
- **ALB / API Gateway タイムアウトの回避**：API 応答は数百 ms 内、長時間処理は Worker 側
- **リトライ容易性**：Worker は SKIP LOCKED でジョブを取り出すため、失敗ジョブの再試行が DB 層で完結

### 2. 既存の grading パターンを generation に流用

- ジョブキュー実装、Worker フレームワーク、OTel トレース連携（[ADR 0010](./0010-w3c-trace-context-in-job-payload.md)）、エラーハンドリング、リトライ戦略 — **すべて流用可能**
- 設計パターンが「ジョブを enqueue → Worker が LLM / Docker を呼ぶ」に統一され、新規 Worker 追加も同じパターン

### 3. apps/workers/<name>/ グループ配下の利点

- **複数 Worker への拡張性**：将来 `apps/workers/analysis/` / `apps/workers/benchmark/` 等を同じパターンで追加可能
- **Go module の独立**：各 Worker が独立 deploy 可能、依存巻き込みなし。例：generation で重量級 LLM SDK を使っても grading に影響しない
- **視認性**：「Worker 群」が apps/workers/ 配下にまとまる、apps/ 直下の列挙時にノイズが減る
- **CLAUDE.md「規模に応じた選定」と整合**：単一 Go module + cmd/<name>/ パターン（apps/worker/cmd/grading 等）は本プロジェクト規模ではオーバー、独立 module の方が独立性が高く採用市場価値（マイクロサービス的設計）も示せる

### 4. プロンプトを Worker 内に閉じる利点

- **「プロンプト = Worker の関心事」が明確になる**：generation worker は generation プロンプト、grading worker は judge プロンプトのみを扱う
- **deploy 単位とプロンプトが揃う**：Worker のリリースとプロンプトのバージョンアップが同じ git 履歴で追える
- **共有パッケージの保守不要**：`packages/prompts/` を別 package として管理する手間がなくなる

### 5. API の責務を絞る

- API（apps/api/）は CRUD + 認証 + ジョブ enqueue に集中、テスト容易性が向上
- LLM プロバイダ依存（API キー / 失敗パターン / レイテンシ）が API レイヤから消える
- Frontend が API を叩く際の「予測可能性」が上がる（応答時間がほぼ一定、外部 I/O 不在）

## Alternatives Considered（検討した代替案）

### Worker のディレクトリ構造

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| **`apps/workers/<name>/`（採用）** | グループ配下、各 Worker は独立 Go module | — |
| `apps/<worker-name>/`（フラット） | apps/grading-worker / apps/generation-worker を直接置く | apps/ 直下に Worker が増えると視認性が落ちる、`apps/` がアプリと Worker の混在状態に |
| `apps/worker/cmd/<name>/`（単一 module） | 1 つの Go module で `cmd/` 配下に複数 main を置く | `internal/` 共有が便利だが、依存巻き込み（generation の重量級 LLM SDK が grading にも入る）が起きる。本プロジェクト規模では独立 module の方が独立性価値が大きい |
| `services/workers/<name>/`（apps の外） | Worker は app ではないので別の根 | apps/ 配下統一を崩すことで CI / mise.toml の構造が複雑化、Frontend の apps/web との対称性も悪化 |

### LLM 呼び出しの場所

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| **Worker 非同期で全 LLM 呼び出し（採用）** | API は enqueue のみ、Worker が LLM | — |
| API 同期で LLM 呼び出し（旧設計） | API がリクエスト時に LLM 呼び出し | タイムアウトリスク、UX 悪化、リトライ実装の複雑化 |
| Streaming response（API 同期 + SSE） | API が SSE で chunk を返す | LLM の SSE 対応プロバイダに依存、HTTP コネクション維持コスト、リトライ困難 |
| ハイブリッド（API + Worker 両方が呼ぶ） | 短い generation は API 同期、長い batch は Worker | パターン分岐が複雑、API 側にも LLM プロバイダ依存が残る |

### プロンプトの所在

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| **Worker 内に閉じる（採用）** | apps/workers/<name>/prompts/ | — |
| packages/prompts/ で共有（旧設計） | root に共通パッケージ | 消費者が Worker のみになる以上、共有パッケージ化の正当性が消えた |
| apps/api/prompts/ に集約（API 同期想定の旧設計） | API が LLM 呼び出すため API 内 | 本 ADR で LLM が Worker に移った時点で消失 |
| 専用 packages/prompts-{generation,judge}/ への分割 | Worker と分離した独立パッケージ | バージョン管理 / deploy 単位が Worker と分離する利点がなく、保守コスト増 |

## Consequences（結果・トレードオフ）

### 得られるもの

- **API 応答時間の予測可能性**：LLM プロバイダ依存が API から消える
- **同じジョブパターンの一貫適用**：grading / generation / 将来の Worker が共通設計に従う
- **複数 Worker 拡張への構造的準備**：apps/workers/<name>/ パターンで何個でも追加可能
- **deploy 単位の独立**：generation の問題が grading に波及しない、逆も同様
- **プロンプトと Worker の deploy 単位が揃う**：プロンプト変更と Worker コード変更が同じ git 履歴で追える
- **採用市場価値**：「ジョブキュー + Worker パターンを LLM 呼び出しに適用する設計」は portfolio で説明しやすい

### 失うもの・受容するリスク

- **問題生成の即時性低下**：API 同期なら数秒で返せたものがジョブキュー経由になる（ただしフロントの UX 設計でカバー可能）
- **ジョブテーブル / ジョブ種別の数が増える**：generation_job / grading_job + 将来追加。命名規則と DB スキーマ設計を一貫させる必要
- **Frontend のポーリング / SSE / WebSocket 実装コスト**：「ジョブ完了通知」を受け取る仕組みが必要（初回実装は grading のために既に作る予定だったので増分コストは小さい）
- **`apps/grading-worker/` のリネームコスト**：未実装段階のため小さい（git 履歴 / 既存 ADR の参照名のみ）

### 将来の見直しトリガー

- **LLM レイテンシが秒未満に短縮された場合**（LLM の構造的な高速化が進んだ場合）：API 同期パターンへの一部回帰を再評価
- **Worker 数が 5 個以上に拡張した場合**：apps/workers/ 配下の独立 module 群が保守的に重くなれば、共通 internal パッケージ（`packages/worker-shared/` 等）の切り出しを検討
- **採点 / 生成以外の LLM 用途が出た場合**：新規 Worker（apps/workers/<new-name>/）を追加、本 ADR の方針で対応
- **特定 Worker が極端な dependency を持つ場合**（例：分析 Worker が PyTorch を使う Python 化）：Go 縛り（[ADR 0016](./0016-go-for-grading-worker.md)）を Worker ごとに見直す可能性

## References

- [ADR 0003: レイヤ別ポリグロット構成](./0003-phased-language-introduction.md)
- [ADR 0004: Postgres をジョブキューに採用](./0004-postgres-as-job-queue.md)（Worker 非同期パターンの基盤）
- [ADR 0006: 共有データ型は Pydantic を SSoT](./0006-json-schema-as-single-source-of-truth.md)（generation_job ペイロードを Pydantic で定義する前提）
- [ADR 0007: LLM プロバイダ抽象化戦略](./0007-llm-provider-abstraction.md)（Worker 側で実装する前提）
- [ADR 0008: LLM-as-a-Judge を自前実装](./0008-custom-llm-judge.md)（grading worker 側）
- [ADR 0009: 採点コンテナの使い捨て方式](./0009-disposable-sandbox-container.md)（grading worker 側）
- [ADR 0010: W3C Trace Context をジョブペイロードに埋め込む](./0010-w3c-trace-context-in-job-payload.md)（OTel 連携）
- [ADR 0016: 採点ワーカーを Go で実装](./0016-go-for-grading-worker.md)（apps/grading-worker → apps/workers/grading にリネーム、Go 採用は維持）
- [ADR 0034: バックエンド API に FastAPI を採用](./0034-fastapi-for-backend.md)（API は enqueue のみ）
- [ADR 0036: Frontend ツーリングを apps/web 内に閉じる](./0036-frontend-monorepo-pnpm-only.md)（apps/<app>/ self-contained パターンの先例）
- [ADR 0039: タスクランナー兼 tool 版数管理に mise を採用](./0039-mise-for-task-runner-and-tool-versions.md)（apps/workers/<name>/ 用のタスク追加先）
