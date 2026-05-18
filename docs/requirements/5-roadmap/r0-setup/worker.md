# Worker（Go）環境構築（✅ 完了）

## このフェーズで何ができるようになるか

Go ランタイム取得から `apps/workers/grading/` + `apps/workers/generation/` の 2 つの Worker（独立 Go module）を品質ゲート + サンドボックス雛形付きで動かすまでのステップ。**両 Worker を同一フェーズで対称に扱う**（[ADR 0040](../../../adr/0040-worker-grouping-and-llm-in-worker.md)）。本フェーズが終わると以下ができるようになる：

- `mise run worker:grading:dev` / `worker:generation:dev` で**両 Worker** の skeleton（jobs polling loop）が起動する
- gofmt / golangci-lint / govulncheck / `go mod tidy -diff` がローカル + CI 両方で**両 Worker 緑**になる
- testing + testify のテスト基盤が両 Worker に揃う
- 使い捨てサンドボックス用 Dockerfile の skeleton が `apps/workers/grading/sandbox/` に配置され、**generation Worker からも image を共有**する（→ [ADR 0040](../../../adr/0040-worker-grouping-and-llm-in-worker.md)：generation は模範解答の sandbox 検証で同じ image を使う）
- 両 Worker の Go 依存の自動更新 PR が週次で来る

Worker のビジネスロジック（採点・問題生成・LLM 呼び出し）の実装は LLM プロバイダ抽象化フェーズ以降で進める。本フェーズはあくまで「両 Worker が同じ品質ゲートで動く skeleton 状態」までを扱う。

---

