# 0019. Go のコード品質ツールに gofmt + golangci-lint を採用

- **Status**: Accepted
- **Date**: 2026-05-09 <!-- Python pivot（ADR 0033）/ mise 採用（ADR 0039）に追従して CI 統合方針と起動経路を明記 -->
- **Decision-makers**: 神保 陽平

## Context（背景・課題）

採点ワーカーを Go で実装する（→ [ADR 0016](./0016-go-for-grading-worker.md)）にあたり、Go 側のコード品質ツール（フォーマット・lint・型チェック）を決める必要がある。

- Go は本プロジェクトで採点ワーカーに使う言語
- 「3 言語に等価な品質ゲートを設計した」と語れる構成にしたい
- フォーマット論争・コードレビューでの揉め事を避けたい
- メタリンターによる包括的なチェックを望む

関連：

- TS の品質ツール → [ADR 0018](./0018-biome-for-tooling.md)
- Python の品質ツール → [ADR 0020](./0020-python-code-quality.md)

## Decision（決定内容）

- **フォーマットに [`gofmt`](https://pkg.go.dev/cmd/gofmt)**（Go 標準）を採用
- **lint に [`golangci-lint`](https://golangci-lint.run/)** を採用（メタリンター）
  - 有効化するリンタ：`govet` / `staticcheck` / `errcheck` / `ineffassign` / `unused` / `gofumpt` / `gosec` 等
  - **`unused` linter** で未使用関数 / 型 / 定数 / フィールドを検出（Knip の export 検査に対称、別途 `deadcode` ツールは不採用 → §Alternatives）
- **型チェックは `go build`（Go 言語仕様）に内蔵**されるため別ツールを採用しない
- **依存衛生に [`go mod tidy`](https://pkg.go.dev/cmd/go#hdr-Add_missing_and_remove_unused_modules)（Go 標準）** を採用
  - 未使用 / 不足 dependency を `go.mod` から自動削除・追加する標準コマンド
  - CI で `go mod tidy && git diff --exit-code go.mod go.sum` を走らせ、未整理 dep の混入を fail-closed
  - Knip の dep 検査・Python の deptry（[ADR 0035](./0035-uv-for-python-package-management.md)）に対称
- **脆弱性スキャンに [`govulncheck`](https://pkg.go.dev/golang.org/x/vuln/cmd/govulncheck)** を採用（Worker 実装着手時に正式有効化）
  - Go 公式・OSV.dev 連携、**到達解析ベースで実際に使われる脆弱性のみ警告**するため誤検知が少ない
  - Python の pip-audit（[ADR 0035](./0035-uv-for-python-package-management.md)）に対称な脆弱性ゲート
  - 3 言語で「未使用検出 / 脆弱性スキャン」の対称性が完成

### CI / lefthook 統合（[ADR 0026](./0026-github-actions-incremental-scope.md) 拡張版に基づく）

- Worker 実装着手前でも **R0 skeleton として `golangci-lint` ジョブ枠を CI に先置き**する（実 Go ファイルが無い間は no-op、追加された瞬間に有効化）
- ジョブ起動経路は **`mise run worker-lint` 経由**で統一（→ [ADR 0039](./0039-mise-for-task-runner-and-tool-versions.md)）。ローカルと CI で同一コマンド
- `go` 本体のバージョン管理は `mise.toml` の `[tools]` セクションに集約（`goenv` は採用しない）
- lefthook も同様に `*.go` glob トリガーで `mise run worker-lint` を呼ぶ（Worker 実装着手時に組込）

## Why（採用理由）

1. **Go 標準（`gofmt`）に逆らわない**
   - フォーマット論争を回避でき、コードレビューで揉めない
   - Go コミュニティの de facto standard で、外部参画者の学習コストがゼロ
2. **メタリンターによる包括チェック**
   - `govet` / `staticcheck` / `errcheck` / `ineffassign` / `unused` / `gofumpt` / `gosec` を 1 コマンドで実行
   - revive 単体や個別ツール手動運用より管理コスト・網羅性で優れる
   - golangci-lint が複数リンタを順次起動・結果集約するため、CLI / CI ともにシンプル
3. **型チェックは `go build` に内蔵**
   - 別途型チェッカーを選定する必要がなく、TS / Python と同等の品質ゲートを最小構成で実現
   - ビルドが通れば型は通っているという保証がある
4. **エコシステム成熟度**
   - golangci-lint はメンテナンス活発、リンタ追加・更新がコミュニティ主導で継続
   - VS Code / GoLand 等の IDE 統合も成熟

## Alternatives Considered（検討した代替案）

### lint / format

| 候補 | 採用しなかった理由 |
|---|---|
| `gofmt` + `golangci-lint`（採用） | — |
| `gofmt` + `revive` 単体 | golangci-lint がメタリンターで複数ツール統合、より包括的 |
| `gofmt` + 個別ツール手動運用（govet / staticcheck 等を直接呼ぶ）| 管理コスト高、golangci-lint で 1 コマンド化が定石 |
| `gofumpt` を `gofmt` の代わりに直接使う | gofumpt は gofmt の追加ルールセット。golangci-lint 経由で gofumpt を有効化する方式の方がリンタ群と統合管理できる |

### 未使用コード / dead code 検出

| 候補 | 採用しなかった理由 |
|---|---|
| **golangci-lint の `unused` linter（採用）** | golangci-lint の有効化リンタとして既採用。未使用関数 / 型 / 定数 / フィールドを 1 ジョブで検出 |
| `golang.org/x/tools/cmd/deadcode`（Go チーム公式） | main 起点の到達不能解析が売りだが、**本プロジェクトの Worker は main package が 1 つ**のため `unused` で実用上同等のカバレッジ。複数 main 構成（admin CLI / migration runner 等）になったら再評価 |
| `deadmono`（Go monorepo 向け） | 複数 main package 環境向けニッチツール、現状該当しない |
| `codecoroner` | メンテナンス縮小傾向、`unused` で代替可能 |

### 依存衛生

| 候補 | 採用しなかった理由 |
|---|---|
| **`go mod tidy`（Go 標準、採用）** | 標準コマンドで完結、追加ツール不要 |
| サードパーティ dep checker | `go mod tidy` が標準として完結しているため不要 |

### 脆弱性スキャン

| 候補 | 採用しなかった理由 |
|---|---|
| **`govulncheck`（Go 公式、採用）** | Go チーム公式、到達解析で誤検知抑制、OSV.dev 連携 |
| Trivy（コンテナイメージ層も含む） | Worker 実装着手時の `govulncheck` で十分。Trivy は本番直前の追加ゲートとして検討（[ADR 0026](./0026-github-actions-incremental-scope.md)） |
| Snyk Open Source | 商用、本プロジェクト規模に対し過剰 |

## Consequences（結果・トレードオフ）

### 得られるもの

- Go 標準ツール群 + メタリンターで「Go コミュニティ canonical」な品質ゲート
- `golangci-lint run` 1 コマンドで複数リンタの結果が集約される
- 設定ファイル `.golangci.yml` 1 つでリンタ on/off を一元管理
- 型チェックを別ツール選定する必要がなく、TS / Python と等価な品質ゲートを最小構成で実現

### 失うもの・受容するリスク

- golangci-lint のバージョン更新時に有効リンタのデフォルト変更で挙動が変わる可能性あり（CI が失敗するケース）→ `.golangci.yml` で明示的に有効化リンタを固定する
- 個別リンタ（特に `gosec`）が誤検知を出すことがある → 必要に応じてルール除外設定で対応
- gofumpt は gofmt より厳しいため、既存 Go コードを取り込む際にフォーマット差分が出る（自動修正で吸収可能）

### 将来の見直しトリガー

- golangci-lint が大幅な仕様変更（v2 以降の破壊的変更等）を行った場合 → 設定移行のコストを再評価
- 採点ワーカー以外に Go 製のツール・サービスが増え、専用 lint プロファイルが必要になった場合 → 各ディレクトリで `.golangci.yml` を上書き運用するか、単一プロファイルで継続するかを再評価
- **Worker が複数 main package 構成（admin CLI / migration runner 等）に分岐した場合**：`golang.org/x/tools/cmd/deadcode` または `deadmono` の採用を検討（unused だけでは到達不能関数の検出が弱くなるため）

## References

- [06-dev-workflow.md: コード品質ツール](../requirements/2-foundation/06-dev-workflow.md#コード品質ツール)
- [ADR 0016: 採点ワーカーを Go で実装](./0016-go-for-grading-worker.md)
- [ADR 0018: TypeScript のコード品質ツールに Biome](./0018-biome-for-tooling.md)（Superseded by 0033、Frontend 用途として継続採用）
- [ADR 0020: Python のコード品質ツールに ruff + pyright を採用](./0020-python-code-quality.md)
- [ADR 0021: 補完ツールを R0 から導入](./0021-r0-tooling-discipline.md)
- [ADR 0026: GitHub Actions の段階拡張](./0026-github-actions-incremental-scope.md)（Go ジョブを R0 skeleton として先置きする根拠）
- [ADR 0039: タスクランナー兼 tool 版数管理に mise を採用](./0039-mise-for-task-runner-and-tool-versions.md)（Go 版数管理 / 起動経路統一の前提）
- [ADR 0033: バックエンドを Python に pivot](./0033-backend-language-pivot-to-python.md)（3 言語対称な品質ゲートの前提）
- [golangci-lint 公式](https://golangci-lint.run/)
- [gofmt 公式](https://pkg.go.dev/cmd/gofmt)
- [govulncheck 公式](https://pkg.go.dev/golang.org/x/vuln/cmd/govulncheck)
