# 0019. Go のコード品質ツールに gofmt + golangci-lint を採用

- **Status**: Accepted
- **Date**: 2026-04-25
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
- **型チェックは `go build`（Go 言語仕様）に内蔵**されるため別ツールを採用しない
- 任意追加：[`govulncheck`](https://pkg.go.dev/golang.org/x/vuln/cmd/govulncheck)（脆弱性スキャン）

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

| 候補 | 採用しなかった理由 |
|---|---|
| `gofmt` + `golangci-lint`（採用） | — |
| `gofmt` + `revive` 単体 | golangci-lint がメタリンターで複数ツール統合、より包括的 |
| `gofmt` + 個別ツール手動運用（govet / staticcheck 等を直接呼ぶ）| 管理コスト高、golangci-lint で 1 コマンド化が定石 |
| `gofumpt` を `gofmt` の代わりに直接使う | gofumpt は gofmt の追加ルールセット。golangci-lint 経由で gofumpt を有効化する方式の方がリンタ群と統合管理できる |

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

## References

- [06-dev-workflow.md: コード品質ツール](../requirements/2-foundation/06-dev-workflow.md#コード品質ツール)
- [ADR 0018: TypeScript のコード品質ツール](./0018-biome-for-tooling.md)
- [ADR 0020: Python のコード品質ツール](./0020-python-code-quality.md)
- [ADR 0016: 採点ワーカーを Go で実装](./0016-go-for-grading-worker.md)
- [ADR 0021: R0 ツール導入規律](./0021-r0-tooling-discipline.md)
- [golangci-lint 公式](https://golangci-lint.run/)
- [gofmt 公式](https://pkg.go.dev/cmd/gofmt)
- [govulncheck 公式](https://pkg.go.dev/golang.org/x/vuln/cmd/govulncheck)
