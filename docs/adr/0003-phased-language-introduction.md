# 0003. レイヤ別ポリグロット構成（Python + Go + TypeScript）

- **Status**: Accepted
- **Date**: 2026-05-09 <!-- ADR 0033（Python pivot）に合わせて本文を書き換え -->
- **Decision-makers**: 神保 陽平

## Context（背景・課題）

ポートフォリオで複数言語を扱える証明をしたい。一方で、「広く浅く」な技術アピールは避け、**各言語の使いどころに明確な役割**を持たせたい。

- 候補言語：Python（AI / LLM / データ系）、Go（システム層 / 軽量並列性）、TypeScript（Web フロント / 型駆動）
- 言語選定そのものに ADR 起票の判断軸がある（Why サブセクション参照）
- バックエンド言語の選定経緯：当初 TS (NestJS) で設計フェーズを完遂し `v1.0.0-typescript` タグで凍結したが、採用面接駆動で Python に pivot（→ [ADR 0033](./0033-backend-language-pivot-to-python.md)）。本 ADR はその後の最新状態を反映する

## Decision（決定内容）

3 言語を**レイヤ別の役割**で並列導入する：

| レイヤ | 言語 | 役割 |
|---|---|---|
| **バックエンド API** | **Python**（FastAPI） | 認証・問題 CRUD・ジョブ enqueue。LLM 呼び出しは Worker 側に委譲（→ [ADR 0034](./0034-fastapi-for-backend.md) / [ADR 0040](./0040-worker-grouping-and-llm-in-worker.md)） |
| **Worker 群（採点 / 問題生成 / …）** | **Go** | `apps/workers/<name>/` 配下に独立 Go module として配置（→ [ADR 0040](./0040-worker-grouping-and-llm-in-worker.md)）。Postgres ジョブ受信 + Docker SDK + LLM 呼び出し。軽量・並列・システム制御（→ [ADR 0016](./0016-go-for-grading-worker.md)） |
| **フロントエンド** | **TypeScript**（Next.js） | ユーザ向け UI、CodeMirror エディタ、React Query。型駆動の開発体験 |
| 将来の拡張 | （言語アダプタ層経由） | 採点対象言語の多言語化（Python / Next.js コンポーネント等）に対応する設計余地を残す |

## Why（採用理由）

### 1. 各言語の役割が明確

- **Python（バックエンド API）**：LLM SDK の async 親和性、Pydantic / FastAPI による型駆動、データ・評価エコシステム（LangChain 等）の portfolio 価値（→ [ADR 0033](./0033-backend-language-pivot-to-python.md)）
- **Go（採点ワーカー）**：シングルバイナリ・goroutine・Docker SDK の親和性、軽量並列性。サンドボックス制御のシステム層として最適（→ [ADR 0016](./0016-go-for-grading-worker.md)）
- **TypeScript（フロント）**：Next.js + React Query + CodeMirror の現代的フロント体験、Vercel 統合（→ [ADR 0013](./0013-vercel-for-frontend-hosting.md)）
- 「広く浅く」ではなく「適材適所」と説明できる

### 2. ポリグロット要求の正当化

- 1 言語のみではポリグロット差別化が消える
- 全部 Python だと採点ワーカーの軽量並列性・Docker 操作で Go の比較優位を捨てる
- 全部 Go だと LLM エコシステム・フロント DX が不利
- **Python（アプリ層）+ Go（システム層）+ TS（UI 層）** が、各言語の比較優位を最も活かす最小構成

### 3. 設計の言語非依存性を実証

- 設計フェーズ（要件定義書 5 バケット / JSON Schema SSoT / LLM プロバイダ抽象化 / Postgres ジョブキュー）は TS 版で完遂し、Python に pivot しても同じ設計が成立することを構造的に検証している（→ [ADR 0033](./0033-backend-language-pivot-to-python.md) Context）
- 「言語選定能力 + 設計の言語独立性」を 2 軸で示せる

