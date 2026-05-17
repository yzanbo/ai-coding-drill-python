# Worker（Go）環境構築（🔴 未着手）

> **守備範囲**：Go ランタイム取得から `apps/workers/grading` を品質ゲート + サンドボックス雛形付きで動かすまでの 8 ステップ。本フェーズが終わると、Go の lint / test / ビルドがローカル + CI 両方で緑になり、依存自動更新が走り始める。Worker のビジネスロジック（採点・LLM 呼び出し）の実装は LLM プロバイダ抽象化フェーズ以降で進める。
> **実行タイミングは柔軟**：R0 の他項目（[foundation.md](./foundation.md) / [backend.md](./backend.md) / [frontend.md](./frontend.md)）と並行で進めても、これら 3 つが完了してから着手しても、R1 着手直前にまとめて行ってもよい。**唯一の制約は「LLM プロバイダ抽象化フェーズが Worker コードを必要とするため、それまでに本フェーズが完了している」こと**。R0 を「Backend + Frontend が動く状態」で先行リリース的に区切り、Worker は後追いで合流させる運用も許容する（その場合 R0 自体は本ファイル以外（[foundation.md](./foundation.md) / [backend.md](./backend.md) / [frontend.md](./frontend.md)）の完了で「実質完了」扱いにできる）。
> **前提フェーズ**：[foundation.md](./foundation.md) 完了済（mise.toml + GitHub Actions 雛形 + Dependabot 雛形）。DB（Postgres）は Worker（採点ジョブの結果書き戻し）でも使うが本フェーズ自体は DB に依存しない（雛形 main.go は jobs polling loop の skeleton まで）。実際に DB を読み書きするのは LLM プロバイダ抽象化フェーズ以降。
> **次フェーズ**：LLM プロバイダ抽象化レイヤ + 初期モデル選定（Worker 側に集約、→ [ADR 0007](../../../adr/0007-llm-provider-abstraction.md) / [ADR 0040](../../../adr/0040-worker-grouping-and-llm-in-worker.md)）。R1 全体の進行順は [../01-roadmap.md](../01-roadmap.md) の「Now：R1 MVP」セクションを参照。
>
> **本ファイル共通の最新版調査ポリシー**：
> [.claude/CLAUDE.md: バージョン方針](../../../../.claude/CLAUDE.md#バージョン方針) に従い、各ステップで **(1) 対象ツールの最新安定版を毎回 Web で調査** し、**(2) 採用前に依存関係（peer dep / 必須最小版数 / breaking changes）をリリースノートで確認** してから書き換える。SSoT（`mise.toml` / `apps/workers/grading/go.mod` + `go.sum` / `apps/workers/grading/sandbox/Dockerfile` / `docker-compose.yml`）に書かれた既存版数には追従しない（陳腐化のため）。RC / beta / nightly は採用しない。本フェーズの対象は **Go / golangci-lint / govulncheck / testcontainers-go / Docker client SDK / Node.js（サンドボックスベースイメージ） / tsx / Vitest** など。`go.mod` の Go 版数は `mise.toml` と揃え、サンドボックス Dockerfile の Node.js 版数は `apps/web/` 側の Node.js 版数と揃える運用とする。
>
> **本フェーズ共通の設計原則**：「環境構築 + 品質ゲート 5 ステップ」パターンと hook 役割分担（pre-commit / pre-push / CI）は [README.md](./README.md) を参照。r0-setup 配下の全フェーズに適用される。

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

## 2. apps/workers/grading 環境構築

**目的**：`apps/workers/grading/` に Go workspace を初期化し、main.go skeleton と golangci-lint 設定を揃える。**この時点から `apps/workers/grading/go.mod` + `go.sum` が Worker 依存版数の SSoT** — README / 他ドキュメントに具体版数を重複記載しない。`go.mod` の Go 版数は `mise.toml` と揃える。

**作業内容**：
1. `apps/workers/grading/` ディレクトリ作成（既存の README + prompts/ がある場合はそのまま）
2. `cd apps/workers/grading && go mod init github.com/yzanbo/ai-coding-drill-python/apps/workers/grading`（module 名は `mise.toml` の規約に従う）
3. `apps/workers/grading/main.go` に最小 skeleton（`package main; func main() { /* TODO: jobs polling loop */ }`）
4. `apps/workers/grading/.golangci.yml` 配置（有効化リンタ：`govet` / `staticcheck` / `errcheck` / `ineffassign` / `unused` / `gofumpt` / `gosec`）
5. `apps/workers/grading/internal/jobtypes/` ディレクトリ雛形（型同期パイプライン構築フェーズで生成された Go struct の置き場、まだ空でよい）

**完了確認**：
```bash
cd apps/workers/grading
go build ./...                                   # main.go がビルド成功
go vet ./...                                     # vet が動く
mise exec -- golangci-lint run                   # golangci-lint が動く
```

**前提**：本ファイルの「1. mise install go」

**関連 ADR**：[ADR 0016](../../../adr/0016-go-for-grading-worker.md) / [ADR 0019](../../../adr/0019-go-code-quality.md) / [ADR 0040](../../../adr/0040-worker-grouping-and-llm-in-worker.md)

---

## 3. サンドボックスイメージ Dockerfile スケルトン

**目的**：採点コンテナ（使い捨て）の Dockerfile 雛形を配置する。実際の採点ロジック（tsx + Vitest 実行）は [F-04 自動採点](../../4-features/F-04-auto-grading.md) 実装フェーズで本格実装するが、ここでは「コンテナがビルド + 起動できる」状態を確立する。

**作業内容**：
1. `apps/workers/grading/sandbox/Dockerfile` 配置（Node.js ベース + tsx + Vitest 入りの最小構成。Node.js の版数は `mise.toml` と揃える）
2. `apps/workers/grading/sandbox/.dockerignore` 配置
3. ビルドスクリプト：`mise.toml` の `worker:grading:sandbox-build` タスク（本ファイルの「4. mise.toml に Worker タスク追記」で追加）から `docker build` を呼ぶ

**Dockerfile スケルトン例**：
```dockerfile
FROM node:22-alpine
RUN npm install -g tsx vitest
WORKDIR /sandbox
USER node
ENTRYPOINT ["tsx"]
# 実際の test 実行は採点ジョブごとに volume mount + cmd で指定（F-04 自動採点実装フェーズで本格実装）
```

**完了確認**：
```bash
docker build -t ai-coding-drill-sandbox:dev apps/workers/grading/sandbox
docker run --rm ai-coding-drill-sandbox:dev --version  # tsx が起動
```

**前提**：本ファイルの「2. apps/workers/grading 環境構築」

**関連 ADR**：[ADR 0009](../../../adr/0009-disposable-sandbox-container.md)

---

## 4. mise.toml に Worker タスク追記

**目的**：apps/workers/grading 配下のツール起動経路を `mise run worker:grading:*` に統一する（→ [ADR 0040](../../../adr/0040-worker-grouping-and-llm-in-worker.md)）。

**追記するタスク（最低限）**：
- `worker:grading:dev` — `cd apps/workers/grading && go run .`
- `worker:grading:test` — `cd apps/workers/grading && go test ./...`
- `worker:grading:lint` — `cd apps/workers/grading && golangci-lint run`
- `worker:grading:audit` — `cd apps/workers/grading && govulncheck ./...`
- `worker:grading:deps-check` — `cd apps/workers/grading && go mod tidy && git diff --exit-code go.mod go.sum`
- `worker:grading:types-gen` — quicktype `--src-lang schema` で `apps/api/job-schemas/` から `apps/workers/grading/internal/jobtypes/` に Go struct 生成（型同期パイプライン構築フェーズで本格使用、本フェーズでは雛形コマンドのみ）
- `worker:grading:sandbox-build` — `docker build -t ai-coding-drill-sandbox:latest apps/workers/grading/sandbox`

**横断タスク**（[foundation.md: 3. mise 導入](./foundation.md#3-mise-導入-) で確立済の `worker:test` / `worker:lint` / `worker:types-gen` の実体化）：
- `worker:test` → `mise run worker:grading:test`（将来 generation worker 追加時に拡張）
- `worker:lint` → `mise run worker:grading:lint`
- `worker:types-gen` → `mise run worker:grading:types-gen`

**完了確認**：
```bash
mise tasks | grep worker:
mise run worker:grading:lint   # golangci-lint が起動
```

**関連 ADR**：[ADR 0039](../../../adr/0039-mise-for-task-runner-and-tool-versions.md) / [ADR 0040](../../../adr/0040-worker-grouping-and-llm-in-worker.md)

---

## 5. lefthook.yml に Worker 用 pre-commit 追加

**目的**：ローカル commit 時に Go の format / lint を自動発火させ、規約逸脱を hook で弾く。

**追記内容**（`pre-commit` セクション）：

```yaml
pre-commit:
  commands:
    gofmt:
      run: mise exec -- gofmt -w {staged_files}
      glob: "apps/workers/**/*.go"
      stage_fixed: true
    golangci-lint:
      run: mise exec -- golangci-lint run --new-from-rev=HEAD apps/workers/grading/...
      glob: "apps/workers/**/*.go"
```

**設計判断**：
- **stage-only な golangci-lint（`--new-from-rev=HEAD`）**：差分行のみチェックして高速化。全体走査は pre-push の `go test` 経由 + CI で担保
- **`mise exec --` 経由**：pre-commit / pre-push と同じ理由（Git フックの非対話シェルに対する shims 解決）

**完了確認**：
```bash
echo 'package main
func main(){}'  > apps/workers/grading/_test.go    # gofmt 違反（インデント無し）
git add apps/workers/grading/_test.go && git commit -m "test"   # gofmt が自動整形 → 通過
git restore --staged apps/workers/grading/_test.go && rm apps/workers/grading/_test.go
```

**前提**：本ファイルの「4. mise.toml に Worker タスク追記」

**関連 ADR**：[ADR 0019](../../../adr/0019-go-code-quality.md)

---

## 6. lefthook.yml に Worker 用 pre-push 追加

**目的**：push 直前に **動的検証（go test）** を発火させ、pre-commit の静的検査と CI の間にあるギャップを埋める。

**追記内容**（`pre-push` セクション）：

```yaml
pre-push:
  commands:
    go-test:
      run: mise exec -- go test ./apps/workers/grading/...
```

**設計判断**：
- **go test は全体実行**：Go の test は通常高速（数秒）。pytest と違い DB 依存テストは「testcontainers でテストごとに spin up」する Go 慣習なので graceful skip 不要。`testcontainers-go` で Postgres を test 時に立てる
- **govulncheck は pre-push に含めない**：脆弱性スキャンは依存衛生系（dependabot 系）と同じく週次で十分なため CI 専用

**完了確認**：
```bash
# 失敗テストを仕込んで push がブロックされることを確認
cat > apps/workers/grading/fail_test.go <<'EOF'
package main
import "testing"
func TestFail(t *testing.T) { t.Fatal("intentional") }
EOF
git add apps/workers/grading/fail_test.go && git push   # pre-push が exit 1 で止まる
git restore --staged apps/workers/grading/fail_test.go && rm apps/workers/grading/fail_test.go
```

**前提**：本ファイルの「5. lefthook.yml に Worker 用 pre-commit 追加」

**関連 ADR**：[ADR 0038](../../../adr/0038-test-frameworks.md)

---

## 7. GitHub Actions に Worker ジョブ追加

**目的**：[foundation.md: 4. GitHub Actions ワークフロー雛形](./foundation.md#4-github-actions-ワークフロー雛形-) で整備したワークフローに Go 用ジョブを追加し、hook bypass された逸脱もリモートで弾く。

**追記内容**（[.github/workflows/ci.yml](../../../../.github/workflows/ci.yml)）：
- 新規ジョブ：`worker-grading-lint`、`worker-grading-test`、`worker-grading-audit`、`worker-grading-deps-check`
  - 各ジョブで `mise install` → `mise run worker:grading:<task>` を実行
  - `actions/checkout` + `jdx/mise-action` を SHA ピン止めで使用
- `ci-success` の `needs:` に上記 4 ジョブを追加

**完了確認**：
- PR を作ると `worker-grading-lint` 〜 `worker-grading-deps-check` が走る
- いずれかが失敗すると `ci-success` も赤になり、Branch protection で merge がブロックされる

**前提**：本ファイルの「5. lefthook.yml に Worker 用 pre-commit 追加」+「6. lefthook.yml に Worker 用 pre-push 追加」（ローカル品質ゲートが緑）

**関連 ADR**：[ADR 0026](../../../adr/0026-github-actions-incremental-scope.md) / [ADR 0031](../../../adr/0031-ci-success-umbrella-job.md)

---

## 8. dependabot.yml の `gomod` コメントアウト解除

**目的**：apps/workers/grading の Go 依存（`go.mod` + `go.sum`）を Dependabot の週次自動更新対象に含める。

**作業内容**（[.github/dependabot.yml](../../../../.github/dependabot.yml)）：
- `gomod` ブロックのコメントアウトを解除
- `directory: /apps/workers/grading` を指定
- `version-update:semver-major` を `ignore` に追加（メジャー更新は手動運用、→ [ADR 0028](../../../adr/0028-dependabot-auto-update-policy.md)）

**完了確認**：
- 翌週月曜 06:00 JST に `build(deps)` の自動 PR が生成される
- もしくは GitHub UI から `Insights → Dependency graph → Dependabot` で手動 trigger で確認

**関連 ADR**：[ADR 0028](../../../adr/0028-dependabot-auto-update-policy.md)

---

## 9. 進捗トラッカーへの反映の最終状態

**目的**：本フェーズが終わったことを、プロジェクトの進捗管理仕組み（ロードマップ / プロジェクト管理ツール / README 等）に反映する。

**最終状態**：

- **プロジェクトの進捗トラッカー**（このプロジェクトでは [docs/requirements/5-roadmap/01-roadmap.md](../01-roadmap.md)。別プロジェクトでは GitHub Project / Notion / README 等、各プロジェクトの慣習に従う）で、本フェーズに該当する項目が**完了状態**として記録されている
- 進捗トラッカー上の該当エントリから、**本ファイル**（または同等の手順詳細）への**リンク**が辿れる
- 本ファイル冒頭のステータスマークが完了状態を示している（完了時に `# 04. Go 環境構築（🔴 未着手）` を `# 04. Go 環境構築（✅ 完了）` に書き換える）

> **このプロジェクトでの具体例**：[01-roadmap.md](../01-roadmap.md) の R0-4 行が、完了時に状態列 `✅ 完了` + 詳細手順列が本ファイルへのリンク `[r0-setup/worker.md](./r0-setup/worker.md)` になっている状態。本フェーズ完了前の `🔴 未着手` 表記は完了時に `✅ 完了` へ書き換える運用とする。

**完了基準**：

- 進捗トラッカー上で本フェーズが完了になっている
- 本ファイルへのリンクが進捗トラッカーから辿れる
- 本ファイル冒頭のステータスマークが完了状態（`✅`）になっている

---

## このフェーズ完了時点で揃うもの

- 🟢 apps/workers/grading が `mise run worker:grading:dev` で起動（jobs polling loop の skeleton が回る）
- 🟢 サンドボックスイメージ `ai-coding-drill-sandbox:latest` がビルド可能（tsx + Vitest 入り）
- 🟢 gofmt / golangci-lint / govulncheck がローカル + CI 両方で動く
- 🟢 規約違反コミットが pre-commit hook で弾かれる
- 🟢 失敗 test が pre-push hook で弾かれる
- 🟢 Go 依存の自動更新 PR が週次で来る
- 🟢 LLM プロバイダ抽象化フェーズ以降（LLM 抽象化、[F-04 自動採点](../../4-features/F-04-auto-grading.md)）の実コード投入準備が整う

---

## R1 以降への引き継ぎ

本フェーズで揃った Worker tooling を前提に：

- **LLM プロバイダ抽象化フェーズ**：抽象化レイヤを `apps/workers/grading/internal/llm/` に実装（→ [ADR 0007](../../../adr/0007-llm-provider-abstraction.md) / [ADR 0040](../../../adr/0040-worker-grouping-and-llm-in-worker.md)）
- **[F-04 自動採点](../../4-features/F-04-auto-grading.md) 実装フェーズ**：`apps/workers/grading/internal/sandbox/` に Docker クライアント（公式 `github.com/docker/docker/client`）を使った採点ロジックを実装し、本フェーズ「3. サンドボックスイメージ Dockerfile スケルトン」で配置したサンドボックス Dockerfile を本格活用

R1 完了時点で `.claude/rules/worker.md` に「Worker 実装契約」（ディレクトリ構成 / pre-commit / pre-push / CI ジョブの対応関係）として転記する。
