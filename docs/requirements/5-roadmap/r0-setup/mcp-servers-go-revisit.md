# Go 追加後の MCP サーバー再選定（✅ 完了 / 追加なし）

## このフェーズで何ができるようになるか

R0-8 で Go 開発対象（`apps/workers/grading/` + `apps/workers/generation/`）が増えたことを受けて、Go 開発を支援する MCP サーバーを `.mcp.json` に追加すべきか判断する。

**結論：本フェーズで `.mcp.json` への追加は行わない**（調査の結果、追加する価値のある「大手公式」MCP が存在しないため）。

---

> **前提フェーズ**：[R0-6 初期 MCP 導入](./mcp-servers.md) + [R0-8 両 Worker Go 環境構築](./worker.md) 完了済
> **次フェーズ**：R0-11（Worker 側型同期パイプライン合流、→ [worker-types-gen.md](./worker-types-gen.md)）

---

## 調査結果

「大手公式（Go チーム / GitHub / Google / Microsoft / JetBrains / Docker / Anthropic 等）が提供する Go 向け MCP サーバー」を対象に調査した。

### 採用候補に挙がったもの → 結論

| MCP | 提供元 | Go 文脈での効きどころ | 採否 | 理由 |
|---|---|---|---|---|
| **github-mcp-server** | GitHub 公式 | PR / Issue / Actions / コードサーチ | 採用せず | Go 専用ではなく汎用。本プロジェクトでは `gh` CLI で十分カバーできる |
| **Docker MCP Toolkit / mcp-gateway** | Docker 公式 | grading Worker の Docker SDK 操作 / image inspect | 採用せず | サンドボックス操作は実装時に SDK 経由で書く方が安全（MCP 経由でホスト Docker を触らせない方が R0-9 の隔離原則と整合） |
| **Context7** | Upstash 公式 | `pgx` / `docker/docker` / `testify` 等の Go ライブラリ docs 取得 | **R0-6 で導入済**（重複追加なし） | 既に `.mcp.json` に登録済。Go ライブラリ docs もカバー |

### 不採用となったカテゴリ

- **gopls 連携 MCP**：gopls は Go チーム公式の LSP だが、MCP ラッパーは公式提供が無い（コミュニティ実装はあるが「大手公式」要件を満たさない）
- **golangci-lint MCP / govulncheck MCP**：公式 MCP は存在しない。`mise run worker:<worker>:lint` / `worker:<worker>:audit` で十分
- **Go test runner MCP**：公式 MCP は存在しない。`mise run worker:<worker>:test` で十分

---

## 完了基準

- [x] Go 向け MCP の「大手公式」候補を Web で調査した
- [x] `.mcp.json` に追加すべき候補が無いことを確認した
- [x] 判断と根拠を本ファイルに記録した（将来 Go 公式 MCP が登場した時点で再評価する）

---

## 関連

- 親階層：[README.md: 役割別 setup の後段](./README.md)
- 前フェーズ：[mcp-servers.md](./mcp-servers.md)（初期 4 MCP 導入）/ [worker.md](./worker.md)（両 Worker Go 環境構築）/ [worker-layers.md](./worker-layers.md)（両 Worker レイヤ分割）
- 次フェーズ：[worker-types-gen.md](./worker-types-gen.md)（Worker 側型同期パイプライン合流）
- ロードマップ：[01-roadmap.md: R0-10](../01-roadmap.md)