### 4. 言語アダプタ層の設計余地を残す

- 将来の採点対象言語多言語化（ユーザが Python や別言語の問題を解く）を見据え、最初から構造的に拡張可能な設計を意識する
- 採点対象コードの言語アダプタ層（採点 Worker 内に置く、ユーザコードのランタイムを抽象化する層）は MVP 時点では TypeScript（Vitest）のみ対応、後続フェーズで他言語を追加

## Alternatives Considered（検討した代替案）

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| **採用：Python + Go + TS（レイヤ別）** | 各層に最適言語を配置 | （採用） |
| TS のみ（Frontend / Backend / Worker 全て TS） | 単一言語で簡略 | ポリグロット差別化が消える、採点ワーカーの軽量並列性で Go の優位を捨てる、Python エコシステム portfolio が消える |
| Python + TS（Go なし） | バックエンド・採点ワーカーともに Python | 採点ワーカーの軽量並列性・Docker SDK 親和性に Python は不向き（→ [ADR 0016](./0016-go-for-grading-worker.md)）。`v1.0.0-typescript` 時点で確立済みの Go 設計を捨てる合理性は無い |
| Go + TS（Python なし） | バックエンドを Go で書く | LLM エコシステム（Anthropic / OpenAI / LangChain 公式 SDK）の async 親和性で Go が不利。AI / データ系の portfolio 訴求力が削がれる |
| TS（Backend）+ Go + Python（評価のみ後付け） | TS 版時点の旧構成（段階導入） | 採用面接駆動の pivot で失効（→ [ADR 0033](./0033-backend-language-pivot-to-python.md)） |

## Consequences（結果・トレードオフ）

### 得られるもの

- 3 言語ポリグロット構成で「言語選定能力」を示せる（広く浅くではなく、適材適所）
- 各言語の役割が明確で、面接時の説明が首尾一貫する
- 設計フェーズを TS で完遂し Python で再実装したことで、設計の言語非依存性を構造的に証明できる

### 失うもの・受容するリスク

- 3 言語をまたぐビルド・テスト・デプロイのオーケストレーションコスト
- 言語ごとに型表現・例外設計・並列性モデルが異なるため、共有型は JSON Schema SSoT（→ [ADR 0006](./0006-json-schema-as-single-source-of-truth.md)）と OpenAPI（→ [ADR 0034](./0034-fastapi-for-backend.md)）で吸収する必要
- 言語ごとのツーリング選定 ADR が複数必要（パッケージ管理 / lint / フォーマッタ / 型チェッカー / マイグレーション 等）

### 将来の見直しトリガー

- 採点対象言語の多言語化を本格導入するタイミングで、言語アダプタ層の設計を別 ADR で起票
- 観測性 / 共有型生成パイプラインの実装を進める中で、3 言語横断のオーバーヘッドが運用 pain になった場合は、レイヤ統合（例：Frontend を Python 配信 SSR に寄せる等）を再検討

## References

- [ADR 0033: バックエンドを Python に pivot](./0033-backend-language-pivot-to-python.md)（バックエンド言語選定の最新判断）
- [ADR 0034: バックエンド API に FastAPI を採用](./0034-fastapi-for-backend.md)（Python の Web framework 選定）
- [ADR 0016: 採点ワーカーを Go で実装](./0016-go-for-grading-worker.md)（Go 採用の根拠）
- [ADR 0013: Frontend ホスティングに Vercel を採用](./0013-vercel-for-frontend-hosting.md)（Next.js / TS のホスティング）
- [ADR 0006: JSON Schema を SSoT に](./0006-json-schema-as-single-source-of-truth.md)（3 言語横断の型生成基盤）
- [01-overview.md: 言語・フレームワーク構成ロードマップ](../requirements/1-vision/01-overview.md)
- [02-architecture.md: 言語構成ロードマップ](../requirements/2-foundation/02-architecture.md)
