# Worker（Go）ディレクトリ構成（🔴 未着手）

## このフェーズで何ができるようになるか

**両 Worker**（`apps/workers/grading/` と `apps/workers/generation/`）配下に Go の **同一 9 package パターン**（`cmd/<worker>/` + `internal/{config,observability,db,job,sandbox,llm,judge,jobtypes,<worker>}/`）を確定し、各 package の責務 + import 方向 + 命名規則を `.claude/rules/worker.md` に「実装契約」として固定する。本フェーズが終わると以下ができるようになる：

- 後続の Worker 機能実装（LLM プロバイダ抽象化 / 採点ロジック / 問題生成ロジック / DB 書き戻し）が**両 Worker で同じ判断基準**で「悩まずに迷わずどの package に置くかを選ぶ」状態になる
- 各 package の責務・import 方向が rules ファイルに固定され、Claude が自動 load して規約に従ったコードを生成できる
- 各 package に人間向け README が揃い、両 Worker の `internal/` 配下の役割分担が一目で分かる
- 型同期パイプライン Worker 側合流フェーズの受け皿（`internal/jobtypes/`）が両 Worker で配置済となる

**両 Worker を同パターンにする理由**（[ADR 0040](../../../adr/0040-worker-grouping-and-llm-in-worker.md)）：grading と generation はジョブ種別が違うが、「Postgres ジョブキュー consumer + 使い捨て sandbox + LLM 呼び出し + judge 評価」という基本骨格は共通。同じレイヤ分割を強制することで、R1-2（LLM 抽象化）/ R1-5（採点）/ R7（生成）の機能実装が「両 Worker で対称な構造で書ける」状態を作る。

---

