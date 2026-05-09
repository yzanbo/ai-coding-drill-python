# 0038. テストフレームワーク確定（pytest / Vitest / Playwright / Go testing）

- **Status**: Accepted
- **Date**: 2026-05-09
- **Decision-makers**: 神保 陽平

## Context（背景・課題）

[ADR 0033](./0033-backend-language-pivot-to-python.md) の Python pivot により、TS 版で前提としていた **Jest（NestJS 標準）** が使えなくなった。3 言語ポリグロット構成（Python / TS / Go）に対応するテストフレームワークを確定する必要がある。

選定にあたっての制約・要請：

- **言語ごとのデファクト**を採用（独自選定でエコシステム / 採用市場価値を損なわない）
- **async ネイティブ対応**：Backend (FastAPI) / Frontend (React Server Components) ともに async I/O が支配的
- **CI 並列実行・カバレッジ計測**：標準的に動かせること
- **E2E テスト**：ブラウザ自動化を 1 ツールでカバー
- **ミューテーションテストは保留**：MVP に不要、R2 以降に再判断

判断のために参照した情報源：

- [FastAPI Testing 公式](https://fastapi.tiangolo.com/tutorial/testing/)
- [Testing FastAPI Applications: pytest + httpx best practices 2026](https://kirankumarvel.wordpress.com/2025/09/09/testing-fastapi-apps-pytest-guide/)

## Decision（決定内容）

レイヤごとに以下のテストフレームワークを採用する。

### Backend（Python / FastAPI）

- **`pytest`**：テストランナー（Python ecosystem デファクト）
- **`pytest-asyncio`**：async テスト対応
- **`httpx.AsyncClient`**：FastAPI アプリへの HTTP 呼び出し（FastAPI の `TestClient` は httpx ベースで構築されている）
- **`pytest-cov`**：カバレッジ計測（出力は coverage.py）
- **DI override**：FastAPI の `app.dependency_overrides` 機構で DB / 外部 API をモック差し替え
- **テスト DB**：本番 DB と分離した PostgreSQL コンテナを CI で起動

### Frontend（TS / Next.js）

- **`Vitest`**：ユニット / コンポーネントテスト（Vite ecosystem 統合、Jest より高速）
- **`@testing-library/react`**：React コンポーネントテスト（React デファクト）
- **`Playwright`**：E2E テスト（クロスブラウザ・モバイルエミュレーション・スクリーンショット差分）
- **`@vitest/coverage-v8`**：カバレッジ計測

### Worker（Go）

- **`testing`**：Go 標準テストパッケージ
- **`testify`**：assertion / mock の補助ライブラリ
- **`go test -cover`**：カバレッジ計測

### 共通基盤

- **カバレッジ集約**：[Codecov](https://about.codecov.io/) に各言語のカバレッジレポートを送信し、PR コメントで可視化
- **CI 統合**：[ADR 0031](./0031-ci-success-umbrella-job.md) の `ci-success` umbrella job 配下に test ジョブを追加（Python / TS / Go 各言語 1 ジョブ）

### スコープ外（将来の判断）

- **ミューテーションテスト**：MVP では採用しない。R2 以降に必要性を再判断（Python なら `mutmut`、TS なら `stryker-js`、Go なら `go-mutesting` 等が候補）
- **Visual regression テスト**：必要が生じた段階で Playwright のスクリーンショット機能 / Chromatic 等を再評価
- **負荷テスト**：MVP では採用しない（必要が生じたら `locust` / `k6` 等を別 ADR で起票）

## Why（採用理由）

### Backend：pytest + httpx

1. **Python ecosystem のデファクト**：FastAPI 公式ドキュメントが pytest 前提で書かれており、事例・記事の量が圧倒的
2. **async ネイティブ対応**：`pytest-asyncio` で `@pytest.mark.asyncio` を付けるだけで async テスト関数が書ける
3. **`httpx.AsyncClient` で FastAPI を直接呼べる**：ネットワークオーバーヘッドなし、deterministic / 高速
4. **DI override で外部依存を差し替え**：FastAPI の `Depends` 機構と相性が良く、DB / 外部 API のモック差し替えが綺麗に書ける
5. **fixture / parametrize / conftest の表現力**：複雑なテストデータ構築、共通セットアップを宣言的に書ける

### Frontend：Vitest + RTL + Playwright

1. **Vitest は Jest API 互換 + Vite 統合**：Jest の知識が活き、ESM / TypeScript ネイティブで設定が薄い
2. **Jest より高速**：HMR 風の watch mode、CI でも並列実行が標準で速い
3. **React Testing Library は React デファクト**：「ユーザがどう見るか」をベースにしたテスト思想、accessibility テストにも繋がる
4. **Playwright はクロスブラウザ E2E のデファクト**：Chromium / Firefox / WebKit を 1 ツールでカバー、モバイルエミュレーション・トレース・動画記録機能が標準同梱
5. **Cypress と異なり async/await ネイティブ**：Promise チェーンの自前管理が不要、テストコードが素直

### Worker：testing + testify

1. **Go 標準ライブラリ + 慣習**：[ADR 0019](./0019-go-code-quality.md) の方針（Go は標準ツールを優先）と整合
2. **testify は assertion / mock の業界標準**：Go コミュニティで事実上のデファクト
3. **`go test -race` で goroutine レース検出**：採点ワーカーの並列性検証に有用

### ミューテーションテストを保留する理由

- **MVP に不要**：通常のテストカバレッジで十分な品質ゲートを構築できる
- **CI 時間負荷が大きい**：テストコード規模が小さい段階で導入してもメリットが薄い
- **R2 以降の選択肢を狭めない**：将来 Python なら `mutmut`、TS なら `stryker-js` 等が選べる

## Alternatives Considered（検討した代替案）

### Backend（Python）

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| **pytest（採用）** | Python ecosystem デファクト | — |
| `unittest`（標準ライブラリ） | Python 標準のテストフレームワーク | 表現力が pytest に劣る、fixture / parametrize が脆弱、FastAPI 事例が少ない |
| `nose2` | unittest 拡張 | メンテナンス縮小、新規採用理由なし |

### Frontend（TS）

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| **Vitest（採用）** | Vite ecosystem 統合の高速ランナー | — |
| Jest | JS テストランナーの旧デファクト | ESM / TS 対応が後付け、Vitest 比で遅い、Vite ecosystem への統合度が低い |
| Mocha + Chai | 老舗の組み合わせ | TS / ESM の設定が冗長、現代的な ergonomics で Vitest に劣る |
| **Playwright（E2E、採用）** | クロスブラウザ E2E デファクト | — |
| Cypress | E2E ツール、UI 操作デバッガが優秀 | Chromium 系のみ（Firefox/WebKit は限定的）、async/await ネイティブでない、モバイルエミュレーションが弱い |
| Selenium | E2E 老舗 | API が冗長、現代的 ergonomics で Playwright / Cypress に劣る |

### Worker（Go）

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| **testing + testify（採用）** | 標準 + ecosystem デファクト補助 | — |
| Ginkgo + Gomega | BDD スタイルのテストフレームワーク | DSL が独自、Go コミュニティのメインストリームから外れる |

## Consequences（結果・トレードオフ）

### 得られるもの

- **3 言語に対し各エコシステムのデファクトが揃う**：採用市場 / portfolio 価値・トラブルシュート情報量を最大化
- **async テストが自然に書ける**：FastAPI / Next.js (RSC) ともに async 前提のため、テスト側の整合性が取れる
- **E2E は Playwright 1 本でクロスブラウザカバー**：シナリオテスト・モバイル検証・accessibility 検査を 1 ツールで完結
- **カバレッジ集約が Codecov 1 箇所に集まる**：3 言語横断で品質ゲートが見える

### 失うもの・受容するリスク

- **3 言語で 3 種類のテスト DSL を学ぶ必要**：これはポリグロット構成の代償として不可避
- **Playwright のブラウザインストールが CI で重い**：初回 ~200MB のダウンロード、CI キャッシュ戦略が必要
- **ミューテーションテストの導入は遅延**：MVP 期間中は通常カバレッジで品質確保
- **Cypress の優れた UI デバッガ体験を捨てる**：Playwright Trace Viewer で代替可能

### 将来の見直しトリガー

- **テストコード規模が大きくなった場合**（数千ファイル超）→ ミューテーションテスト導入を検討
- **E2E が遅くなった場合**（CI で 10 分超等）→ Playwright のシャーディング・並列実行を強化
- **Visual regression が必要になった場合** → Playwright のスクリーンショット差分機能 / Chromatic を再評価

## References

- [ADR 0019: Go のコード品質ツール](./0019-go-code-quality.md)（Go 標準ツール優先方針との整合）
- [ADR 0020: Python のコード品質ツールに ruff + pyright を採用](./0020-python-code-quality.md)（Pyright で型注釈付きテスト）
- [ADR 0031: ci-success umbrella ジョブ](./0031-ci-success-umbrella-job.md)（CI 統合の前提）
- [ADR 0033: バックエンドを Python に pivot](./0033-backend-language-pivot-to-python.md)（Jest 廃止の契機）
- [ADR 0034: バックエンド API に FastAPI を採用](./0034-fastapi-for-backend.md)
- [pytest 公式](https://docs.pytest.org/)
- [FastAPI Testing 公式](https://fastapi.tiangolo.com/tutorial/testing/)
- [Vitest 公式](https://vitest.dev/)
- [Playwright 公式](https://playwright.dev/)
- [testify](https://github.com/stretchr/testify)
