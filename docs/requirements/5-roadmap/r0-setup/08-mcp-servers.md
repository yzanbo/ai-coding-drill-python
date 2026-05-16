# 08. MCP サーバー導入（✅ 完了）

> **守備範囲**：Claude Code（VSCode 拡張）で使う MCP サーバーをプロジェクト共有の `.mcp.json` に登録する。
> **前提フェーズ**：[01-foundation.md](./01-foundation.md) 完了済（`mise install` で Node.js が動作）。
> **実行タイミング**：R0 の他項目と並行可。レイヤ規約への依存無し（R1 のブロッカーではない）。
>
> **バージョン方針**：[.claude/CLAUDE.md: バージョン方針](../../../../.claude/CLAUDE.md#バージョン方針) に従い、各パッケージは導入時に Web で最新版を調査してから採用する。本ファイルのパッケージ名はあくまで導入時点の情報。

---

## 導入するもの（4 つ）

| # | MCP 名 | 用途 | パッケージ（npm） | API キー |
|---|---|---|---|---|
| 1 | **Context7** | あらゆる OSS の**最新ドキュメント**を Claude にロード（Next.js / React / FastAPI / SQLAlchemy 等を執筆時点の最新で参照させる）| `@upstash/context7-mcp` | 不要 |
| 2 | **shadcn** | **shadcn/ui コンポーネントを Claude 経由で追加**（[frontend-component.md §1](../../../../.claude/rules/frontend-component.md) のフォルダ規約も込みで）| `shadcn`（CLI の `mcp` サブコマンド）| 不要 |
| 3 | **Next.js** | Next.js プロジェクトの**プロジェクト解析と最新仕様参照**（App Router / RSC / Server Actions）。Vercel 公式、Next.js 16+ のランニング dev サーバーを自動検出して `nextjs_index` / `nextjs_call` でルーティング解析、`nextjs_docs` で docs 参照、`upgrade_nextjs_16` でアップグレード支援 | `next-devtools-mcp` | 不要 |
| 4 | **Playwright** | E2E テストの**実機ブラウザ実行・スクリーンショット・失敗時イテレーション**を Claude が直接行う。Microsoft 公式メンテ。**Claude Code 同梱ではないため明示追加が必要** | `@playwright/mcp` | 不要 |

---

## 将来の導入候補（R0-8 では入れない）

R1 以降で必要になった時点で追加。判断基準だけ残しておく。

| MCP | 用途 | 追加するタイミング |
|---|---|---|
| **Postgres MCP** | ローカル DB のスキーマ確認・クエリ実行を Claude に許可 | R1-1 ジョブペイロード設計時に `docker compose` の Postgres へ繋ぎたくなったら |
| **GitHub MCP** | issue / PR 作成・コメント取得を Claude から | issue / PR 管理を Claude に任せたくなったら（`GITHUB_TOKEN` を `.env` に置く運用に切り替え） |
| **Filesystem MCP** | ファイルシステム操作 | Claude Code 内蔵 `Read` / `Write` / `Edit` で代替可、横断 grep の高速化等で必要時 |

---

## `.mcp.json` の最終状態

リポジトリ root の `.mcp.json` に下記を配置。**git にコミットする**（API キー不要のため安全、チーム全員が同じ MCP セットを使える）。

```json
{
  "mcpServers": {
    "context7": {
      "command": "npx",
      "args": ["-y", "@upstash/context7-mcp@latest"]
    },
    "shadcn": {
      "command": "npx",
      "args": ["-y", "shadcn@latest", "mcp"],
      "cwd": "apps/web"
    },
    "next-devtools": {
      "command": "npx",
      "args": ["-y", "next-devtools-mcp@latest"]
    },
    "playwright": {
      "command": "npx",
      "args": ["-y", "@playwright/mcp@latest"]
    }
  }
}
```

**ポイント**：

- `shadcn` は `cwd: "apps/web"`（`components.json` を apps/web 配下で読むため）
- `next-devtools` / `playwright` は `cwd` 無し（`next-devtools-mcp` は走行中の Next.js dev サーバーを自動検出する。Playwright はリポジトリ全体から相対パスで E2E シナリオを扱う）
- `next-devtools` が `connected` にならない場合は当該エントリを削除して Context7 で代替する

---

## VSCode に反映させる流れ

1. **新規ブランチを切る**：[CLAUDE.md: ブランチ運用](../../../../.claude/CLAUDE.md#ブランチ運用) に従う（`main` で直接作業しない）。本フェーズは MCP 設定変更のみの単発作業として切り出す場合は `chore/config/<名前>`、ロードマップ更新等を同梱する場合は `docs/<名前>` 等、内容に応じて scope を選ぶ
2. **各 MCP の最新版を Web で調査**：[npmjs.com](https://www.npmjs.com/) と各公式リポジトリでパッケージ名・最新バージョンを確認。Next.js 専用 MCP の公式実装は採用時に確定
3. **`.mcp.json` をリポジトリ root に作成**：上記「最終状態」をそのまま貼り付ける（Next.js MCP は Vercel 公式 `next-devtools-mcp` を採用済）
4. **`.gitignore` を確認**：`.mcp.json` が含まれていないこと（API キー不要のため git 管理する）
5. **JSON 妥当性確認**：`jq . .mcp.json` がエラーなく整形出力される
6. **VSCode の Claude Code 拡張を再読み込み**：
   - Cmd+Shift+P → 「Developer: Reload Window」または「Claude Code: Reload」
   - もしくは VSCode ウィンドウを閉じて開き直す
7. **`/mcp` で接続確認**：Claude Code のチャット入力で `/mcp` を打ち、4 つすべてが `connected` 状態で表示される
   - 初回は `npx` がパッケージをダウンロードするので 1〜2 分かかる
   - Playwright は初回だけ Chromium / WebKit / Firefox バイナリ（数百 MB）も取得 → 完了まで `disconnected` のままになる、待つ
8. **各 MCP の実機テスト**：
   - Context7：「Next.js 16 の App Router を Context7 で最新ドキュメントを引いて教えて」
   - shadcn：「shadcn/ui の button を apps/web に追加して、frontend-component.md §1 のフォルダ規約で配置して」
   - Next.js：「`mise run web:dev` 起動中の前提で、next-devtools MCP の `nextjs_index` で apps/web のルーティング構造を解析して」
   - Playwright：「`mise run web:dev` 起動中の前提で、http://localhost:3000 にアクセスしてスクリーンショットを取って」
9. **`CONTRIBUTING.md` に MCP セクションを追記**：`git clone` 後の開発者が「Claude Code 起動だけで MCP が動く」状態を達成する旨と、初回ダウンロード時間に関する注意を 1 段落で書く（[CONTRIBUTING.md](../../../../CONTRIBUTING.md) の「動作確認」セクション直後に追加。`README.md` は CONTRIBUTING.md にリンクするだけの軽量構成のため、追記は CONTRIBUTING.md 側に集約する。SSoT は本ファイル、CONTRIBUTING.md はリンク誘導のみ）
10. **進捗トラッカーを反映**（コミット前に必ず行う）：
    - [01-roadmap.md](../01-roadmap.md) の R0-8 行の状態列を `🔴 未着手` → `✅ 完了` に書き換える（項目説明も実際に導入した 4 MCP 名（Context7 / shadcn / next-devtools / @playwright/mcp）に具体化する）
    - 本ファイル冒頭のステータスマークを `# 08. MCP サーバー導入（🔴 未着手）` → `# 08. MCP サーバー導入（✅ 完了）` に書き換える
    - 詳細は本ファイル §「進捗トラッカーへの反映の最終状態」を参照
11. **コミット / プッシュ / PR**：ユーザーの明示指示が出てから行う。進捗トラッカー（手順 10）を反映済みの状態でコミットすることで、PR レビュー時に「R0-8 完了状態」が一覧で見える

**トラブルシューティング**：

| 症状 | 対応 |
|---|---|
| `/mcp` で `disconnected` 表示 | 1〜2 分待つ。それでも駄目なら手動で `npx -y <package>@latest` をターミナルで実行してダウンロード完了させ、VSCode を再読み込み |
| shadcn の add で `components.json not found` | `.mcp.json` の `cwd: "apps/web"` 設定漏れ |
| Playwright が `Executable doesn't exist` | `npx playwright install chromium` で先回り、または `npx -y @playwright/mcp@latest --help` を 1 回手動実行 |
| `.mcp.json` が読まれない | `claude --version` で版確認、古ければ Claude Code 拡張を更新 |

---

## 進捗トラッカーへの反映の最終状態

- [01-roadmap.md](../01-roadmap.md) の R0-8 行が、状態列 `✅ 完了` + 詳細手順列が本ファイルへのリンクになっている
- 本ファイル冒頭のステータスマークが完了時に `# 08. MCP サーバー導入（✅ 完了）` に書き換わっている

**完了基準**：

- `.mcp.json` が git 管理下にある
- `/mcp` で 4 つ（Next.js が動かない場合は 3 つ）すべてが `connected`
- 各 MCP の実機テストが通る
- `CONTRIBUTING.md` に MCP セクションが追記されている

---

## 関連

- ロードマップ：[01-roadmap.md: R0-8](../01-roadmap.md#nowr0-基盤直列初期慣行--役割別環境構築--レイヤ分割--mcp-整備)
- フォルダ規約（shadcn 追加時に Claude が従う）：[.claude/rules/frontend-component.md](../../../../.claude/rules/frontend-component.md)
- 公式リソース：[Claude Code MCP ドキュメント](https://docs.claude.com/en/docs/claude-code/mcp) / [github.com/upstash/context7](https://github.com/upstash/context7) / [shadcn/ui](https://ui.shadcn.com/) / [github.com/microsoft/playwright-mcp](https://github.com/microsoft/playwright-mcp)
