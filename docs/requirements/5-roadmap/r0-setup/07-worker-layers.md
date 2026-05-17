# 07. Worker（Go）ディレクトリ構成（🔴 未着手）

> **守備範囲**：`apps/workers/grading/` 配下に Go の package 分割（`cmd/` + `internal/{jobtypes,llm,sandbox,grading,db,observability}/`）を確定し、各 package の責務 + import 方向 + 命名規則を `.claude/rules/worker.md` に「実装契約」として固定する。本フェーズが終わると、後続の Worker 機能実装（LLM プロバイダ抽象化 / 採点ロジック / DB 書き戻し）が「悩まずに迷わずどの package に置くかを選ぶ」状態になる。
> **前提フェーズ**：[Go 環境構築フェーズ](./04-worker.md) 完了済（`apps/workers/grading/main.go` skeleton / `go.mod` / `.golangci.yml` / `sandbox/Dockerfile` skeleton が配置済、`mise run worker:grading:dev` で起動可能、golangci-lint / govulncheck がローカル + CI 両方で緑）
> **次フェーズ**：R1 開始（LLM プロバイダ抽象化フェーズが本フェーズの成果物に依存、→ [01-roadmap.md](../01-roadmap.md)）
>
> **本フェーズの位置付け**：[README.md: 役割別 setup の後段](./README.md#役割別-setup-の後段レイヤ分割フェーズ) を参照。言語ツーリングが整った上に、その言語側でプロジェクト固有のレイヤ分割を確定するフェーズで、「悩む余地のない基本構造」とは別物として扱う（[05-backend-layers.md](./05-backend-layers.md) / [06-frontend-layers.md](./06-frontend-layers.md) と同パターン）。
>
> **書き方の方針**：依存ライブラリのインストールを伴わないため「環境構築 + 品質ゲート 5 ステップ」パターンには載らない。代わりに「**決定値の確認 → ディレクトリ作成 → 各 package README → 全体 README → rules ファイルに実装契約として固定**」の構造で進める（Backend / Frontend レイヤ分割フェーズと同パターン）。
>
> **本ファイルと `.claude/rules/worker.md` の役割分担**：本ファイルが「**手順 + このフェーズで下す決定**」の SSoT、`worker.md` が「**実装契約（R1 以降の機能実装が読む規約）**」の SSoT。`§決定値` の表（`§A` ツリー / `§C` import 方向 / `§D` 命名規則）は両ファイルに同じ値を書く。一方を更新したら他方も合わせて更新する。

---

## 自律実行ポリシー（Claude が本ファイルを読んで作業する時の前提）

本ファイルは Claude に**そのまま実行を依頼**する想定で書かれている。次の原則を守って、ユーザーに確認を取らずに最後まで進める。

1. **ユーザーに設計上の確認を求めない**：`§決定値` に書かれた選択（package 分割 / `internal/` 配下サブ構成 / LLM Worker 集約方針 / import 方向 等）は**決定済みで議論しない**。関連 ADR（[ADR 0016](../../../adr/0016-go-for-grading-worker.md) / [ADR 0019](../../../adr/0019-go-code-quality.md) / [ADR 0040](../../../adr/0040-worker-grouping-and-llm-in-worker.md) / [ADR 0009](../../../adr/0009-disposable-sandbox-container.md) / [ADR 0007](../../../adr/0007-llm-provider-abstraction.md)）は既に消化済みのため、再検討しない。
2. **関連ファイルが本ファイルとズレていたら、関連ファイル側を直す**：以下のファイル群が `§決定値` と違う状態にあれば、本ファイルを真として書き換える：
   - `apps/workers/grading/` 配下のフォルダ・README（`§A` のツリーに対応）
   - `.claude/rules/worker.md`（Worker 全般の実装契約）
   - `.claude/CLAUDE.md`（「ルールファイルの管理」リストに `worker.md` が列挙されていること）
   - `docs/requirements/5-roadmap/01-roadmap.md`（R0-7 行の状態列とリンク列）
3. **新規ブランチを切る**：[CLAUDE.md: ブランチ運用](../../../../.claude/CLAUDE.md#ブランチ運用) に従い、`feature/worker/r0-7-layers`（または同等の `feature/worker/<名前>`）で作業する。`main` で直接作業しない。
4. **コミット・PR 作成は明示指示があるまで行わない**：[CLAUDE.md: Git 操作の禁止](../../../../.claude/CLAUDE.md#git-操作の禁止) に従い、`git add` / `git commit` / `git push` / PR 作成はユーザーから明示指示が出るまで保留する。ファイル作成・編集は自動で進めてよい。
5. **初期状態のばらつきに対する方針**：
   - 想定 package が存在しない → 作る（空ディレクトリ + `.gitkeep` ではなく `README.md` を入れる）
   - 想定 package が存在し中身が空 → README を入れる
   - 想定 package が存在し中身がある（既存の `internal/jobtypes/` 等、04-worker.md フェーズで埋まったもの）→ 中身を確認して `§決定値` と矛盾する部分のみ書き換える。04-worker.md 由来の実装ファイル（`main.go` / `go.mod` / `go.sum` / `.golangci.yml` / `sandbox/Dockerfile` / `sandbox/.dockerignore`）は本フェーズでは触らない（04 の SSoT を尊重する）
   - `.claude/rules/worker.md` に「§ディレクトリ構成（`apps/workers/grading/`）」「§レイヤ間の import 方向」セクションが無い、または `§A` / `§C` / `§D` と矛盾する → 機械可読版に展開して追加 or 書き換える（手順 4 が SSoT）
   - `.claude/CLAUDE.md` の「ルールファイルの管理」リストに `worker.md` が無ければ追加する
6. **完了後に検証コマンドを必ず流す**：`mise run worker:grading:lint` / `mise run worker:grading:test` を順に実行し、両方 clean になることを確認する。失敗があれば修正して再実行（ユーザーに投げ返さない）
7. **「書き換える」「削除する」「追加する」「リネームする」の解釈**：本ドキュメント中のこれらの動詞は、すべて**最終状態を §決定値 に合わせる作業**を指す。**初期状態がどうであれ、最終的に §決定値 と一致していればよい**（idempotent）

---

## 決定値（このフェーズで固定する、議論しない設計）

### A. ディレクトリ構成

```text
apps/workers/grading/
├── go.mod                                           # 04-worker.md 配置済
├── go.sum                                           # 04-worker.md 配置済
├── .golangci.yml                                    # 04-worker.md 配置済
├── README.md                                        # 全体図 + やってはいけないこと（本フェーズで作成）
├── cmd/                                             # エントリポイント（main package）
│   ├── README.md                                    # 本フェーズで作成
│   └── worker/
│       ├── README.md                                # 本フェーズで作成
│       └── main.go                                  # 04-worker.md の main.go を cmd/worker/main.go へ移設
├── internal/                                        # private packages（他 module から import 不可、Go 規約）
│   ├── README.md                                    # 本フェーズで作成
│   ├── jobtypes/                                    # apps/api/job-schemas/ から quicktype で生成された Go struct（04-worker.md で雛形配置済）
│   │   └── README.md                                # 本フェーズで作成
│   ├── llm/                                         # LLM プロバイダ抽象化（ADR 0007 / 0040）
│   │   └── README.md                                # 本フェーズで作成
│   ├── sandbox/                                     # Docker サンドボックス操作（公式 docker/docker/client、ADR 0009）
│   │   └── README.md                                # 本フェーズで作成
│   ├── grading/                                     # 採点ロジック（judge LLM 呼び出し + サンドボックス連携）
│   │   └── README.md                                # 本フェーズで作成
│   ├── db/                                          # Postgres ジョブキュー取得 + 結果書き戻し（SELECT FOR UPDATE SKIP LOCKED、ADR 0004）
│   │   └── README.md                                # 本フェーズで作成
│   └── observability/                               # OpenTelemetry + 構造化ログ + Prometheus metrics（R4 で実体化）
│       └── README.md                                # 本フェーズで作成
├── prompts/                                         # LLM プロンプト（apps/workers/grading/prompts/judge/、ADR 0040）
│   └── judge/                                       # 04-worker.md or 既存配置（本フェーズでは触らない）
└── sandbox/                                         # サンドボックスイメージ Dockerfile（04-worker.md 配置済、本フェーズでは触らない）
    ├── Dockerfile
    └── .dockerignore
```

> **既存実装ファイル**（04-worker.md 配置済、本フェーズでは触らない）：`go.mod` / `go.sum` / `.golangci.yml` / `sandbox/Dockerfile` / `sandbox/.dockerignore` / `prompts/judge/` 配下。中身の SSoT は [04-worker.md](./04-worker.md) の各 step。
>
> **`main.go` の移動**：04-worker.md は `apps/workers/grading/main.go` の skeleton を配置している。本フェーズで `cmd/worker/main.go` に移設する（Go コミュニティ慣習に従い、エントリポイントを `cmd/<binary-name>/main.go` に置く）。

### B. 配置に関する重要な選択（なぜそうしたか）

| 論点 | 採用 | 不採用 | 採用理由 |
|---|---|---|---|
| エントリポイントの位置 | **`cmd/worker/main.go`** | `apps/workers/grading/main.go`（リポジトリ直下）| Go コミュニティ慣習。将来 `cmd/migrator/` `cmd/dlq-replayer/` 等の補助バイナリを足せる構造に倒す |
| public package vs internal | **全て `internal/` 配下** | `pkg/<name>/` で外部 module 公開 | このリポジトリ外から import される想定が無い。`internal/` にすることで Go コンパイラレベルで「リポジトリ外から import 不可」を強制 |
| LLM 呼び出しの置き場 | **`internal/llm/`**（Worker 内）| `apps/api/app/llm/` 等の Backend 側 | ユーザー応答性と LLM レイテンシを分離するため。Backend は enqueue + 結果取得のみ（→ [ADR 0040](../../../adr/0040-worker-grouping-and-llm-in-worker.md)） |
| プロンプトの置き場 | **`prompts/judge/`**（Worker 同居）| `packages/prompts/`（旧構想）| プロンプトは利用 Worker と同居（→ [ADR 0040](../../../adr/0040-worker-grouping-and-llm-in-worker.md)）。`packages/prompts/` は廃止（[.claude/CLAUDE.md](../../../../.claude/CLAUDE.md) 参照） |
| サンドボックス Dockerfile の位置 | **`sandbox/Dockerfile`**（Go コード外）| `internal/sandbox/Dockerfile` | Dockerfile は Go の build 対象外。Go コードと混在させると `go test ./...` のスコープが曖昧になるため、別ディレクトリに分離 |

### C. 各 package の import 方向

新規機能追加時、各 package から何を import してよいかを下記表で固定する。R1 以降の全機能実装はこの契約に従う。

| package | import してよい | import 禁止 |
|---|---|---|
| `cmd/worker/` | 全 `internal/*`（main は全ての internal を組み合わせる） | （上位なし） |
| `internal/grading/` | `internal/llm` / `internal/sandbox` / `internal/jobtypes` / `internal/db`（読み出しのみ）/ `internal/observability` | `cmd/` / 他 module |
| `internal/llm/` | `internal/jobtypes`（型のみ） / `internal/observability` | `cmd/` / `internal/grading` / `internal/sandbox` / `internal/db` |
| `internal/sandbox/` | `internal/jobtypes`（型のみ） / `internal/observability` | `cmd/` / `internal/grading` / `internal/llm` / `internal/db` |
| `internal/db/` | `internal/jobtypes`（型のみ） / `internal/observability` | `cmd/` / `internal/grading` / `internal/llm` / `internal/sandbox` |
| `internal/jobtypes/` | （標準ライブラリのみ、生成物のため終端）| 全て |
| `internal/observability/` | （標準ライブラリ + OTel SDK のみ）| 業務 package 全て |

**補足ルール**：

- **依存は一方向**：A → B かつ B → A を作らない。`internal/` 内の package 間も同じ
- **`internal/jobtypes/` を終端に保つ**：quicktype による自動生成物（`apps/api/job-schemas/` から `mise run worker:grading:types-gen` で生成、[ADR 0006](../../../adr/0006-json-schema-as-single-source-of-truth.md)）のため、手書き拡張は別 package（`internal/llm` 等）で被せる
- **`internal/observability/` を別系統に保つ**：trace_id / metrics / logger の初期化は `cmd/worker/main.go` で 1 回だけ行い、業務 package は受け取った logger / span だけを使う
- **`grading` を集約点に**：採点ジョブの処理本体は `internal/grading/` がオーケストレーターとなり、`llm` + `sandbox` + `db` を組み合わせる

### D. 命名規則

| 種別 | 命名パターン | 例 |
|---|---|---|
| package 名 | 短い小文字、複合語は連結 | `grading` / `llm` / `sandbox` / `jobtypes` / `observability` |
| ファイル名 | snake_case | `grading_job.go` / `judge_runner.go` / `docker_sandbox.go` |
| エクスポート識別子（型・関数）| PascalCase | `GradingJob` / `JudgeRunner` / `RunInSandbox` |
| 非エクスポート識別子 | camelCase | `parsePayload` / `dockerClient` |
| エラー定数 | `Err<Domain>` | `ErrJobNotFound` / `ErrSandboxTimeout` |
| インタフェース | 1 メソッドなら動詞 + `er`、複数なら名詞 | `Runner` / `LLMProvider` / `SandboxExecutor` |
| テストファイル | `<source>_test.go` | `grading_job_test.go` |

### E. 「やってはいけないこと」（NG パターン一覧）

`apps/workers/grading/README.md` および `worker.md` の OK/NG コード片で取り上げる代表 NG。

#### E-1. 配置・import の NG

1. `internal/llm/` から `internal/grading/` を import（逆流、`§C`）
2. `internal/jobtypes/` を手書きで編集（quicktype の再生成で消える、[ADR 0006](../../../adr/0006-json-schema-as-single-source-of-truth.md)）
3. `internal/` 配下を別 Go module から import（Go の `internal/` 規約で禁止、ビルドエラーになる）
4. LLM SDK を `apps/api/` 配下に置く（LLM は Worker に閉じる、[ADR 0040](../../../adr/0040-worker-grouping-and-llm-in-worker.md)）
5. プロンプト YAML をリポジトリ root の `packages/prompts/` に置く（`apps/workers/grading/prompts/judge/` に同居、[ADR 0040](../../../adr/0040-worker-grouping-and-llm-in-worker.md)）

#### E-2. 実装の NG

6. サンドボックス起動時にホストの volume を生のまま mount（[ADR 0009](../../../adr/0009-disposable-sandbox-container.md) の隔離原則違反、tmpfs / read-only mount を使う）
7. ジョブ取得を `SELECT ... FOR UPDATE` 単独で書く（必ず `SKIP LOCKED` を併用、複数 Worker でのスタックジョブを避ける、[ADR 0004](../../../adr/0004-postgres-as-job-queue.md)）
8. trace_id の伝播を忘れる（jobs テーブルの `trace_context` カラムから W3C Trace Context を復元、[ADR 0010](../../../adr/0010-w3c-trace-context-in-job-payload.md)）
9. LLM プロバイダを直接 import（必ず `internal/llm.Provider` interface 経由、設定で差し替え可能に、[ADR 0007](../../../adr/0007-llm-provider-abstraction.md)）
10. エラーハンドリングで `panic` を多用（Go 慣習：エラーは戻り値で返す、`panic` は本当に回復不能な状態のみ）

---

## 1. ディレクトリ構造の最終状態

**目的**：`apps/workers/grading/` 配下に Go の package 分割を 1 つの方針で固定する。以降の機能実装はこの `cmd/` + `internal/<sub>/` のどこに置くかを判断するだけ、という状態を作る。

**最終状態**（§自律実行ポリシー §7 の通り、初期状態のばらつきは問わない）：

- `apps/workers/grading/` 配下が §A のツリーに一致している：
  - `cmd/worker/main.go` が存在し、`internal/*` の全 package を `import` で参照して組み立てている
  - `internal/{jobtypes,llm,sandbox,grading,db,observability}/` の 6 サブディレクトリすべてに README が存在
- **計 9 個の `README.md` ファイル**が存在する：
  - `apps/workers/grading/README.md`（1 個、`grading/` 直下）
  - `cmd/README.md` + `cmd/worker/README.md`（2 個）
  - `internal/README.md` + `internal/{jobtypes,llm,sandbox,grading,db,observability}/README.md`（7 個）
- 04-worker.md 由来の `main.go` が `cmd/worker/main.go` に移設されている（パス変更後も `mise run worker:grading:dev` が動作する）
- §A のツリーに無い別のディレクトリ（例：`apps/workers/grading/services/` のような不適切な命名、`pkg/` で公開 package を切る等）が残っていない

**完了基準**：

- 上記 9 個の README.md が（空でも可）存在する
- `cmd/worker/main.go` への移設が完了し、`mise run worker:grading:dev` がエラーなく起動する
- `mise run worker:grading:lint` / `mise run worker:grading:test` / `mise run worker:grading:audit` がすべて clean で通る
- 04-worker.md 配置済の `go.mod` / `.golangci.yml` / `sandbox/Dockerfile` / `prompts/judge/` に変更が入っていない

**関連 ADR**：[ADR 0016](../../../adr/0016-go-for-grading-worker.md)（Go 採用）/ [ADR 0019](../../../adr/0019-go-code-quality.md)（golangci-lint / govulncheck）/ [ADR 0040](../../../adr/0040-worker-grouping-and-llm-in-worker.md)（LLM Worker 集約、プロンプト同居）/ [ADR 0009](../../../adr/0009-disposable-sandbox-container.md)（使い捨てサンドボックス）/ [ADR 0007](../../../adr/0007-llm-provider-abstraction.md)（LLM プロバイダ抽象化）

---

## 2. 各 package の README.md の最終状態

**目的**：各サブ package に人間向けの 1 ファイル README を置き、初学者が階層を辿る時に「この package は何の置き場か」を即把握できるようにする。Backend / Frontend レイヤ分割フェーズと同じ書き分け方針（[05-backend-layers.md §2](./05-backend-layers.md) / [06-frontend-layers.md §2](./06-frontend-layers.md) 参照）。

**最終状態で存在すべき README**（全 9 ファイル）：

| パス | 重視する内容 |
|---|---|
| `apps/workers/grading/README.md` | トップの全体図（手順 3 で詳述） |
| `cmd/README.md` | エントリポイント置き場の役目、将来 `cmd/migrator/` 等が増える場合の運用 |
| `cmd/worker/README.md` | `main.go` の役目（全 `internal/*` を組み立ててジョブループを起動）、observability の初期化はここで 1 回だけ |
| `internal/README.md` | `internal/` の Go 規約（リポジトリ外からの import 不可）、6 サブ package の対比表 |
| `internal/jobtypes/README.md` | quicktype 自動生成物の置き場、手書き禁止、再生成コマンド（`mise run worker:grading:types-gen`） |
| `internal/llm/README.md` | LLM プロバイダ抽象化 interface（`Provider`）、Claude / Gemini 等の実装差し替え点 |
| `internal/sandbox/README.md` | Docker サンドボックス操作、使い捨てコンテナ生成・破棄、tmpfs mount 等の隔離設計 |
| `internal/grading/README.md` | 採点フローの**オーケストレーター**、`llm` + `sandbox` + `db` を組み合わせる |
| `internal/db/README.md` | Postgres ジョブキュー取得（`SELECT FOR UPDATE SKIP LOCKED`）+ 結果書き戻し、Backend と同じ DB を共有 |
| `internal/observability/README.md` | OTel SDK 初期化 + 構造化ログ + Prometheus exporter、trace_context payload からの復元 |

**書き方の規約**：[05-backend-layers.md §2 の「書き方の規約」](./05-backend-layers.md) と同じ（コード片は書かず概念ベース、専門用語を平易な日本語で、紛らわしい組には対比表）。

**完了基準**：

- 上記 9 個の README.md が存在する
- 各 README は「とは何か」セクションを冒頭に持つ
- 紛らわしい組（`internal/grading/` と `internal/llm/`、`internal/sandbox/` と root の `sandbox/`、`internal/db/` と Backend `apps/api/app/db/`）には対比的な記述がある
- 全 README で `§E` の NG パターンから該当する 1〜4 件が「やってはいけないこと」または本文の戒めとして転記されている

---

## 3. `apps/workers/grading/README.md` の最終状態

**目的**：人間が `apps/workers/grading/` 直下を開いた時に、package 間の呼び出しの向きが 1 枚の図で見て取れる状態にする。

**最終状態**（`apps/workers/grading/README.md` が下記をすべて含む）：

A. **package 一覧表**：8 ディレクトリ（`cmd/worker/` + 6 サブ internal + `prompts/judge/` + `sandbox/`）を「これは何か（役目）」付きで表にし、各セルから対応する README へリンクが張られている

B. **ASCII 図で package 間の呼び出し方向**を示す。`§C` の import 方向と一致する。叩き台：
   ```text
                         [jobs テーブル]
                              │
                              ▼
                        ┌────────────┐
                        │ cmd/worker │  main: 全 internal を組み立て
                        └─────┬──────┘
                              │
                  ┌───────────┴────────────┐
                  ▼                        ▼
            ┌──────────┐              ┌──────────────┐
            │ internal │              │ observability│  起動時 1 回だけ初期化
            │ /grading │              └──────────────┘
            └──┬───────┘
               │ 採点フローのオーケストレーター
       ┌───────┼─────────┬────────────┐
       ▼       ▼         ▼            ▼
   ┌─────┐ ┌─────┐ ┌─────────┐  ┌────────┐
   │ llm │ │ db  │ │ sandbox │  │jobtypes│  生成物・終端
   └─────┘ └─────┘ └─────────┘  └────────┘
   ```

C. **読み方の具体例**：
   - 正常な採点フロー：`cmd/worker` が `db` からジョブ取得 → `grading` がオーケストレートし `llm`（judge 呼び出し）+ `sandbox`（テスト実行）を呼ぶ → 結果を `db` に書き戻し
   - `jobtypes/` が終端である意味（生成物のため手書きしない、終端を壊さない）
   - `observability/` が別系統である意味（`main.go` で 1 回初期化、業務 package は受け取った logger / span だけを使う）
   - `internal/` の Go 規約（リポジトリ外からの import が**コンパイラ強制で**禁止される）

D. **`## やってはいけないこと` セクション**が `§E` の NG パターン一覧から **4 件以上**を箇条書きで含む（`§E-1` 配置・import 系を中心に、`§E-2` の実装 NG も適宜）

**完了基準**：

- `apps/workers/grading/README.md` を開けば「何の機能がどう繋がるか」が図 + 補足で完結する
- 「やってはいけないこと」が `§E` から 4 件以上列挙されている
- 図中の矢印が `§C` の import 方向表と一致している

---

## 4. 実装契約を `.claude/rules/worker.md` に固定

**目的**：Claude が新規実装時に参照する「実装契約」として、ディレクトリ配置 + import 方向 + 命名規則 + package 単位の責務を、表 + コード片で曖昧さなく固定する。人間向け README が「概念で理解する」のに対し、rules ファイルは「パターンマッチで判定する」用途。

### 4-1. `.claude/rules/worker.md` の最終状態

`§自律実行ポリシー §7` の通り、初期状態（既存セクションの有無 / 内容のズレ）は不問。**最終状態が下記の条件をすべて満たしていればよい**。

A. **`## ディレクトリ構成（`apps/workers/grading/`）` セクションが存在する**。内容は次を含む：
- `§A` のツリー（コメント付き）
- `§B` の設計方針 5 点（cmd 慣習 / internal 強制 / LLM Worker 集約 / プロンプト同居 / Dockerfile 分離）
- `§C` への内部リンク（または `§C` の表を直接ここに転記）

B. **`### package 間の import 方向` セクションが存在する**。内容は次を含む：
- `§C` の import 可 / 禁止表（全 package 行）
- `§C` の補足ルール（依存一方向 / `internal/jobtypes/` 終端 / `observability` 別系統 / `grading` 集約点）
- OK / NG コード片を **4 例以上** `.go` コードブロックで含む：
  - ✅ `cmd/worker/main.go` が全 `internal/*` を import して組み立てる
  - ❌ `internal/llm/` が `internal/grading/` を import（逆流）
  - ❌ `internal/jobtypes/` を手書きで拡張
  - ❌ LLM プロバイダ実装を `internal/llm/` 外で直接 import

C. **`## ジョブキュー取得` セクション**が以下を含む：
- `SELECT FOR UPDATE SKIP LOCKED` の使い方（[ADR 0004](../../../adr/0004-postgres-as-job-queue.md)）
- `LISTEN/NOTIFY` で push 通知を受ける構造
- ジョブの retry / DLQ 戦略（R2 で詳細化、R0-7 では雛形のみ）

D. **`## LLM 呼び出し` セクション**が以下を含む：
- `internal/llm.Provider` interface 定義（`Generate(ctx, prompt, opts) (Response, error)` 等）
- Claude / Gemini 等の実装は `internal/llm/<provider>/` 配下に分離
- プロンプトは `prompts/judge/*.yaml` から読み込む（[.claude/rules/prompts.md](../../../../.claude/rules/prompts.md)）

E. **`## サンドボックス操作` セクション**が以下を含む：
- 公式 `github.com/docker/docker/client` を使う
- 使い捨てコンテナ（ジョブごとに生成・破棄）の原則（[ADR 0009](../../../adr/0009-disposable-sandbox-container.md)）
- tmpfs mount / read-only mount / network 切断 / ulimit 等の隔離設計

F. **`## observability` セクション**が以下を含む：
- W3C Trace Context payload の復元（jobs テーブルの `trace_context` カラム、[ADR 0010](../../../adr/0010-w3c-trace-context-in-job-payload.md)）
- 構造化ログ（slog）+ Prometheus exporter + OTel SDK の組み立て

G. **`## コーディング規約` セクション**が以下を含む：
- gofmt（gofumpt） + golangci-lint 必須（[ADR 0019](../../../adr/0019-go-code-quality.md)）
- `Any`（`interface{}`）の使用を最小化、型を明示
- エラーは戻り値、`panic` は本当に回復不能な場合のみ
- テスト：標準 `testing` + `stretchr/testify`（[ADR 0038](../../../adr/0038-test-frameworks.md)）

H. **`## 新規機能の追加パターン` セクション**が以下を含む：
- ジョブ種別を増やす時の手順（`apps/api/app/schemas/jobs/<job_type>.py` 追加 → `mise run api:job-schemas-export` → `mise run worker:grading:types-gen` → `internal/<処理>/` 実装）

I. **`## ツーリング` セクション**が `mise run worker:grading:*` タスク表を含む（dev / test / lint / audit / deps-check / types-gen / sandbox-build）

> **書き換え方の指針**：上記の「**最終的にこうなっていればよい**」を満たすために、既存 `worker.md` から関連箇所を探して整合させる。一致しているものは触らない、無いものは足す、矛盾しているものは書き換える（§自律実行ポリシー §7）。

### 4-2. `.claude/CLAUDE.md` の最終状態

- `.claude/CLAUDE.md` の「ルールファイルの管理」リストに `.claude/rules/worker.md` が列挙されている：「Worker（採点 / 問題生成、Go）に関すること → `.claude/rules/worker.md`」の 1 行が存在する
- 該当行が無ければ追加し、別パスを指している場合は修正する

**完了基準**：

- `worker.md` の「§ディレクトリ構成（`apps/workers/grading/`）」セクションに `§A` のツリー + 設計方針 5 点 + `§C` の import 方向表 + OK/NG 例（4 例以上）が揃っている
- import 方向表に全 package が行として並ぶ
- `## ジョブキュー取得` / `## LLM 呼び出し` / `## サンドボックス操作` / `## observability` / `## コーディング規約` / `## 新規機能の追加パターン` / `## ツーリング` の各セクションが揃っている
- `CLAUDE.md` の「ルールファイルの管理」リストに `worker.md` が列挙されている

---

## 5. 進捗トラッカーへの反映の最終状態

**目的**：本フェーズが終わったことを、プロジェクトの進捗管理仕組み（ロードマップ / プロジェクト管理ツール / README 等）に反映する。

**最終状態**：

- [01-roadmap.md](../01-roadmap.md) の R0-7 行が、状態列 `✅ 完了` + 詳細手順列が本ファイルへのリンク `[r0-setup/07-worker-layers.md](./r0-setup/07-worker-layers.md)` になっている（本フェーズ完了前の `🔴 未着手` 表記 + `（要作成）` 注記は完了時に書き換える）
- 本ファイル冒頭のステータスマークが完了時に `# 07. Worker（Go）ディレクトリ構成（✅ 完了）` に書き換わっている

**完了基準**：

- 進捗トラッカー上で本フェーズが完了になっている
- 本ファイルへのリンクが進捗トラッカーから辿れる
- 本ファイル冒頭のステータスマークが完了状態（`✅`）になっている

---

## 関連

- 親階層：[README.md: 役割別 setup の後段](./README.md#役割別-setup-の後段レイヤ分割フェーズ)
- 前フェーズ：[04-worker.md](./04-worker.md)（apps/workers/grading workspace + main.go skeleton + sandbox Dockerfile 雛形の配置元）
- 並行フェーズ：[05-backend-layers.md](./05-backend-layers.md) / [06-frontend-layers.md](./06-frontend-layers.md)（同じ「レイヤ分割」パターン）
- ロードマップ：[01-roadmap.md: Now：R0 基盤](../01-roadmap.md#nowr0-基盤直列初期慣行--役割別環境構築--レイヤ分割--mcp-整備)
- 実装契約 SSoT：[.claude/rules/worker.md](../../../../.claude/rules/worker.md)
- 関連 ADR：[ADR 0016](../../../adr/0016-go-for-grading-worker.md)（Go 採用）/ [ADR 0019](../../../adr/0019-go-code-quality.md)（Go コード品質）/ [ADR 0040](../../../adr/0040-worker-grouping-and-llm-in-worker.md)（LLM Worker 集約、プロンプト同居）/ [ADR 0009](../../../adr/0009-disposable-sandbox-container.md)（使い捨てサンドボックス）/ [ADR 0007](../../../adr/0007-llm-provider-abstraction.md)（LLM プロバイダ抽象化）/ [ADR 0004](../../../adr/0004-postgres-as-job-queue.md)（Postgres ジョブキュー）/ [ADR 0010](../../../adr/0010-w3c-trace-context-in-job-payload.md)（W3C Trace Context payload）
