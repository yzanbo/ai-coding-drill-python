# Worker 側型同期パイプライン合流（✅ 完了）

## このフェーズで何ができるようになるか

R0-7（型同期パイプライン基盤）で配線済の **Pydantic SSoT → JSON Schema artifact** に、Worker（Go）側を end-to-end で合流させる。本フェーズが終わると以下ができるようになる：

- `apps/api/app/schemas/jobs/<job_type>.py` に Pydantic クラスを 1 つ追加 → `mise run types-gen` 一発で **両 Worker の `apps/workers/<worker>/internal/jobtypes/*.go` が同期更新**される
- `mise run worker:types-gen` 単独で両 Worker の Go struct 生成のみを走らせられる
- CI（GitHub Actions）に `worker-types-gen` ジョブが追加され、PR で **両 Worker の生成パイプラインが壊れた変更**（quicktype が落ちる / 生成 Go が `go vet` を通らない 等）が main にマージされない
- 以後 R1-2 / R1-3 / R1-5 等の機能実装で新規 `*JobPayload` Pydantic を追加した時、Worker 側の Go 型は **手書きせず自動生成で揃う**

R0-7（HTTP API 境界、Backend ⇄ Frontend）と本フェーズ（Job キュー境界、Backend ⇄ Worker）で、ADR 0006 の「Pydantic SSoT + 境界別 2 伝送路」が 3 言語（Python / TS / Go）に全て展開された状態になる。

---