> **両 Worker 対称の理由**（[ADR 0040](../../../adr/0040-worker-grouping-and-llm-in-worker.md)）：grading（採点）と generation（問題生成）はユーザーフロー上「問題生成 → 解答 → 採点」と直列につながるが、Worker としては独立 Go module で並立する。環境構築 / 品質ゲート / CI / dependabot を grading だけ先に整えて generation を後追いにすると、generation 着手時に R0-8 相当の作業が再発する。同フェーズで両 Worker をスキャフォールドし、R7（generation の機能実装）以降は「ビジネスロジックだけ書けばいい」状態に倒す。
>
> **実行タイミングは柔軟**：R0 の他項目（[foundation.md](./foundation.md) / [backend.md](./backend.md) / [frontend.md](./frontend.md)）と並行で進めても、これら 3 つが完了してから着手しても、R1 着手直前にまとめて行ってもよい。**唯一の制約は「LLM プロバイダ抽象化フェーズが Worker コードを必要とするため、それまでに本フェーズが完了している」こと**。R0 を「Backend + Frontend が動く状態」で先行リリース的に区切り、Worker は後追いで合流させる運用も許容する（その場合 R0 自体は本ファイル以外（[foundation.md](./foundation.md) / [backend.md](./backend.md) / [frontend.md](./frontend.md)）の完了で「実質完了」扱いにできる）。
> **前提フェーズ**：[foundation.md](./foundation.md) 完了済（mise.toml + GitHub Actions 雛形 + Dependabot 雛形）。DB（Postgres）は Worker（採点ジョブの結果書き戻し / 問題生成結果の保存）でも使うが本フェーズ自体は DB に依存しない（雛形 main.go は jobs polling loop の skeleton まで）。実際に DB を読み書きするのは LLM プロバイダ抽象化フェーズ以降。
> **次フェーズ**：[worker-layers.md](./worker-layers.md)（**両 Worker のディレクトリ構成決定** = R0-9）→ LLM プロバイダ抽象化レイヤ + 初期モデル選定（[ADR 0007](../../../adr/0007-llm-provider-abstraction.md) / [ADR 0040](../../../adr/0040-worker-grouping-and-llm-in-worker.md)）。R1 全体の進行順は [../01-roadmap.md](../01-roadmap.md) の「Now：R1 MVP」セクションを参照。
>
> **本ファイル共通の最新版調査ポリシー**：
> [.claude/CLAUDE.md: バージョン方針](../../../../.claude/CLAUDE.md#バージョン方針) に従い、各ステップで **(1) 対象ツールの最新安定版を毎回 Web で調査** し、**(2) 採用前に依存関係（peer dep / 必須最小版数 / breaking changes）をリリースノートで確認** してから書き換える。SSoT（`mise.toml` / `apps/workers/<worker>/go.mod` + `go.sum`（両 Worker）/ `apps/workers/grading/sandbox/Dockerfile` / `docker-compose.yml`）に書かれた既存版数には追従しない（陳腐化のため）。RC / beta / nightly は採用しない。本フェーズの対象は **Go / golangci-lint / govulncheck / testcontainers-go / Docker client SDK / Node.js（サンドボックスベースイメージ） / tsx / Vitest** など。両 Worker の `go.mod` の Go 版数は `mise.toml` と揃え、サンドボックス Dockerfile の Node.js 版数は `apps/web/` 側の Node.js 版数と揃える運用とする。
>
> **本フェーズ共通の設計原則**：「環境構築 + 品質ゲート 5 ステップ」パターンと hook 役割分担（pre-commit / pre-push / CI）は [README.md](./README.md) を参照。r0-setup 配下の全フェーズに適用される。
>
> **doc 内の `<worker>` 表記**：grading / generation の 2 値を取るテンプレ変数として使う。具体例として両方を列挙する箇所と、片方の例だけ示す箇所がある（片方の例だけの所は反対側にも対称適用する）。

---

## 1. Go 最新安定版を調査して pin → mise install

**目的**：Go の最新安定版（stable、RC・beta は不採用）を調査し、`mise.toml` と `README.md` の 2 箇所のみを書き換えて pin 化、そのうえで実体化する。本プロジェクトのバージョン方針（[.claude/CLAUDE.md: バージョン方針](../../../../.claude/CLAUDE.md#バージョン方針)）に従い、**mise.toml に書かれた既存版数に追従するのではなく、毎回その時点の最新安定版を調査してから書き換える**。

**作業内容**：
1. **最新安定版を調査**：[go.dev/doc/devel/release](https://go.dev/doc/devel/release) で latest stable の minor 版（例 `1.26.x`）を確認
2. **`mise.toml` を書き換え**：`[tools]` の `go = "<X.Y>"` を最新の minor に更新
3. **`README.md` を書き換え**：「技術スタック概要」表の Go 版数を同じ minor に更新
4. **`mise install go`** を実行：実 binary をダウンロード・展開
5. **`go version` で動作確認**：`go version go<X.Y>.<patch>` が表示されることを確認

**コマンド例**：
```bash
# 1〜3. 最新安定版を調査して mise.toml と README.md を編集
# 4. インストール
mise install go
# 5. 動作確認
go version  # 例：go version go1.26.3 darwin/arm64
```

**前提**：[foundation.md: 3. mise 導入](./foundation.md#3-mise-導入-)（mise CLI が動作）

**関連 ADR**：[ADR 0039](../../../adr/0039-mise-for-task-runner-and-tool-versions.md)

---

## 2. 両 Worker（grading / generation）の Go workspace 初期化

**目的**：`apps/workers/grading/` と `apps/workers/generation/` の **2 つの独立 Go module** を初期化し、main.go skeleton と golangci-lint 設定を揃える。**この時点から各 Worker の `go.mod` + `go.sum` がその Worker の依存版数の SSoT** — README / 他ドキュメントに具体版数を重複記載しない。両 Worker の `go.mod` の Go 版数は `mise.toml` と揃える。

**作業内容**（`<worker>` = `grading` / `generation` の両方に対称適用）：
1. `apps/workers/<worker>/` ディレクトリの存在確認（既存の README + `prompts/<worker専用>/` がある場合はそのまま）
2. `cd apps/workers/<worker> && go mod init github.com/yzanbo/ai-coding-drill-python/apps/workers/<worker>`（module 名は `mise.toml` の規約に従う）
3. `apps/workers/<worker>/cmd/<worker>/main.go` に最小 skeleton（`signal.NotifyContext` で SIGTERM 受信、30 秒 tick の heartbeat ログだけ出すループ）。配置は [worker-layers.md §A](./worker-layers.md) の `cmd/<binary-name>/main.go` 慣習に従う（次フェーズで確定する layer に合わせる）
4. `apps/workers/<worker>/.golangci.yml` 配置（v2 形式、有効化リンタ：`govet` / `staticcheck` / `errcheck` / `ineffassign` / `unused` / `gosec`、formatter は `gofumpt`）。**両 Worker で同一内容**
5. `apps/workers/<worker>/.gitignore` 配置（`go build ./...` のバイナリ出力 `/<worker>` と `coverage.out` を除外）
6. `apps/workers/<worker>/internal/jobtypes/.gitignore` 配置（型同期パイプライン構築フェーズで quicktype が生成する Go struct の置き場。生成物は git 管理せず、ディレクトリ存在だけ保つ）

**完了確認**（両 Worker で同じことが緑になる）：
```bash
cd apps/workers/<worker>
mise exec -- go build ./...                      # cmd/<worker>/main.go がビルド成功
mise exec -- go vet ./...                        # vet が動く
mise exec -- golangci-lint run                   # golangci-lint が動く
```

**前提**：本ファイルの「1. mise install go」

**関連 ADR**：[ADR 0016](../../../adr/0016-go-for-grading-worker.md) / [ADR 0019](../../../adr/0019-go-code-quality.md) / [ADR 0040](../../../adr/0040-worker-grouping-and-llm-in-worker.md)（両 Worker を独立 module で並立）

---

## 3. サンドボックスイメージ Dockerfile スケルトン（grading のみ配置、generation も同 image を共有）

**目的**：使い捨てサンドボックスコンテナの Dockerfile 雛形を `apps/workers/grading/sandbox/` に**1 箇所だけ**配置する。実際のロジック（tsx + Vitest 実行）は [自動採点](../../4-features/grading.md) 実装フェーズで本格実装するが、ここでは「コンテナがビルド + 起動できる」状態を確立する。

**両 Worker が同じ image を使う理由**：grading は受験者解答の test 実行、generation は生成された問題の模範解答が動くかの検証。どちらも「TS コードを使い捨てコンテナで安全に走らせる」用途で同一であり、image を二重管理しない（[ADR 0009](../../../adr/0009-disposable-sandbox-container.md) / [ADR 0040](../../../adr/0040-worker-grouping-and-llm-in-worker.md)）。

**作業内容**：
1. `apps/workers/grading/sandbox/Dockerfile` 配置（Node.js ベース + tsx + Vitest 入りの最小構成。Node.js の版数は `mise.toml` と揃える）
2. `apps/workers/grading/sandbox/.dockerignore` 配置
3. ビルドスクリプト：`mise.toml` の `worker:grading:sandbox-build` タスク（本ファイルの「4. mise.toml に Worker タスク追記」で追加）から `docker build` を呼ぶ
4. **`apps/workers/generation/sandbox/` は作らない**：generation Worker は実装時に同じ `ai-coding-drill-sandbox:latest` image を Docker SDK 経由で起動する（Dockerfile を generation 側で複製しない）

**Dockerfile スケルトン例**：
```dockerfile
FROM node:24-alpine
RUN npm install -g tsx vitest
WORKDIR /sandbox
USER node
ENTRYPOINT ["tsx"]
# 実際の test 実行はジョブごとに volume mount + cmd で指定（採点・生成のどちらも自動採点実装フェーズで本格実装）
```

**完了確認**：
```bash
docker build -t ai-coding-drill-sandbox:dev apps/workers/grading/sandbox
docker run --rm ai-coding-drill-sandbox:dev --version  # tsx が起動
```

**前提**：本ファイルの「2. 両 Worker の Go workspace 初期化」

**関連 ADR**：[ADR 0009](../../../adr/0009-disposable-sandbox-container.md) / [ADR 0040](../../../adr/0040-worker-grouping-and-llm-in-worker.md)

---

## 4. mise.toml に両 Worker のタスク追記

**目的**：両 Worker 配下のツール起動経路を `mise run worker:<worker>:*` に統一する（[ADR 0040](../../../adr/0040-worker-grouping-and-llm-in-worker.md)）。grading / generation で**対称な 6 タスク**を持ち、grading にだけ `sandbox-build`（image 所有者のため）を追加する。

**両 Worker 共通のタスク**（`<worker>` = `grading` / `generation`）：
- `worker:<worker>:dev` — `cd apps/workers/<worker> && go run ./cmd/<worker>`
- `worker:<worker>:test` — `cd apps/workers/<worker> && go test ./...`
- `worker:<worker>:lint` — `cd apps/workers/<worker> && golangci-lint run`
- `worker:<worker>:audit` — `cd apps/workers/<worker> && govulncheck ./...`
- `worker:<worker>:deps-check` — `cd apps/workers/<worker> && go mod tidy -diff`（Go 1.23+ の `-diff` を使う。`git diff --exit-code go.mod go.sum` は go.sum 未存在時に pathspec error で fail するため不採用）
- `worker:<worker>:types-gen` — `quicktype --src-lang schema` で `apps/api/job-schemas/` から `apps/workers/<worker>/internal/jobtypes/` に Go struct 生成（型同期パイプライン構築フェーズで本格使用、本フェーズでは雛形コマンドのみ）

**grading のみのタスク**：
- `worker:grading:sandbox-build` — `docker build -t ai-coding-drill-sandbox:latest apps/workers/grading/sandbox`（image は両 Worker で共有、generation は別タスクで build しない）

**横断タスク**（[foundation.md: 3. mise 導入](./foundation.md#3-mise-導入-) で確立済の `worker:test` / `worker:lint` / `worker:types-gen` の実体化）：
- `worker:test` → `worker:grading:test` + `worker:generation:test`
- `worker:lint` → `worker:grading:lint` + `worker:generation:lint`
- `worker:types-gen` → `worker:grading:types-gen` + `worker:generation:types-gen`

> **`worker:dev` は横断タスクを設けない**：grading / generation のどちらを起動するかは目的が違うため、`worker:grading:dev` / `worker:generation:dev` を直接呼ぶ運用とする（横断 dev を作ると 2 プロセス並行起動になり混乱する）。

**完了確認**：
```bash
mise tasks | grep worker:                       # 13 タスクが並ぶ（grading 7 + generation 6 = 13、横断 3 は別行）
mise run worker:grading:lint                    # golangci-lint が起動
mise run worker:generation:lint                 # generation 側も同じく起動
```

**関連 ADR**：[ADR 0039](../../../adr/0039-mise-for-task-runner-and-tool-versions.md) / [ADR 0040](../../../adr/0040-worker-grouping-and-llm-in-worker.md)

---

## 5. lefthook.yml に両 Worker 用 pre-commit を追加

**目的**：ローカル commit 時に両 Worker の Go の format / lint を自動発火させ、規約逸脱を hook で弾く。**`gofmt` は両 Worker を 1 つの glob でまとめて処理し、`golangci-lint` は Worker ごとに per-module で起動する**（独立 Go module を跨いで lint できないため）。

**追記内容**（`pre-commit` セクション）：

```yaml
pre-commit:
  commands:
    # gofmt は両 Worker 共通：apps/workers/**/*.go を一括整形 → 再ステージ
    worker-gofmt:
      run: mise exec -- gofmt -w {staged_files}
      glob: "apps/workers/**/*.go"
      stage_fixed: true

    # golangci-lint は Worker 単位（独立 Go module のため module 跨ぎ実行不可）
    worker-grading-golangci-lint:
      glob: "apps/workers/grading/**/*.go"
      root: apps/workers/grading
      run: mise exec -- golangci-lint run --new-from-rev=HEAD ./...

    worker-generation-golangci-lint:
      glob: "apps/workers/generation/**/*.go"
      root: apps/workers/generation
      run: mise exec -- golangci-lint run --new-from-rev=HEAD ./...
```

**設計判断**：
- **stage-only な golangci-lint（`--new-from-rev=HEAD`）**：差分行のみチェックして高速化。全体走査は pre-push の `go test` 経由 + CI で担保
- **`mise exec --` 経由**：pre-commit / pre-push と同じ理由（Git フックの非対話シェルに対する shims 解決）
- **per-Worker glob で同 Worker の commit だけ発火**：grading の Go ファイルだけ変更した commit では generation の golangci-lint は skip される（lefthook のデフォルト挙動、無駄な走査を避ける）

**完了確認**（grading 側 / generation 側どちらでも同じ流れ）：
```bash
echo 'package main
func main(){}'  > apps/workers/<worker>/cmd/<worker>/_test.go    # gofmt 違反
git add apps/workers/<worker>/cmd/<worker>/_test.go && git commit -m "test"   # gofmt が自動整形 → 通過
git restore --staged apps/workers/<worker>/cmd/<worker>/_test.go && rm apps/workers/<worker>/cmd/<worker>/_test.go
```

**前提**：本ファイルの「4. mise.toml に両 Worker のタスク追記」

**関連 ADR**：[ADR 0019](../../../adr/0019-go-code-quality.md)

---

## 6. lefthook.yml に両 Worker 用 pre-push を追加

**目的**：push 直前に**動的検証（go test）** を両 Worker で発火させ、pre-commit の静的検査と CI の間にあるギャップを埋める。

**追記内容**（`pre-push` セクション、Worker ごとに 1 hook）：

```yaml
pre-push:
  commands:
    worker-grading-go-test:
      glob: "apps/workers/grading/**/*.go"
      root: apps/workers/grading
      run: mise exec -- go test ./...

    worker-generation-go-test:
      glob: "apps/workers/generation/**/*.go"
      root: apps/workers/generation
      run: mise exec -- go test ./...
```

**設計判断**：
- **go test は両 Worker を per-module で全体実行**：Go の test は通常高速（数秒）。pytest と違い DB 依存テストは「testcontainers でテストごとに spin up」する Go 慣習なので graceful skip 不要
- **glob で同 Worker の変更時だけ発火**：grading だけ触った push では generation の go test は skip される
- **govulncheck は pre-push に含めない**：脆弱性スキャンは依存衛生系と同じく週次で十分なため CI 専用

**完了確認**：失敗テストを `apps/workers/<worker>/cmd/<worker>/fail_test.go` に仕込んで `git push` が exit 1 でブロックされること。

**前提**：本ファイルの「5. lefthook.yml に両 Worker 用 pre-commit を追加」

**関連 ADR**：[ADR 0038](../../../adr/0038-test-frameworks.md)

---

## 7. GitHub Actions に両 Worker のジョブ追加

**目的**：[foundation.md: 4. GitHub Actions ワークフロー雛形](./foundation.md#4-github-actions-ワークフロー雛形-) で整備したワークフローに両 Worker 用ジョブを追加し、hook bypass された逸脱もリモートで弾く。

**追記内容**（[.github/workflows/ci.yml](../../../../.github/workflows/ci.yml)）：
- 新規ジョブ（8 個 = 4 種 × 2 Worker）：
  - `worker-grading-lint` / `worker-grading-test` / `worker-grading-audit` / `worker-grading-deps-check`
  - `worker-generation-lint` / `worker-generation-test` / `worker-generation-audit` / `worker-generation-deps-check`
- 各ジョブで `actions/checkout` + `jdx/mise-action`（SHA ピン）→ `mise run worker:<worker>:<task>` を実行
- `ci-success` の `needs:` に上記 8 ジョブを全て追加

**完了確認**：
- PR を作ると 8 ジョブが並行で走る
- いずれかが失敗すると `ci-success` も赤になり、Branch protection で merge がブロックされる

**前提**：本ファイルの「5. pre-commit」+「6. pre-push」（ローカル品質ゲートが両 Worker で緑）

**関連 ADR**：[ADR 0026](../../../adr/0026-github-actions-incremental-scope.md) / [ADR 0031](../../../adr/0031-ci-success-umbrella-job.md)

---

## 8. dependabot.yml の `gomod` を両 Worker で有効化

**目的**：両 Worker の Go 依存（`go.mod` + `go.sum`）を Dependabot の週次自動更新対象に含める。各 Worker は独立 Go module（[ADR 0040](../../../adr/0040-worker-grouping-and-llm-in-worker.md)）のため、Dependabot エントリも Worker ごとに必要。

**作業内容**（[.github/dependabot.yml](../../../../.github/dependabot.yml)）：
- `gomod` ブロックを 2 つ有効化：`directory: /apps/workers/grading` と `directory: /apps/workers/generation`
- 両エントリで `version-update:semver-major` を `ignore` に追加（メジャー更新は手動運用、[ADR 0028](../../../adr/0028-dependabot-auto-update-policy.md)）
- ラベル：`dependencies` + `go`、commit prefix：`build` / `build`（Dependabot が deps / deps-dev を自動付与）

**完了確認**：
- 翌週月曜 06:00 JST に両 Worker 分の `build(deps)` 自動 PR が生成される
- もしくは GitHub UI から `Insights → Dependency graph → Dependabot` で手動 trigger で確認

**関連 ADR**：[ADR 0028](../../../adr/0028-dependabot-auto-update-policy.md) / [ADR 0040](../../../adr/0040-worker-grouping-and-llm-in-worker.md)

---

## 9. 進捗トラッカーへの反映の最終状態

**目的**：本フェーズが終わったことを、プロジェクトの進捗管理仕組み（ロードマップ / プロジェクト管理ツール / README 等）に反映する。

**最終状態**：

- **プロジェクトの進捗トラッカー**（このプロジェクトでは [docs/requirements/5-roadmap/01-roadmap.md](../01-roadmap.md)。別プロジェクトでは GitHub Project / Notion / README 等、各プロジェクトの慣習に従う）で、本フェーズに該当する項目が**完了状態**として記録されている
- 進捗トラッカー上の該当エントリから、**本ファイル**（または同等の手順詳細）への**リンク**が辿れる
- 本ファイル冒頭のステータスマークが完了状態を示している（完了時に `# 04. Go 環境構築（🔴 未着手）` を `# 04. Go 環境構築（✅ 完了）` に書き換える）

> **このプロジェクトでの具体例**：[01-roadmap.md](../01-roadmap.md) の 本フェーズに該当する行が、完了時に状態列 `✅ 完了` + 詳細手順列が本ファイルへのリンク `[r0-setup/worker.md](./r0-setup/worker.md)` になっている状態。本フェーズ完了前の `🔴 未着手` 表記は完了時に `✅ 完了` へ書き換える運用とする。

**完了基準**：

- 進捗トラッカー上で本フェーズが完了になっている
- 本ファイルへのリンクが進捗トラッカーから辿れる
- 本ファイル冒頭のステータスマークが完了状態（`✅`）になっている

---

## このフェーズ完了時点で揃うもの

- 🟢 両 Worker が `mise run worker:grading:dev` / `worker:generation:dev` で起動（jobs polling loop の skeleton が回る）
- 🟢 サンドボックスイメージ `ai-coding-drill-sandbox:latest` が `apps/workers/grading/sandbox/` からビルド可能（tsx + Vitest 入り、両 Worker が同 image を使用）
- 🟢 gofmt / golangci-lint / govulncheck / `go mod tidy -diff` が両 Worker でローカル + CI 両方とも緑
- 🟢 規約違反コミットが両 Worker で pre-commit hook（per-Worker glob）で弾かれる
- 🟢 失敗 test が両 Worker で pre-push hook で弾かれる
- 🟢 両 Worker の Go 依存の自動更新 PR が週次で来る（Dependabot に 2 entry 登録）
- 🟢 LLM プロバイダ抽象化フェーズ（[ADR 0007](../../../adr/0007-llm-provider-abstraction.md)）と [自動採点](../../4-features/grading.md) / 問題生成（R7）の実コード投入準備が整う

---

## R1 以降への引き継ぎ

本フェーズで揃った両 Worker tooling を前提に：

- **次フェーズ**（[worker-layers.md](./worker-layers.md) = R0-9）：両 Worker のディレクトリ構成（`cmd/<worker>/` + `internal/<9 package>/`）を確定し、各 package の責務 + import 方向 + 命名規則を `.claude/rules/worker.md` に「実装契約」として固定する
- **LLM プロバイダ抽象化フェーズ**（R1-2）：抽象化レイヤを `apps/workers/<worker>/internal/llm/` に**両 Worker で同じ interface**として実装（[ADR 0007](../../../adr/0007-llm-provider-abstraction.md) / [ADR 0040](../../../adr/0040-worker-grouping-and-llm-in-worker.md)）。実装は Worker ごとに独立 module で持つ（共有 module は不採用、Go module 境界をシンプルに保つ）
- **[自動採点](../../4-features/grading.md) 実装フェーズ**（R1-5）：`apps/workers/grading/internal/sandbox/` に Docker クライアント（公式 `github.com/docker/docker/client`）を使った採点ロジックを実装し、本フェーズ §3 で配置したサンドボックス Dockerfile を本格活用
- **問題生成 Worker 機能実装フェーズ**（R7）：`apps/workers/generation/internal/generation/` に生成オーケストレーターを実装。本フェーズで Go module・mise タスク・CI・dependabot が揃っているため、generation 側は機能ロジックだけ書けばよい状態（環境構築の二重作業を回避）
