---
name: update-documents
description: アプリケーションのユーザーマニュアル（HTML・PDF）を生成・更新する
argument-hint: "[user|admin] (省略時は両方生成)"
---

# ユーザーマニュアルの生成・更新

引数 `$ARGUMENTS` を対象ドキュメントの種別として解釈する。

## 引数の解釈

| 引数 | 対象 |
|---|---|
| （なし / 空） | ユーザー向けマニュアル + 管理者向けマニュアル（両方） |
| `user` | ユーザー向けマニュアルのみ |
| `admin` | 管理者向けマニュアルのみ（R4 以降） |

## 出力先

- ユーザー向けマニュアル
  - HTML：`docs/manuals/user/html/index.html`
  - PDF：`docs/manuals/user/pdf/ai-coding-drill-user-manual.pdf`
  - スクリーンショット：`docs/manuals/user/html/images/`
- 管理者向けマニュアル（R4 以降）
  - HTML：`docs/manuals/admin/html/index.html`
  - PDF：`docs/manuals/admin/pdf/ai-coding-drill-admin-manual.pdf`
  - スクリーンショット：`docs/manuals/admin/html/images/`

## 文体・トーンのルール

- **敬体（です・ます調）** で統一する
- user 向け：プログラミング学習者を想定。専門用語は初出時にカッコ書きで補足する
- admin 向け：運用担当者を想定。技術用語をそのまま使ってよい
- 手順の説明は「〜をクリックします」「〜を入力します」のように動作主体を省略した形で統一する

## デザイン・カラースキームのルール

- user 向け：**緑系**グラデーション（`#059669 → #10b981 → #34d399`）— 親しみやすい印象
- admin 向け：**青系**グラデーション（`#1e40af → #2563eb → #0ea5e9`）— 業務用の落ち着いた印象
- CSS 変数 `--primary` 等のカラーパレットは user / admin で別管理

## 差分更新のルール

- 既存の HTML マニュアルがある場合は **全体を上書き**する（セクション単位のパッチは行わない）
- 表紙のバージョン番号は `YYYY.MM` 形式（例：`2026.05`）とし、生成時の年月で自動更新する
- 表紙の最終更新日は生成実行日を記載する

## スクリーンショットの撮影ルール

- **ビューポートサイズ**：1280x800 で固定する
- **撮影範囲**：原則ビューポート内のみ（フルページスクロールは不要）
- **ファイル命名**：`screenshot-<画面名>.png`（例：`screenshot-login.png`、`screenshot-problem-detail.png`）
- **保存先**：各マニュアルの `html/images/` ディレクトリ
- 既存のスクリーンショットがある場合は上書きする

## 手順

### 1. 現状の把握

- フロントエンドの画面構成を確認する（`apps/web/src/app/(routing)/` 配下のルーティング）
- 機能要件（`docs/requirements/4-features/`）とベース要件 [01-overview.md](../../../docs/requirements/1-vision/01-overview.md) を確認する
- 既存のマニュアルがあれば読み込み、内容の参考とする

### 2. ユーザー向けマニュアル（`user` または引数なしの場合）

対象：プログラミング学習者（GitHub アカウント所有層）

以下の構成でドキュメントを作成する：

1. **表紙** — タイトル、バージョン、最終更新日
2. **目次**
3. **はじめに** — サービス概要、推奨環境、GitHub OAuth ログインの流れ
4. **基本操作** — 画面ごとに以下を記載：
   - **トップ（`/`）** — サービス紹介とログインへの導線
   - **ログイン（`/login`）** — GitHub OAuth ログイン手順
   - **問題一覧（`/problems`）** — カテゴリ・難易度フィルタ、過去解答状況
   - **問題詳細・解答（`/problems/:id`）** — 問題文の読み方、コードエディタ（CodeMirror）の使い方、ブラウザ内型診断、解答送信、採点結果の見方
   - **学習履歴（`/history`）** — 正答率・弱点カテゴリの確認方法
5. **コードエディタの使い方** — CodeMirror の操作（キーバインド、補完、型診断）
6. **採点の仕組み** — サーバ側で Vitest が走り、テストケース全通過で正解判定。タイムアウト・メモリ制限の説明
7. **よくある質問（FAQ）** — 採点エラー時の対処、対応言語、レート制限について

### 3. 管理者向けマニュアル（`admin` または引数なしの場合）

**前提：管理者ダッシュボードは R4 で実装される**（→ [01-roadmap.md](../../../docs/requirements/5-roadmap/01-roadmap.md)）。
R4 未実装の場合は、ユーザーに「R4 の管理ダッシュボード実装後に作成可能」と案内し、スキップする。

対象：運用担当者（自分自身、または将来のチームメンバー）

以下の構成でドキュメントを作成する：

1. **表紙** — タイトル、バージョン、最終更新日
2. **目次**
3. **はじめに** — システム概要、運用環境、ログイン方法
4. **ダッシュボード** — 生成成功率・コスト・採点レイテンシの読み方、アラート閾値
5. **問題管理** — 生成問題の確認、品質スコア（Judge）の見方、不採用問題の扱い
6. **ユーザー管理** — 利用状況、レート制限超過アカウントの確認
7. **ジョブ監視** — `jobs` テーブルの状態確認（queued / running / done / failed / dead）、スタックジョブの手動リクレイム
8. **トラブルシューティング** — LLM API 障害時のフォールバック、サンドボックス障害、コスト超過時の対応
9. **観測性** — Grafana ダッシュボード、Sentry、ログ検索（OTel + Loki）

### 4. HTML 版の生成

- 単一の HTML ファイルとして出力する（外部 CSS は使わず、`<style>` タグ内にスタイルを記載）
- 日本語フォントを指定（Hiragino Kaku Gothic ProN, Noto Sans JP 等）
- レスポンシブ対応（PC・タブレット・スマートフォンで閲覧可能）
- 印刷用スタイル（`@media print`）を含める
- スクリーンショット画像は `images/` ディレクトリからの相対パスで参照する

### 5. PDF 版の生成

HTML 版を元に、Playwright MCP の `browser_run_code` を使って PDF を生成する。

```javascript
async (page) => {
  await page.goto('file:///absolute/path/to/index.html', { waitUntil: 'networkidle' });
  await page.pdf({
    path: '/absolute/path/to/output.pdf',
    format: 'A4',
    margin: { top: '20mm', bottom: '20mm', left: '15mm', right: '15mm' },
    displayHeaderFooter: true,
    headerTemplate: '<div></div>',
    footerTemplate: '<div style="font-size:9px; text-align:center; width:100%;"><span class="pageNumber"></span> / <span class="totalPages"></span></div>',
    printBackground: true,
  });
}
```

- HTML ファイルは絶対パスで `file://` プロトコルで開く
- `printBackground: true` で背景色・画像も PDF に含める

### 6. スクリーンショットの撮影

- Playwright MCP を使ってローカル環境（`http://localhost:3000`）からキャプチャする
- 撮影前に必ずログイン状態を確立する（GitHub OAuth はモック・テストアカウントを使用）
- シードデータ（`pnpm db:seed`）が投入された状態で撮影する
- 管理画面（R4）の撮影には認証が必要なため、テスト用セッションで撮影する

### 7. 最終確認

- HTML ファイルがブラウザで正常に表示されることを確認する
- PDF ファイルが正常に生成されていることを確認する
- 画像パスが正しく設定されていることを確認する
- 生成したファイルの一覧をユーザーに報告する