> **前提フェーズ**：[R0-7 型同期パイプライン基盤](./type-sync-pipeline.md)（HTTP API 境界 + `apps/api/job-schemas/` への JSON Schema 出力スクリプトと mise タスクが配線済）+ [R0-8 両 Worker Go 環境構築](./worker.md) + [R0-9 両 Worker レイヤ分割](./worker-layers.md)（`internal/jobtypes/` ディレクトリと `.gitignore` が両 Worker に配置済）完了
> **次フェーズ**：R1 開始（R1-2 LLM プロバイダ抽象化が本フェーズの成果物に依存）
>
> **本フェーズの位置付け**：[README.md: 役割別 setup の後段](./README.md#役割別-setup-の後段レイヤ分割フェーズ) の最終ピース。Worker のレイヤ分割（R0-9）で配置された `internal/jobtypes/` を「生成物の置き場」として正式運用に乗せる。
>
> **書き方の方針**：依存ツール（quicktype）の導入を伴うため、Backend / Frontend / Worker の **「環境構築 + 品質ゲート 5 ステップ」** パターンに準じて「ツール導入 → 生成スクリプト → mise タスク → CI 配線 → 完了確認」の流れで進める。

---

## 自律実行ポリシー（Claude が本ファイルを読んで作業する時の前提）

本ファイルは Claude に**そのまま実行を依頼**する想定。次の原則を守って最後まで進める。

1. **設計上の確認を求めない**：`§決定値` に書かれた選択（quicktype 採用 / mise tools 経由配信 / ファイル単位呼び出し / 1 schema → 1 .go ファイル / CI 別ジョブ化 / 生成物 gitignore 継続）は決定済み。関連 ADR（[ADR 0006](../../../adr/0006-json-schema-as-single-source-of-truth.md) / [ADR 0039](../../../adr/0039-mise-for-task-runner-and-tool-versions.md) / [ADR 0040](../../../adr/0040-worker-grouping-and-llm-in-worker.md)）は消化済み
2. **関連ファイルが本ファイルとズレていたら、関連ファイル側を直す**：以下が `§決定値` と違う状態にあれば、本ファイルを真として書き換える：
   - [mise.toml](../../../../mise.toml)（`[tools]` に `npm:quicktype` / `[tasks."worker:<worker>:types-gen"]` / `[tasks."worker:types-gen"]` / `[tasks."types-gen"]` の depends）
   - [.github/workflows/ci.yml](../../../../.github/workflows/ci.yml)（`worker-types-gen` ジョブ + `ci-success.needs`）
   - [apps/api/scripts/generate_worker_jobtypes.py](../../../../apps/api/scripts/generate_worker_jobtypes.py)（quicktype ドライバ）
   - [apps/api/app/schemas/jobs/health_check.py](../../../../apps/api/app/schemas/jobs/health_check.py)（疎通サンプル）
   - 両 Worker の `internal/jobtypes/.gitignore` / `internal/jobtypes/README.md`（R0-9 配置済を流用）
   - [docs/requirements/5-roadmap/01-roadmap.md](../01-roadmap.md)（R0-11 行と R1 umbrella の状態列）
3. **新規ブランチを切る**：[CLAUDE.md: ブランチ運用](../../../../.claude/CLAUDE.md#ブランチ運用) に従い、`feature/shared/worker-types-gen` で作業する（`shared` scope = `apps/api/job-schemas/` artifact 拡張 + 両 Worker への影響）
4. **コミット・PR 作成は明示指示まで保留**（[CLAUDE.md: Git 操作の禁止](../../../../.claude/CLAUDE.md#git-操作の禁止)）
5. **完了後に検証コマンドを必ず流す**：`mise run types-gen` / `mise run worker:types-gen` / `mise run worker:grading:lint` / `worker:grading:test` / `worker:generation:lint` / `worker:generation:test` の **6 つすべて** clean になることを確認

---

## 決定値（このフェーズで固定する、議論しない設計）

### A. ツールチェーン

| 項目 | 採用 | 不採用 | 採用理由 |
|---|---|---|---|
| JSON Schema → Go struct 変換器 | **quicktype** | `oapi-codegen` / 手書き / Python script で AST 生成 | [ADR 0006](../../../adr/0006-json-schema-as-single-source-of-truth.md) で既に SSoT として記載。Frontend 側 Hey API と思想が揃う（schema-first） |
| quicktype の配信方法 | **`mise.toml [tools]` の `"npm:quicktype" = "latest"`** | apps/web の devDep に追加 / `pnpm dlx` / Homebrew | Worker dir からも CI からも単一バイナリで起動できる。apps/web 経由だと「Worker のための生成ツールを Frontend deps に置く」責務逆転になる |
| quicktype 呼び出し方 | **schema ファイル単位で positional 引数で渡す** | `--src DIRECTORY` でまとめて渡す | quicktype は `--src DIR` モードで `--src-lang schema` を無視し、各ファイルを JSON データとして読んでしまう（実機検証で確認）。ファイル単位なら `--src-lang schema` が正しく効く |
| ドライバ言語 | **Python（`apps/api/scripts/generate_worker_jobtypes.py`）** | シェル + jq / Node script | リポジトリで Python は常設（[ADR 0035](../../../adr/0035-uv-for-python-package-management.md)）。jq は環境依存。json.title フィールドの読み取りが Python 標準ライブラリで完結 |
| 出力ファイル粒度 | **1 schema → 1 `.go` ファイル**（`internal/jobtypes/<job-name>.go`） | 全 schema を 1 ファイルに集約 | 複雑な schema で nested 型名がコリジョンするリスクを最小化。schema 削除時に取り残しが残らないよう、ドライバが実行時に既存 `*.go` を一掃してから再生成 |
| Go struct 名 | **schema の `title` フィールド**（= Pydantic クラス名そのまま、`HealthCheckJobPayload` 等） | 自動命名（`T` / ファイル名由来）/ 別命名規則 | export_job_schemas.py が Pydantic クラス名を `title` に入れているので、Pydantic ↔ Go で名前が完全一致する |
| 生成物の git 管理 | **gitignore 継続**（`apps/workers/<worker>/internal/jobtypes/.gitignore` で `*` + `!.gitignore` + `!README.md`） | git commit する | 「生成物は commit しない」の R0-9 方針を維持。drift 検出は CI で `mise run worker:types-gen` を走らせれば quicktype が落ちる / `go vet` が落ちることで気づく |
| CI でのドリフト検出方針 | **専用ジョブ `worker-types-gen`**（schemas-export → worker:types-gen → 両 Worker で `go vet`） | `types-gen-drift` 内に統合 / `worker-*-test` の前段に組込 | 生成物が gitignored なので `git diff --exit-code` 軸が無く、検証軸は「実行成否 + build 可能性」。types-gen-drift（git diff 軸）と責務が違うため別ジョブにする |

### B. ディレクトリ・ファイル配置

**新規追加（本フェーズ）**：

```text
apps/api/
├── scripts/
│   └── generate_worker_jobtypes.py     # quicktype ドライバ（schema ごとに 1 .go 出力）
├── app/schemas/jobs/
│   └── health_check.py                 # 疎通確認用サンプル *JobPayload（最小 1 件）
└── job-schemas/
    └── health-check.schema.json        # 上記の JSON Schema artifact（commit 対象、R0-7 既存）

apps/workers/<worker>/internal/jobtypes/
├── .gitignore                          # R0-9 配置済（生成 .go を ignore、README + .gitignore は commit）
├── README.md                           # R0-9 配置済（責務 + 命名 + 使い方）
└── health-check.go                     # 生成物（gitignored、ローカル / CI で毎回再生成）
```

**変更**：

- [mise.toml](../../../../mise.toml)：`[tools]` に `"npm:quicktype" = "latest"` 追加 / 既存 `worker:<worker>:types-gen` を新ドライバ呼び出しに切替 / `types-gen` 横断タスクの depends に `worker:generation:types-gen` 追加 / `worker:types-gen` の depends 先頭に `api:job-schemas-export` 追加
- [.github/workflows/ci.yml](../../../../.github/workflows/ci.yml)：`worker-types-gen` ジョブ追加 / `ci-success.needs` に追加

### C. ジョブ追加時の運用フロー（R1 以降で実機能の Pydantic を追加する手順）

新しいジョブ種別を増やす時、本フェーズの成果物のうえに「Pydantic を 1 つ書く」だけで両 Worker の Go 型が揃う：

1. `apps/api/app/schemas/jobs/<job_type>.py` を新規作成し、`XxxJobPayload(BaseModel)` を定義（クラス名末尾必須）
2. `mise run types-gen` を実行（または `api:job-schemas-export` + `worker:types-gen` の組み合わせ）
3. `apps/api/job-schemas/<job-type>.schema.json` と両 Worker の `internal/jobtypes/<job-type>.go` が揃う
4. Backend では Pydantic を直接 import、Worker では生成 struct を `internal/jobtypes` 経由で import

これにより「片方を変えて片方を忘れる」事故が型レベルで起きなくなる（[ADR 0006](../../../adr/0006-json-schema-as-single-source-of-truth.md)）。

---

## 1. quicktype のツール導入

**目的**：両 Worker と CI から quicktype CLI を `mise exec -- quicktype ...` の形で同一バイナリで叩けるようにする。

**最終状態**：

- [mise.toml](../../../../mise.toml) の `[tools]` セクションに `"npm:quicktype" = "latest"` が記載されている
- `mise install` 後、`mise exec -- quicktype --version` がエラー無く版数を返す
- CI ジョブで `jdx/mise-action` を使えば追加セットアップ無しで quicktype が PATH に乗る

**完了基準**：

- `mise exec -- quicktype --lang go --src-lang schema --help` で usage が出る
- npm の警告（transitive 依存の inflight / glob 等）は出るが exit 0 で完了する

---

## 2. quicktype ドライバスクリプトの配置

**目的**：`apps/api/job-schemas/*.schema.json` を順に走査し、各ファイルを quicktype に positional 引数で渡して両 Worker の `internal/jobtypes/*.go` を生成する。

**最終状態**：[apps/api/scripts/generate_worker_jobtypes.py](../../../../apps/api/scripts/generate_worker_jobtypes.py) が次を満たす：

- 第 1 引数で出力先 Worker dir（`../workers/grading` / `../workers/generation`）を受け取る
- `<worker_dir>/internal/jobtypes/` 配下の既存 `*.go` を**一掃してから**再生成する（schema 削除時の取り残しを防ぐ）
- 各 schema の `title` フィールドを読み、`quicktype --top-level <title>` で Pydantic クラス名そのままを Go struct 名として採用
- quicktype 失敗時は stdout / stderr を吐いて exit 1
- schema が 0 件でも警告メッセージを出して exit 0（R1-2 着手前の placeholder 状態を許容）

**完了基準**：

- `uv run python -m scripts.generate_worker_jobtypes ../workers/grading` がローカルで成功し、`apps/workers/grading/internal/jobtypes/health-check.go` を出力
- 生成された `.go` ファイルに `type HealthCheckJobPayload struct` が含まれる
- `go vet ./internal/jobtypes/...` がエラー無く通る

---

## 3. mise タスクの差し替え

**目的**：既存の `worker:<worker>:types-gen` を新ドライバ呼び出しに切替え、`types-gen` / `worker:types-gen` の depends を両 Worker 対称に揃える。

**最終状態**（[mise.toml](../../../../mise.toml) のタスク定義が以下に揃っている）：

| タスク | dir | run / depends |
|---|---|---|
| `worker:grading:types-gen` | `apps/api` | `uv run python -m scripts.generate_worker_jobtypes ../workers/grading` |
| `worker:generation:types-gen` | `apps/api` | `uv run python -m scripts.generate_worker_jobtypes ../workers/generation` |
| `worker:types-gen`（横断）| — | depends = `api:job-schemas-export` + `worker:grading:types-gen` + `worker:generation:types-gen` |
| `types-gen`（全境界）| — | depends = `api:openapi-export` + `api:job-schemas-export` + `web:types-gen` + `worker:grading:types-gen` + `worker:generation:types-gen` |

**完了基準**：

- `mise run worker:types-gen` を `internal/jobtypes/*.go` を消した状態から実行し、両 Worker に `health-check.go` が生成される
- `mise run types-gen` を実行し、HTTP API artifact（`openapi.json` / `web/__generated__/api/`）+ Job キュー artifact（`job-schemas/` + 両 Worker `jobtypes/`）の **4 経路すべて**が更新される

---

## 4. 疎通確認用サンプル `*JobPayload` の配置

**目的**：R1-2 以降の実 payload が増える前に、パイプラインが end-to-end で動くことを 1 件の placeholder で常時検証可能にする。

**最終状態**：

- [apps/api/app/schemas/jobs/health_check.py](../../../../apps/api/app/schemas/jobs/health_check.py) に `HealthCheckJobPayload(BaseModel)` が定義されている（`job_id: str` + `note: str = ""`）
- `mise run api:job-schemas-export` で `apps/api/job-schemas/health-check.schema.json` が出力される（title フィールドに `HealthCheckJobPayload` が入る）
- `mise run worker:types-gen` で両 Worker の `internal/jobtypes/health-check.go` が生成される

**完了基準**：

- 生成 Go の中身に `type HealthCheckJobPayload struct { JobID string ...; Note *string ... }` が含まれる
- 上記 placeholder は **R1-2 以降も削除しない**（最小サンプルとして疎通確認用に残す）

---

## 5. CI への組込

**目的**：PR で「Pydantic を変えたら quicktype が落ちる」「生成 Go が `go vet` を通らない」を main マージ前に弾く。

**最終状態**（[.github/workflows/ci.yml](../../../../.github/workflows/ci.yml) が以下を満たす）：

- `worker-types-gen` ジョブが追加されている
  - 起動条件：`changes.outputs.api == 'true' || .grading == 'true' || .generation == 'true' || .shared == 'true'`
  - ステップ：`actions/checkout` → `jdx/mise-action` → `mise run api:job-schemas-export` → `mise run worker:types-gen` → `mise exec -- go -C apps/workers/grading vet ./internal/jobtypes/...` → 同じく generation
- `ci-success.needs` に `worker-types-gen` が 1 行追加されている（[ADR 0031](../../../adr/0031-required-status-checks-umbrella-job.md) の umbrella パターン）
- `types-gen-drift` ジョブのコメントに「Worker 側は worker-types-gen ジョブで別管理」と明記されている

**完了基準**：

- 上記変更を含む PR で `worker-types-gen` がチェックリストに現れて緑になる
- `ci-success` Required status checks の網に自動で組込まれる

---

## 6. 進捗トラッカーへの反映

**目的**：本フェーズが終わったことをロードマップに反映する。

**最終状態**：

- [01-roadmap.md](../01-roadmap.md) の R0-11 行が、状態列 `✅ 完了` + 詳細手順列が本ファイルへのリンク `[r0-setup/worker-types-gen.md](./r0-setup/worker-types-gen.md)` になっている（完了前の `🔴 未着手` + `（要作成）` 注記は完了時に削除）
- R1 ブロッカー umbrella 行（`R0-8 + R0-9 + R0-11 完了`）が ✅ 完了に更新される
- マイルストーン段落の「型同期パイプライン Worker 側合流 = R0-11 完了」が達成された前提で記述が整合
- 本ファイル冒頭のステータスマークが `# Worker 側型同期パイプライン合流（✅ 完了）` に書き換わっている

**完了基準**：

- 進捗トラッカー上で本フェーズが完了になっている
- 本ファイルへのリンクが進捗トラッカーから辿れる
- R1-2 LLM プロバイダ抽象化に着手可能な「R1 ブロッカー解消」状態が実現している

---

## 関連

- 親階層：[README.md: 役割別 setup の後段](./README.md#役割別-setup-の後段レイヤ分割フェーズ)
- 前フェーズ：[type-sync-pipeline.md](./type-sync-pipeline.md)（HTTP API 境界 + JSON Schema artifact 出力スクリプト）/ [worker.md](./worker.md)（両 Worker workspace）/ [worker-layers.md](./worker-layers.md)（`internal/jobtypes/` 配置）
- 関連 ADR：[ADR 0006](../../../adr/0006-json-schema-as-single-source-of-truth.md)（Pydantic SSoT + 境界別 2 伝送路）/ [ADR 0039](../../../adr/0039-mise-for-task-runner-and-tool-versions.md)（mise によるツール版数管理）/ [ADR 0040](../../../adr/0040-worker-grouping-and-llm-in-worker.md)（両 Worker 並立）
- 実装契約 SSoT：[.claude/rules/worker.md](../../../../.claude/rules/worker.md)（`internal/jobtypes/` の責務、手書き禁止、再生成コマンド）
- 横断要件：[06-dev-workflow.md](../../2-foundation/06-dev-workflow.md)（型同期方針の全体像）