> **前提フェーズ**：[Go 環境構築フェーズ](./worker.md) 完了済（**両 Worker** の `cmd/<worker>/main.go` skeleton / `go.mod` / `.golangci.yml` / `.gitignore` が配置済、grading 側に `sandbox/Dockerfile`、`mise run worker:<worker>:dev` で両 Worker 起動可能、両 Worker で golangci-lint / govulncheck / go mod tidy -diff がローカル + CI 両方で緑）
> **次フェーズ**：R1 開始（LLM プロバイダ抽象化フェーズが本フェーズの成果物に依存、→ [01-roadmap.md](../01-roadmap.md)）
>
> **本フェーズの位置付け**：[README.md: 役割別 setup の後段](./README.md#役割別-setup-の後段レイヤ分割フェーズ) を参照。言語ツーリングが整った上に、その言語側でプロジェクト固有のレイヤ分割を確定するフェーズで、「悩む余地のない基本構造」とは別物として扱う（[backend-layers.md](./backend-layers.md) / [frontend-layers.md](./frontend-layers.md) と同パターン）。
>
> **書き方の方針**：依存ライブラリのインストールを伴わないため「環境構築 + 品質ゲート 5 ステップ」パターンには載らない。代わりに「**決定値の確認 → ディレクトリ作成（両 Worker） → 各 package README（両 Worker） → 全体 README（両 Worker） → rules ファイルに実装契約として固定**」の構造で進める（Backend / Frontend レイヤ分割フェーズと同パターン）。
>
> **本ファイルと `.claude/rules/worker.md` の役割分担**：本ファイルが「**手順 + このフェーズで下す決定**」の SSoT、`worker.md` が「**実装契約（R1 以降の機能実装が読む規約）**」の SSoT。`§決定値` の表（`§A` ツリー / `§C` import 方向 / `§D` 命名規則）は両ファイルに同じ値を書く。一方を更新したら他方も合わせて更新する。
>
> **doc 内の `<worker>` 表記**：grading / generation の 2 値を取るテンプレ変数として使う。9 package のうち 1 つ（orchestrator）と `cmd/<worker>/` は Worker 名と一致する。他の 8 package は **両 Worker で同一名**。

---

## 自律実行ポリシー（Claude が本ファイルを読んで作業する時の前提）

本ファイルは Claude に**そのまま実行を依頼**する想定で書かれている。次の原則を守って、ユーザーに確認を取らずに最後まで進める。

1. **ユーザーに設計上の確認を求めない**：`§決定値` に書かれた選択（cmd path / 9 package 分割 / `internal/` 配下サブ構成 / LLM Worker 集約方針 / import 方向 / 両 Worker 対称適用 等）は**決定済みで議論しない**。関連 ADR（[ADR 0016](../../../adr/0016-go-for-grading-worker.md) / [ADR 0019](../../../adr/0019-go-code-quality.md) / [ADR 0040](../../../adr/0040-worker-grouping-and-llm-in-worker.md) / [ADR 0009](../../../adr/0009-disposable-sandbox-container.md) / [ADR 0007](../../../adr/0007-llm-provider-abstraction.md)）は既に消化済みのため、再検討しない。
2. **関連ファイルが本ファイルとズレていたら、関連ファイル側を直す**：以下のファイル群が `§決定値` と違う状態にあれば、本ファイルを真として書き換える：
   - `apps/workers/grading/` および `apps/workers/generation/` 配下のフォルダ・README（`§A` のツリーに対応、**両 Worker で対称**）
   - `.claude/rules/worker.md`（Worker 全般の実装契約、両 Worker のツリー + import 方向を含む）
   - `.claude/CLAUDE.md`（「ルールファイルの管理」リストに `worker.md` が列挙されていること、generation の Go module 完了の事実反映）
   - `docs/requirements/5-roadmap/01-roadmap.md`（本フェーズに該当する行の状態列とリンク列）
3. **新規ブランチを切る**：[CLAUDE.md: ブランチ運用](../../../../.claude/CLAUDE.md#ブランチ運用) に従い、`feature/worker/layers`（または同等の `feature/worker/<名前>`）で作業する。`main` で直接作業しない。
4. **コミット・PR 作成は明示指示があるまで行わない**：[CLAUDE.md: Git 操作の禁止](../../../../.claude/CLAUDE.md#git-操作の禁止) に従い、`git add` / `git commit` / `git push` / PR 作成はユーザーから明示指示が出るまで保留する。ファイル作成・編集は自動で進めてよい。
5. **初期状態のばらつきに対する方針**（両 Worker 各々に同じく適用）：
   - 想定 package が存在しない → 作る（空ディレクトリ + `.gitkeep` ではなく `README.md` を入れる）
   - 想定 package が存在し中身が空 → README を入れる
   - 想定 package が存在し中身がある（既存の `internal/jobtypes/` 等、[worker.md](./worker.md) フェーズで埋まったもの）→ 中身を確認して `§決定値` と矛盾する部分のみ書き換える。worker.md 由来の実装ファイル（`go.mod` / `go.sum` / `.golangci.yml` / `.gitignore` / `cmd/<worker>/main.go` / `internal/jobtypes/.gitignore` / `apps/workers/grading/sandbox/Dockerfile` / `apps/workers/grading/sandbox/.dockerignore`）は本フェーズでは触らない（[worker.md](./worker.md) の SSoT を尊重する）
   - `.claude/rules/worker.md` に「§ディレクトリ構成（両 Worker）」「§レイヤ間の import 方向」セクションが無い、または `§A` / `§C` / `§D` と矛盾する → 機械可読版に展開して追加 or 書き換える（手順 4 が SSoT）
   - `.claude/CLAUDE.md` の「ルールファイルの管理」リストに `worker.md` が無ければ追加する。generation Worker が「Go module 未着手」と書かれていたら更新する
6. **完了後に検証コマンドを必ず流す**：`mise run worker:grading:lint` / `worker:grading:test` / `worker:generation:lint` / `worker:generation:test` を順に実行し、**4 つすべて** clean になることを確認する。失敗があれば修正して再実行（ユーザーに投げ返さない）
7. **「書き換える」「削除する」「追加する」「リネームする」の解釈**：本ドキュメント中のこれらの動詞は、すべて**最終状態を §決定値 に合わせる作業**を指す。**初期状態がどうであれ、最終的に §決定値 と一致していればよい**（idempotent）

---

## 決定値（このフェーズで固定する、議論しない設計）

### A. ディレクトリ構成

**両 Worker で共有する 9 package テンプレート**（`<worker>` = `grading` / `generation`）：

```text
apps/workers/<worker>/
├── go.mod                                           # worker.md 配置済
├── go.sum                                           # worker.md 配置済（依存追加時に生成）
├── .golangci.yml                                    # worker.md 配置済（両 Worker で同一内容）
├── .gitignore                                       # worker.md 配置済（go build バイナリ除外）
├── README.md                                        # 全体図 + やってはいけないこと（本フェーズで update / 作成）
├── cmd/                                             # エントリポイント置き場（main package）
│   └── <worker>/                                    # binary 名 = <worker>（worker.md 配置済）
│       ├── README.md                                # 本フェーズで作成
│       └── main.go                                  # worker.md 配置済（skeleton、本フェーズでは触らない）
├── internal/                                        # private packages（他 module から import 不可、Go 規約）
│   ├── README.md                                    # 本フェーズで作成
│   ├── config/                                      # 環境変数読み込み（caarlos0/env/v11）
│   │   └── README.md                                # 本フェーズで作成
│   ├── observability/                               # 構造化ログ（slog）+ OpenTelemetry + (R4) Prometheus（lump）
│   │   └── README.md                                # 本フェーズで作成
│   ├── db/                                          # pgx pool + transaction helpers（純 infrastructure）
│   │   └── README.md                                # 本フェーズで作成
│   ├── job/                                         # claim / listener / reclaim / complete（queue domain logic）
│   │   └── README.md                                # 本フェーズで作成
│   ├── sandbox/                                     # Docker SDK ラッパ + 隔離設定（ADR 0009、両 Worker が同じ image を起動）
│   │   └── README.md                                # 本フェーズで作成
│   ├── llm/                                         # LLM プロバイダ抽象化（ADR 0007）。実装は internal/llm/<provider>/
│   │   └── README.md                                # 本フェーズで作成
│   ├── judge/                                       # LLM-as-a-Judge prompt 整形 + response パース（grading: 解答評価 / generation: 問題評価）
│   │   └── README.md                                # 本フェーズで作成
│   ├── jobtypes/                                    # apps/api/job-schemas/ から quicktype で生成された Go struct（worker.md で雛形配置済、本フェーズで README 追加）
│   │   ├── .gitignore                               # worker.md 配置済（生成物を除外、README は commit）
│   │   └── README.md                                # 本フェーズで作成
│   └── <worker>/                                    # オーケストレーター（grading: 採点フロー / generation: 問題生成フロー）
│       └── README.md                                # 本フェーズで作成
└── prompts/                                         # LLM プロンプト（ADR 0040、本フェーズでは触らない、Worker ごとに subdir が違う）
    └── <worker専用 prompt subdir>/                  # grading: judge/、generation: generation/ + judge/
```

**Worker 固有の差分**（テンプレートからの逸脱はこれだけ）：

| 差分項目 | grading | generation |
|---|---|---|
| `cmd/<worker>/` の `<worker>` | `cmd/grading/` | `cmd/generation/` |
| `internal/<worker>/` orchestrator の `<worker>` | `internal/grading/`（採点フロー：job → sandbox + judge → db） | `internal/generation/`（生成フロー：job → llm + sandbox + judge → db） |
| `sandbox/Dockerfile` 所有 | **所有**：`apps/workers/grading/sandbox/{Dockerfile,.dockerignore}` | **所有しない**：grading の `ai-coding-drill-sandbox:latest` image を Docker SDK で起動 |
| `prompts/` 配下 | `prompts/judge/`（解答評価プロンプト） | `prompts/generation/`（問題生成プロンプト） + `prompts/judge/`（問題評価プロンプト） |
| go module 名 | `github.com/yzanbo/ai-coding-drill-python/apps/workers/grading` | `github.com/yzanbo/ai-coding-drill-python/apps/workers/generation` |

> **既存実装ファイル**（[worker.md](./worker.md) 配置済、本フェーズでは触らない）：両 Worker の `go.mod` / `.golangci.yml` / `.gitignore` / `cmd/<worker>/main.go` / `internal/jobtypes/.gitignore` / `prompts/<subdir>/` 配下、および grading のみの `sandbox/Dockerfile` / `sandbox/.dockerignore`。中身の SSoT は [worker.md](./worker.md) の各 step。
>
> **`main.go` は移動しない**：worker.md フェーズで両 Worker とも `cmd/<worker>/main.go` に配置済。`apps/workers/<worker>/cmd/<worker>/main.go` で `<worker>` 名が一致する慣習で確定済み（binary 名衝突を避けるため `cmd/worker/` 共通名は不採用）。
>
> **README 個数**：**両 Worker 合計 22 ファイル**＝Worker ごとに 11 ファイル × 2。1 Worker 分の内訳＝top（`apps/workers/<worker>/README.md`）+ `cmd/<worker>/README.md` + `internal/README.md` + `internal/{config,observability,db,job,sandbox,llm,judge,jobtypes,<worker>}/README.md`（9 個）。

### B. 配置に関する重要な選択（なぜそうしたか）

| 論点 | 採用 | 不採用 | 採用理由 |
|---|---|---|---|
| エントリポイントの位置 | **`cmd/grading/main.go`**（binary 名 = grading） | `cmd/worker/main.go`（汎用名）/ `apps/workers/grading/main.go`（リポジトリ直下） | 将来 `apps/workers/generation/cmd/generation/` と対称になり、`docker ps` / `go install` の binary 名で grading / generation を識別可能。`cmd/worker/` 共通名にすると 2 module で同一 binary 名になり判別不可 |
| public package vs internal | **全て `internal/` 配下** | `pkg/<name>/` で外部 module 公開 | このリポジトリ外から import される想定が無い。`internal/` にすることで Go コンパイラレベルで「リポジトリ外から import 不可」を強制 |
| `internal/db/` と `internal/job/` の分割 | **分離**（`db/` = pgx infrastructure、`job/` = queue domain） | 1 package に統合（`internal/db/` に queue SQL も置く） | 「pgx 接続管理」と「queue claim/reclaim semantics」は責務が違う。分離すると `job → db` 一方向 layering が綺麗、将来 `internal/results/` 等を追加する時も `db/` を肥大化させない |
| `internal/llm/` と `internal/judge/` の分割 | **分離**（`llm/` = provider 抽象、`judge/` = grading 専用 prompt） | 1 package に統合（`judge/` 内で provider 直接呼び出し） | `llm/` の抽象化（ADR 0007）は generation worker も再利用予定。`judge/` は grading 専用の prompt / response パース層。混ぜると provider 切り替えが grading 用途に縛られる |
| `internal/observability/`（lump） | **`slog` + `OTel` + (R4) Prometheus を 1 package** | `internal/log/` + `internal/otel/` 分割 | slog の trace_id 連動 handler は OTel API を import するため、`log/` を独立にすると `log → otel` 依存が発生し境界が曖昧。lump で `observability.Init(ctx, cfg)` 1 関数に集約する方が main.go も簡潔 |
| `internal/grading/` orchestrator | **採用**（採点フロー本体は package 化） | `cmd/grading/main.go` 内にインライン | orchestrator が 100〜200 行規模になるため、main.go は組み立て + signal handling だけに保つ。`grading.Process(ctx, deps, job)` を fake deps で table-driven test 可能 |
| LLM 呼び出しの置き場 | **`internal/llm/`**（Worker 内）| `apps/api/app/llm/` 等の Backend 側 | ユーザー応答性と LLM レイテンシを分離するため。Backend は enqueue + 結果取得のみ（→ [ADR 0040](../../../adr/0040-worker-grouping-and-llm-in-worker.md)） |
| プロンプトの置き場 | **`prompts/judge/`**（Worker 同居）| `packages/prompts/`（旧構想）| プロンプトは利用 Worker と同居（→ [ADR 0040](../../../adr/0040-worker-grouping-and-llm-in-worker.md)）。`packages/prompts/` は廃止（[.claude/CLAUDE.md](../../../../.claude/CLAUDE.md) 参照） |
| サンドボックス Dockerfile の位置 | **`sandbox/Dockerfile`**（Go コード外）| `internal/sandbox/Dockerfile` | Dockerfile は Go の build 対象外。Go コードと混在させると `go test ./...` のスコープが曖昧になるため、別ディレクトリに分離 |

### C. 各 package の import 方向（layer-based）

新規機能追加時、各 package から何を import してよいかを下記表で固定する。R1 以降の全機能実装はこの契約に従う。**両 Worker（grading / generation）に同じ表が対称適用される**（`<worker>` を `grading` / `generation` に置換して読む）。Go の `internal/` 規約により他 module（grading ↔ generation）への import は不可なので、表は 1 Worker 内の関係のみ記述。

**layer 図**：

```text
Layer 3（entrypoint）
  cmd/<worker>/                 → 全 internal/* を組み立て

Layer 2（orchestration）
  internal/<worker>/            → job, sandbox, judge, db, jobtypes
  ※ grading は internal/grading/、generation は internal/generation/

Layer 1（domain）
  internal/job/                 → db, jobtypes
  internal/judge/               → llm, jobtypes

Layer 0（leaf / infrastructure）
  internal/config/              → （標準ライブラリ + caarlos0/env のみ）
  internal/observability/       → （標準ライブラリ + slog + OTel SDK のみ）
  internal/db/                  → （pgx のみ）
  internal/sandbox/             → （Docker SDK のみ）
  internal/llm/                 → （HTTP client + provider SDK のみ）
  internal/jobtypes/            → （生成物、標準ライブラリのみ）
```

**import 可否表**（両 Worker で同じ表が対称適用される）：

| package | import してよい（internal） | import 禁止 |
|---|---|---|
| `cmd/<worker>/` | 全 `internal/*` | （上位なし） |
| `internal/<worker>/`（orchestrator） | `job` / `sandbox` / `judge` / `db` / `jobtypes` | `cmd/` / `llm`（`judge` 経由で間接利用） / `config`（main で組み立てて DI で受け取る） |
| `internal/job/` | `db` / `jobtypes` | `cmd/` / `<worker>` / `judge` / `llm` / `sandbox` |
| `internal/judge/` | `llm` / `jobtypes` | `cmd/` / `<worker>` / `job` / `db` / `sandbox` |
| `internal/db/` | （pgx のみ、internal は import しない）| `cmd/` / 全 `internal/*` |
| `internal/sandbox/` | （Docker SDK のみ、internal は import しない）| `cmd/` / 全 `internal/*` |
| `internal/llm/` | （HTTP client + provider SDK のみ） | `cmd/` / 全 `internal/*` |
| `internal/config/` | （caarlos0/env のみ）| `cmd/` / 全 `internal/*` |
| `internal/observability/` | （slog + OTel SDK のみ）| 業務 package 全て |
| `internal/jobtypes/` | （標準ライブラリのみ、生成物のため終端）| 全て |

**補足ルール**：

- **依存は一方向**：A → B かつ B → A を作らない。`internal/` 内の package 間も同じ
- **両 Worker module 跨ぎの import は禁止**：`apps/workers/grading/internal/llm/` を `apps/workers/generation/` から import 不可（Go の `internal/` 規約 + 独立 module）。LLM 抽象化を再利用する時は **同名 package を両 Worker に複製**するか、将来共通 module を切り出す（[ADR 0040](../../../adr/0040-worker-grouping-and-llm-in-worker.md) は当面コード重複を許容）
- **`internal/jobtypes/` を終端に保つ**：quicktype による自動生成物（`apps/api/job-schemas/` から `mise run worker:<worker>:types-gen` で生成、[ADR 0006](../../../adr/0006-json-schema-as-single-source-of-truth.md)）のため、手書き拡張は別 package で被せる
- **`internal/observability/` は context 経由で透過利用**：trace_id / metrics / logger の初期化は `cmd/<worker>/main.go` で 1 回だけ行い、業務 package は `slog.InfoContext(ctx, ...)` / `otel.Tracer("name").Start(ctx, ...)` を直接使う（observability package を import しない）
- **`internal/config/` は entrypoint でのみ読む**：`cmd/<worker>/main.go` が `config.Load()` を呼び、得た値を各業務 package に DI で渡す。業務 package が `os.Getenv` を直接読まない
- **`internal/<worker>/` を集約点に**：ジョブの処理本体は `internal/<worker>/` がオーケストレーターとなり、`job` + `sandbox` + `judge` + `db`（+ generation は `llm` も直接使う場面あり）を組み合わせる
- **`internal/llm/` のサブ package**：provider 実装は `internal/llm/anthropic/` / `internal/llm/google/` / `internal/llm/openai/` / `internal/llm/openrouter/`（R1-2 で配置）。サブ package は親 `llm/` の interface のみ参照し、相互に依存しない。両 Worker で同じ構造を取る

### D. 命名規則

| 種別 | 命名パターン | 例 |
|---|---|---|
| package 名 | 短い小文字、複合語は連結 | `config` / `observability` / `db` / `job` / `sandbox` / `llm` / `judge` / `jobtypes` / `grading` |
| ファイル名 | snake_case | `claim.go` / `listener.go` / `reclaim.go` / `docker_runner.go` / `judge_verdict.go` |
| エクスポート識別子（型・関数）| PascalCase | `GradingJob` / `Claim` / `Verdict` / `Process` |
| 非エクスポート識別子 | camelCase | `parsePayload` / `dockerClient` / `defaultBackoff` |
| エラー値 | `Err<Domain>` | `ErrJobNotFound` / `ErrSandboxTimeout` / `ErrLLMRateLimit` |
| インタフェース | 1 メソッドなら動詞 + `er`、複数なら名詞 | `Runner`（sandbox） / `Provider`（llm） / `Verdicter`（judge） |
| テストファイル | `<source>_test.go` | `claim_test.go` / `docker_runner_test.go` |

### E. 「やってはいけないこと」（NG パターン一覧、両 Worker 共通）

両 Worker の `apps/workers/<worker>/README.md` および `.claude/rules/worker.md` の OK/NG コード片で取り上げる代表 NG。

#### E-1. 配置・import の NG

1. `internal/llm/` から `internal/<worker>/`（orchestrator）を import（逆流、`§C`）
2. `internal/judge/` から `internal/sandbox/` を import（同 Layer 1 内の横断、orchestrator 経由にする）
3. `internal/db/` から `internal/job/` を import（逆流、`db` は infrastructure として独立）
4. `internal/jobtypes/` を手書きで編集（quicktype の再生成で消える、[ADR 0006](../../../adr/0006-json-schema-as-single-source-of-truth.md)）
5. `internal/` 配下を別 Go module から import（Go の `internal/` 規約で禁止。**grading ↔ generation 間も独立 module なので互いに import 不可**、ビルドエラーになる）
6. LLM SDK を `apps/api/` 配下に置く（LLM は Worker に閉じる、[ADR 0040](../../../adr/0040-worker-grouping-and-llm-in-worker.md)）
7. プロンプト YAML をリポジトリ root の `packages/prompts/` に置く（各 Worker の `apps/workers/<worker>/prompts/<subdir>/` に同居、[ADR 0040](../../../adr/0040-worker-grouping-and-llm-in-worker.md)）
8. 業務 package が `os.Getenv` を直接呼ぶ（`internal/config/` で集約、main で DI）
9. grading 側の sandbox image を generation worker 専用にコピーして二重所有（`apps/workers/grading/sandbox/Dockerfile` 1 箇所のみ所有、generation は Docker SDK で `ai-coding-drill-sandbox:latest` を起動して image を共有）

#### E-2. 実装の NG

10. サンドボックス起動時にホストの volume を生のまま mount（[ADR 0009](../../../adr/0009-disposable-sandbox-container.md) の隔離原則違反、tmpfs / read-only mount を使う）
11. ジョブ取得を `SELECT ... FOR UPDATE` 単独で書く（必ず `SKIP LOCKED` を併用、複数 Worker でのスタックジョブを避ける、[ADR 0004](../../../adr/0004-postgres-as-job-queue.md)）
12. trace_id の伝播を忘れる（jobs テーブルの `trace_context` カラムから W3C Trace Context を復元、[ADR 0010](../../../adr/0010-w3c-trace-context-in-job-payload.md)）
13. LLM プロバイダを直接 import（必ず `internal/llm.Provider` interface 経由、設定で差し替え可能に、[ADR 0007](../../../adr/0007-llm-provider-abstraction.md)）
14. エラーハンドリングで `panic` を多用（Go 慣習：エラーは戻り値で返す、`panic` は本当に回復不能な状態のみ）

---

## 1. 両 Worker のディレクトリ構造の最終状態

**目的**：両 Worker（`apps/workers/grading/` と `apps/workers/generation/`）配下に同じ 9 package パターンを固定する。以降の機能実装はこの `cmd/<worker>/` + `internal/<sub>/` のどこに置くかを判断するだけ、という状態を作る。

**最終状態**（§自律実行ポリシー §7 の通り、初期状態のばらつきは問わない）：

- 両 Worker（`apps/workers/grading/` / `apps/workers/generation/`）配下が §A のテンプレートツリーに一致している：
  - `cmd/<worker>/main.go` が存在（R0-8 = [worker.md](./worker.md) で配置済み skeleton、本フェーズでは触らない）
  - `internal/{config,observability,db,job,sandbox,llm,judge,jobtypes,<worker>}/` の 9 サブディレクトリすべてに README が存在
- **両 Worker 合計 22 個の `README.md` ファイル**が存在する（1 Worker 11 個 × 2）：
  - `apps/workers/<worker>/README.md`（1 個、Worker 直下）
  - `cmd/<worker>/README.md`（1 個）
  - `internal/README.md` + `internal/{config,observability,db,job,sandbox,llm,judge,jobtypes,<worker>}/README.md`（10 個 = 1 + 9）
- §A のテンプレートに無い別のディレクトリ（例：`apps/workers/<worker>/services/` のような不適切な命名、`pkg/` で公開 package を切る等）が残っていない

**完了基準**：

- 上記 22 個の README.md が（空でも可）存在する
- `mise run worker:grading:dev` / `mise run worker:generation:dev` が両 Worker でエラーなく起動する
- `mise run worker:grading:lint` / `worker:grading:test` / `worker:grading:audit` および `worker:generation:lint` / `worker:generation:test` / `worker:generation:audit` の**計 6 つすべて**が clean で通る
- [worker.md](./worker.md) 配置済の `go.mod` / `.golangci.yml` / `.gitignore` / `cmd/<worker>/main.go` / `internal/jobtypes/.gitignore` / `apps/workers/grading/sandbox/{Dockerfile,.dockerignore}` / `prompts/<subdir>/` に変更が入っていない

**関連 ADR**：[ADR 0016](../../../adr/0016-go-for-grading-worker.md)（Go 採用）/ [ADR 0019](../../../adr/0019-go-code-quality.md)（golangci-lint / govulncheck）/ [ADR 0040](../../../adr/0040-worker-grouping-and-llm-in-worker.md)（LLM Worker 集約、両 Worker 並立、プロンプト同居）/ [ADR 0009](../../../adr/0009-disposable-sandbox-container.md)（使い捨てサンドボックス）/ [ADR 0007](../../../adr/0007-llm-provider-abstraction.md)（LLM プロバイダ抽象化）

---

## 2. 各 package の README.md の最終状態（両 Worker 対称）

**目的**：両 Worker の各サブ package に人間向けの 1 ファイル README を置き、初学者が階層を辿る時に「この package は何の置き場か」を即把握できるようにする。Backend / Frontend レイヤ分割フェーズと同じ書き分け方針（[backend-layers.md §2](./backend-layers.md) / [frontend-layers.md §2](./frontend-layers.md) 参照）。

**最終状態で存在すべき README**（**両 Worker 合計 22 ファイル**、`<worker>` を `grading` / `generation` 両方で展開）：

| パス | 重視する内容 |
|---|---|
| `apps/workers/<worker>/README.md` | トップの全体図（手順 3 で詳述） |
| `cmd/<worker>/README.md` | `main.go` の役目（全 `internal/*` を組み立ててジョブループを起動）、observability の初期化はここで 1 回だけ |
| `internal/README.md` | `internal/` の Go 規約（リポジトリ外からの import 不可）、9 サブ package の対比表 |
| `internal/config/README.md` | 環境変数集約（caarlos0/env/v11）、業務 package が直接 `os.Getenv` を呼ばない理由 |
| `internal/observability/README.md` | OTel SDK 初期化 + 構造化ログ + (R4) Prometheus exporter、trace_context payload からの復元 |
| `internal/db/README.md` | pgx 接続プール + transaction helpers（pure infrastructure）、Backend `apps/api/app/db/` との責務対比 |
| `internal/job/README.md` | Postgres ジョブキュー取得（`SELECT FOR UPDATE SKIP LOCKED`）+ LISTEN/NOTIFY + reclaim、`internal/db/` への依存方向 |
| `internal/sandbox/README.md` | Docker サンドボックス操作、使い捨てコンテナ生成・破棄、tmpfs mount 等の隔離設計（両 Worker が同じ image を起動） |
| `internal/llm/README.md` | LLM プロバイダ抽象化 interface（`Provider`）、Claude / Gemini 等の実装差し替え点、両 Worker で同名 package が独立 module に存在することの説明 |
| `internal/judge/README.md` | LLM-as-a-Judge prompt 整形 + response パース。grading: 解答評価 / generation: 問題評価で目的が違うが構造は同じ |
| `internal/jobtypes/README.md` | quicktype 自動生成物の置き場、手書き禁止、再生成コマンド（`mise run worker:<worker>:types-gen`） |
| `internal/<worker>/README.md` | orchestrator。grading: `job → sandbox + judge → db` / generation: `job → llm + sandbox + judge → db` |

**書き方の規約**：[backend-layers.md §2 の「書き方の規約」](./backend-layers.md) と同じ（コード片は書かず概念ベース、専門用語を平易な日本語で、紛らわしい組には対比表）。

**両 Worker 同名 package（`config` / `observability` / `db` / `job` / `sandbox` / `llm` / `judge` / `jobtypes`）の README 内容方針**：8 package は両 Worker でほぼ同じ責務なので、内容を**ほぼ複製して可**（DRY を諦める判断）。Worker 固有の差異（例：`judge/` の評価対象が「解答」vs「問題」）はその README 内の 1 段落で書き分ける。「片方を変えると他方が古くなる」リスクは小さい（責務が概念レベルで一致しているため、追従漏れの実害が低い）。共通内容の SSoT 化は将来 `apps/workers/_shared/` 等を切り出す時に検討。

**完了基準**：

- 上記 22 個の README.md が存在する
- 各 README は「とは何か」セクションを冒頭に持つ
- 紛らわしい組（`internal/<worker>/` と `internal/llm/`、`internal/sandbox/` と grading 直下の `sandbox/`、`internal/db/` と Backend `apps/api/app/db/`、`internal/db/` と `internal/job/`）には対比的な記述がある
- 全 README で `§E` の NG パターンから該当する 1〜4 件が「やってはいけないこと」または本文の戒めとして転記されている

---

## 3. 両 Worker の `apps/workers/<worker>/README.md` の最終状態

**目的**：人間が `apps/workers/grading/` / `apps/workers/generation/` 直下を開いた時に、package 間の呼び出しの向きが 1 枚の図で見て取れる状態にする（両 Worker で構造は同じで、orchestrator package 名と呼び出し先（grading: judge を経由 / generation: llm + judge）だけ異なる）。

**最終状態**（両 Worker の `apps/workers/<worker>/README.md` が下記をすべて含む）：

A. **package 一覧表**：9 package（`cmd/<worker>/` + 9 サブ internal）+ `prompts/<subdir>/` + grading のみ `sandbox/` を「これは何か（役目）」付きで表にし、各セルから対応する README へリンクが張られている

B. **ASCII 図で package 間の呼び出し方向**を示す。`§C` の import 方向と一致する。叩き台（`<worker>` を Worker 名に置換）：
   ```text
                         [jobs テーブル]
                              │
                              ▼
                        ┌────────────────┐
                        │ cmd/<worker>   │  main: 全 internal を組み立て
                        └─────┬──────────┘
                              │
                  ┌───────────┴────────────┐
                  ▼                        ▼
            ┌──────────────┐         ┌──────────────────┐
            │ internal     │         │ observability    │  起動時 1 回だけ初期化
            │ /<worker>    │         │ + config         │
            └──┬───────────┘         └──────────────────┘
               │ オーケストレーター
       ┌───────┼─────────┬────────────┬─────────┐
       ▼       ▼         ▼            ▼         ▼
   ┌─────┐ ┌─────┐ ┌─────┐ ┌─────────┐  ┌────────┐
   │ job │ │ db  │ │judge│ │ sandbox │  │jobtypes│  生成物・終端
   └──┬──┘ └─────┘ └──┬──┘ └─────────┘  └────────┘
      │               │
      ▼               ▼
    ┌────┐          ┌─────┐
    │ db │          │ llm │   provider 抽象化
    └────┘          └─────┘
   ```

C. **読み方の具体例**（Worker ごとに差し替え）：
   - 正常な採点フロー（grading）：`cmd/grading` が起動 → `internal/grading` が `job.Claim` でジョブ取得 → `judge`（解答評価 LLM）+ `sandbox`（test 実行）を呼ぶ → 結果を `db` 経由で書き戻し
   - 正常な生成フロー（generation）：`cmd/generation` が起動 → `internal/generation` が `job.Claim` でジョブ取得 → `llm`（生成 LLM）で問題作成 → `sandbox`（模範解答実行で検証）→ `judge`（問題品質評価）→ 結果を `db` 経由で `problems` に INSERT
   - `jobtypes/` が終端である意味（生成物のため手書きしない、終端を壊さない）
   - `observability/` + `config/` が起動時 1 回だけ初期化される意味（業務 package は受け取った logger / span / 設定値だけを使う）
   - `internal/` の Go 規約（リポジトリ外からの import が**コンパイラ強制で**禁止、両 Worker 間も独立 module で相互 import 不可）

D. **`## やってはいけないこと` セクション**が `§E` の NG パターン一覧から **4 件以上**を箇条書きで含む（`§E-1` 配置・import 系を中心に、`§E-2` の実装 NG も適宜）

**完了基準**：

- 両 Worker の `apps/workers/<worker>/README.md` を開けば「何の機能がどう繋がるか」が図 + 補足で完結する
- 「やってはいけないこと」が `§E` から 4 件以上列挙されている
- 図中の矢印が `§C` の import 方向表と一致している

---

## 4. 実装契約を `.claude/rules/worker.md` に固定

**目的**：Claude が新規実装時に参照する「実装契約」として、両 Worker のディレクトリ配置 + import 方向 + 命名規則 + package 単位の責務を、表 + コード片で曖昧さなく固定する。人間向け README が「概念で理解する」のに対し、rules ファイルは「パターンマッチで判定する」用途。

### 4-1. `.claude/rules/worker.md` の最終状態

`§自律実行ポリシー §7` の通り、初期状態（既存セクションの有無 / 内容のズレ）は不問。**最終状態が下記の条件をすべて満たしていればよい**。

A. **`## ディレクトリ構成（両 Worker 共有 9 package パターン）` セクションが存在する**。内容は次を含む：
- `§A` のテンプレートツリー（`<worker>` 表記、コメント付き）+ Worker 固有差分の表
- `§B` の設計方針（cmd 慣習 / internal 強制 / `db`/`job` 分離 / `llm`/`judge` 分離 / observability lump / orchestrator package / LLM Worker 集約 / プロンプト同居 / Dockerfile 分離）
- `§C` への内部リンク（または `§C` の表を直接ここに転記）

B. **`### package 間の import 方向` セクションが存在する**。内容は次を含む：
- `§C` の import 可 / 禁止表（全 9 package 行、両 Worker 共通）
- `§C` の補足ルール（依存一方向 / module 跨ぎ禁止 / `internal/jobtypes/` 終端 / `observability` 別系統 / `<worker>` orchestrator 集約点 / `internal/llm/<provider>/` サブ構造）
- OK / NG コード片を **4 例以上** `.go` コードブロックで含む（`<worker>` を grading or generation の具体例に展開）：
  - ✅ `cmd/grading/main.go` が全 `internal/*` を import して組み立てる
  - ❌ `internal/llm/` が `internal/grading/` を import（逆流）
  - ❌ `internal/jobtypes/` を手書きで拡張
  - ❌ LLM プロバイダ実装を `internal/llm/` 外で直接 import
  - ❌ `apps/workers/generation/` から `apps/workers/grading/internal/llm/` を import（module 跨ぎ禁止）

C. **`## ジョブキュー取得` セクション**が以下を含む：
- `SELECT FOR UPDATE SKIP LOCKED` の使い方（[ADR 0004](../../../adr/0004-postgres-as-job-queue.md)）
- `LISTEN/NOTIFY` で push 通知を受ける構造
- ジョブの retry / DLQ 戦略（R2 で詳細化、本フェーズでは雛形のみ）
- 配置：`internal/job/` package 配下、両 Worker で同名

D. **`## LLM 呼び出し` セクション**が以下を含む：
- `internal/llm.Provider` interface 定義（`Generate(ctx, prompt, opts) (Response, error)` 等）、両 Worker で同 interface
- Claude / Gemini 等の実装は `internal/llm/<provider>/` 配下に分離
- プロンプトは Worker ごとに `prompts/<subdir>/*.yaml`（grading: `prompts/judge/`、generation: `prompts/generation/` + `prompts/judge/`）から読み込む（[.claude/rules/prompts.md](../../../../.claude/rules/prompts.md)）

E. **`## サンドボックス操作` セクション**が以下を含む：
- 公式 `github.com/docker/docker/client` を使う
- 使い捨てコンテナ（ジョブごとに生成・破棄）の原則（[ADR 0009](../../../adr/0009-disposable-sandbox-container.md)）
- tmpfs mount / read-only mount / network 切断 / ulimit 等の隔離設計
- **両 Worker が同じ `ai-coding-drill-sandbox:latest` image を起動**（image 所有は grading のみ）

F. **`## observability` セクション**が以下を含む：
- W3C Trace Context payload の復元（jobs テーブルの `trace_context` カラム、[ADR 0010](../../../adr/0010-w3c-trace-context-in-job-payload.md)）
- 構造化ログ（slog）+ Prometheus exporter + OTel SDK の組み立て
- 配置：`internal/observability/`（lump、両 Worker で同一構造）

G. **`## コーディング規約` セクション**が以下を含む：
- gofmt（gofumpt） + golangci-lint 必須（[ADR 0019](../../../adr/0019-go-code-quality.md)）
- `Any`（`interface{}`）の使用を最小化、型を明示
- エラーは戻り値、`panic` は本当に回復不能な場合のみ
- テスト：標準 `testing` + `stretchr/testify`（[ADR 0038](../../../adr/0038-test-frameworks.md)）

H. **`## 新規機能の追加パターン` セクション**が以下を含む：
- ジョブ種別を増やす時の手順（`apps/api/app/schemas/jobs/<job_type>.py` 追加 → `mise run api:job-schemas-export` → `mise run worker:<worker>:types-gen` → 該当 Worker の `internal/<worker>/` 内 dispatch + 必要 package 拡張）

I. **`## ツーリング` セクション**が `mise run worker:<worker>:*` タスク表を両 Worker 分含む（dev / test / lint / audit / deps-check / types-gen、grading のみ sandbox-build）

> **書き換え方の指針**：上記の「**最終的にこうなっていればよい**」を満たすために、既存 `worker.md`（rules）から関連箇所を探して整合させる。一致しているものは触らない、無いものは足す、矛盾しているものは書き換える（§自律実行ポリシー §7）。

### 4-2. `.claude/CLAUDE.md` の最終状態

- 「ルールファイルの管理」リストに `.claude/rules/worker.md` が列挙されている：「Worker（採点 / 問題生成、Go）に関すること → `.claude/rules/worker.md`」の 1 行が存在する
- generation Worker が「Go module 未着手」と書かれていたら更新する（本フェーズで Go module が配置されたため）
- 該当行が無ければ追加し、別パスを指している場合は修正する

**完了基準**：

- `.claude/rules/worker.md` の「§ディレクトリ構成（両 Worker 共有 9 package パターン）」セクションに `§A` テンプレートツリー + Worker 固有差分表 + `§B` 設計方針 + `§C` import 方向表 + OK/NG 例（4 例以上）が揃っている
- import 方向表に全 9 package が行として並ぶ
- `## ジョブキュー取得` / `## LLM 呼び出し` / `## サンドボックス操作` / `## observability` / `## コーディング規約` / `## 新規機能の追加パターン` / `## ツーリング` の各セクションが揃っている
- `.claude/CLAUDE.md` の「ルールファイルの管理」リストに `worker.md` が列挙されており、generation の「未着手」記述が更新されている

---

## 5. 進捗トラッカーへの反映の最終状態

**目的**：本フェーズが終わったことを、プロジェクトの進捗管理仕組み（ロードマップ / プロジェクト管理ツール / README 等）に反映する。

**最終状態**：

- [01-roadmap.md](../01-roadmap.md) の R0-9 行が、状態列 `✅ 完了` + 詳細手順列が本ファイルへのリンク `[r0-setup/worker-layers.md](./r0-setup/worker-layers.md)` になっている（本フェーズ完了前の `🔴 未着手` 表記 + `（要作成）` 注記は完了時に書き換える）
- R0-8 行も本フェーズと同時に**両 Worker 前提**として記述が揃っている（generation 側の Go module / mise タスク / CI / dependabot が本フェーズと併せて完了）
- R7 行は「generation Worker の機能実装」へ scope を縮小（旧記述「切り出し + プロンプト群移管」は R0-8 + R0-9 に取り込まれたため、機能実装のみ残る）
- 本ファイル冒頭のステータスマークが完了時に `# Worker（Go）ディレクトリ構成（✅ 完了）` に書き換わっている

**完了基準**：

- 進捗トラッカー上で本フェーズが完了になっている
- 本ファイルへのリンクが進捗トラッカーから辿れる
- 本ファイル冒頭のステータスマークが完了状態（`✅`）になっている

---

## 関連

- 親階層：[README.md: 役割別 setup の後段](./README.md#役割別-setup-の後段レイヤ分割フェーズ)
- 前フェーズ：[worker.md](./worker.md)（両 Worker workspace + main.go skeleton + sandbox Dockerfile 雛形の配置元）
- 並行フェーズ：[backend-layers.md](./backend-layers.md) / [frontend-layers.md](./frontend-layers.md)（同じ「レイヤ分割」パターン）
- ロードマップ：[01-roadmap.md: Now：R0 基盤](../01-roadmap.md#nowr0-基盤直列初期慣行--役割別環境構築--レイヤ分割--mcp-整備)
- 実装契約 SSoT：[.claude/rules/worker.md](../../../../.claude/rules/worker.md)
- 関連 ADR：[ADR 0016](../../../adr/0016-go-for-grading-worker.md)（Go 採用）/ [ADR 0019](../../../adr/0019-go-code-quality.md)（Go コード品質）/ [ADR 0040](../../../adr/0040-worker-grouping-and-llm-in-worker.md)（LLM Worker 集約、両 Worker 並立、プロンプト同居）/ [ADR 0009](../../../adr/0009-disposable-sandbox-container.md)（使い捨てサンドボックス）/ [ADR 0007](../../../adr/0007-llm-provider-abstraction.md)（LLM プロバイダ抽象化）/ [ADR 0004](../../../adr/0004-postgres-as-job-queue.md)（Postgres ジョブキュー）/ [ADR 0010](../../../adr/0010-w3c-trace-context-in-job-payload.md)（W3C Trace Context payload）
