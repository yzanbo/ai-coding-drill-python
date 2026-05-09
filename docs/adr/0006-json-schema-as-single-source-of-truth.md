# 0006. 共有データ型は Pydantic を Single Source of Truth とし、用途別伝送路で各言語に展開する

- **Status**: Accepted
- **Date**: 2026-05-09 <!-- Python pivot（ADR 0033）に追従して JSON Schema-first → Pydantic-first に転換 -->
- **Decision-makers**: 神保 陽平

## Context（背景・課題）

このプロジェクトは複数言語を横断する設計（→ [ADR 0003](./0003-phased-language-introduction.md)）：

- **Python**（FastAPI、Backend 本体、→ [ADR 0033](./0033-backend-language-pivot-to-python.md) / [ADR 0034](./0034-fastapi-for-backend.md)）
- **TypeScript**（Next.js、Frontend）
- **Go**（採点ワーカー、→ [ADR 0016](./0016-go-for-grading-worker.md)）

これら 3 言語が**同じデータ構造**を扱う必要がある：

- API リクエスト / レスポンス型（Frontend ↔ Backend 間の HTTP 契約）
- ジョブペイロード（Backend が Postgres にエンキュー、Worker が SKIP LOCKED で取得、→ [ADR 0004](./0004-postgres-as-job-queue.md)）
- ジョブ結果 / 問題スキーマ / 採点結果

各言語で型を**手動で書くと食い違いが発生**し、デバッグ困難なバグの温床になる。型の整合性を構造的に保証する仕組みが必要。

### Python pivot（2026-05-09）に伴う SSoT 戦略の見直し

本 ADR は当初「JSON Schema を SSoT として `packages/shared-types/schemas/` に置く」設計だった（Python は R7 分析パイプライン用想定）。Python pivot で Backend が Python になり、以下の事実が判明：

- **FastAPI は Pydantic から OpenAPI 3.1 を自動生成**する（→ [ADR 0034](./0034-fastapi-for-backend.md) で OpenAPI 自動生成を SSoT として運用すると明記済み）
- **Pydantic は `model.model_json_schema()` で JSON Schema を標準出力**できる（PEP 標準）
- 「JSON Schema を SSoT、Pydantic を生成側」とすると、**FastAPI で書くべき Pydantic と生成された Pydantic が二重定義**になり破綻する

このため、Python pivot 後は **Pydantic そのものを SSoT に転換**するのが自然。Pydantic は API スキーマと内部データモデルの両方を一元的に表現でき、FastAPI / openapi-ts / quicktype 等の周辺エコシステムが Pydantic 出力（OpenAPI 3.1 / JSON Schema）を入力として扱える。

### 流通経路の二分

Worker は **API クライアントではなく Postgres を直接読む**（[ADR 0004](./0004-postgres-as-job-queue.md) の SKIP LOCKED ベース設計）。一方 Frontend は API クライアントとして HTTP 経由で Backend を叩く。**この非対称性が型生成パスの選定に影響する**：

| 言語 | 必要な型 | 流通経路 |
|---|---|---|
| TS（Frontend） | API リクエスト / レスポンス + Zod ランタイム検証 + HTTP クライアント | OpenAPI 3.1 経由 |
| Go（Worker） | ジョブペイロード struct + JSON タグ。**HTTP クライアントは不要** | JSON Schema 経由 |

判断のために参照した情報源：

- [FastAPI Generating SDKs](https://fastapi.tiangolo.com/advanced/generate-clients/)
- [Hey API openapi-ts Zod Plugin](https://heyapi.dev/openapi-ts/plugins/zod)
- [How To Generate an OpenAPI Document With Pydantic V2 - Speakeasy](https://www.speakeasy.com/openapi/frameworks/pydantic)
- [oapi-codegen は OpenAPI 3.1 未対応 / ogen は対応](https://github.com/ogen-go/ogen)

## Decision（決定内容）

**Pydantic モデル（`apps/api/` 配下）を Single Source of Truth とし、用途別の伝送路で TS / Go に展開する**設計を採用する。

### 配置と流通経路

```
apps/api/ （Python Backend）
  └─ src/.../schemas/   ← ★ Single Source of Truth（Pydantic v2 モデル）
       │
       ├──[API 契約]──→ FastAPI 自動 OpenAPI 3.1（/openapi.json）
       │                    │
       │                    ├──→ apps/web/ （Frontend）
       │                    │     Hey API（openapi-ts + Zod プラグイン）
       │                    │     生成物：TS 型 + Zod スキーマ + HTTP クライアント
       │                    │
       │                    └──→ Swagger UI / Redoc（人間向け、FastAPI 標準同梱）
       │
       └──[非 API 共有データ]──→ model.model_json_schema() で JSON Schema 出力
                                     │
                                     └──→ apps/grading-worker/ （Go）
                                           quicktype
                                           生成物：Go struct + JSON タグ
```

### 言語別の生成ツール

| 言語 | 入力源 | 生成ツール | 出力 | コミット方針 |
|---|---|---|---|---|
| **Python**（Backend） | （SSoT 自身、生成不要） | — | Pydantic v2 モデルそのもの | ソースコードとしてコミット |
| **TypeScript**（Frontend） | FastAPI 自動 OpenAPI 3.1 | **Hey API**（`@hey-api/openapi-ts` + Zod プラグイン） | TS 型 + Zod スキーマ + 型付き HTTP クライアント | **生成物をコミット**（IDE 補完即時性、ビルド前に型必要） |
| **Go**（Worker） | Pydantic 出力の JSON Schema（ジョブペイロードのみ） | **quicktype** | Go struct + JSON タグ | **gitignore**（`go generate` 時に都度生成、Go 慣習に従う） |

### 生成パイプラインの実装

- **OpenAPI 出力**：`mise run api-openapi-export` → FastAPI の `/openapi.json` を JSON ファイルとしてリポジトリに書き出し（または直接 in-memory 配信）
- **TS 生成**：`mise run web-types-gen` → Hey API CLI で OpenAPI から TS / Zod / HTTP クライアントを生成
- **JSON Schema 出力**：`mise run api-job-schemas-export` → `model.model_json_schema()` を呼ぶ Python スクリプトで `packages/shared-schemas/job/*.schema.json` を生成
- **Go 生成**：`mise run worker-types-gen` → quicktype で JSON Schema から Go struct を生成
- **CI ガード**：上記 4 タスクを CI で実行し、`git diff --exit-code` で「生成物の更新忘れ」を fail-closed（drift 検出ジョブ、→ [ADR 0026](./0026-github-actions-incremental-scope.md) で R3 追加項目）

### 配置物理パス

```
apps/api/src/<package>/schemas/         ← Pydantic SSoT（コミット）
apps/api/openapi.json                    ← FastAPI 自動生成 OpenAPI 3.1（コミット、CI で drift 検出）
apps/web/src/__generated__/api/          ← Hey API 生成物（TS + Zod + HTTP client、コミット）
packages/shared-schemas/job/*.json       ← Pydantic から書き出した JSON Schema（コミット、Worker 入力源）
apps/grading-worker/internal/jobtypes/   ← quicktype 生成物（gitignore、go generate）
```

### Pydantic ↔ TypeScript の API 外直接変換は採用しない

`pydantic-to-typescript` のような Pydantic → TS 直接変換ツールは存在するが、本 ADR では採用しない：

- API 契約は OpenAPI 経由でフルセット（型 + Zod + HTTP クライアント）が手に入る
- API 外の共有データ（ジョブペイロード）は Frontend には不要（Worker 専用）。Frontend が必要になった場合のみ JSON Schema → TS 変換を追加検討

## Why（採用理由）

### 1. Python pivot の利点を最大化

- Backend が Python になった結果、**Pydantic は API スキーマ・バリデーション・OpenAPI 生成・JSON Schema 出力を一手に担う**位置にある
- Pydantic 1 箇所の定義から FastAPI の `/openapi.json` が自動生成され、TS / Go の型生成の入力源になる
- 「Backend で書く Pydantic」と「JSON Schema から生成された Pydantic」の二重定義を構造的に回避

### 2. FastAPI 自動 OpenAPI 3.1 を SSoT にできる

- ルート定義からそのまま OpenAPI 3.1 が導出される（[ADR 0034](./0034-fastapi-for-backend.md) で確立済み）
- 「コード = 仕様」が成立し、API ドキュメント（Swagger UI / Redoc）が同時に手に入る
- TS 側の Zod ランタイム検証も同じ OpenAPI から派生 → API 入出力のバリデーションが Frontend / Backend で同じスキーマに収束

### 3. 用途別伝送路で「適材適所」

- **Frontend は API クライアント**：OpenAPI 3.1 → Hey API で TS 型 + Zod + HTTP クライアントを一括取得（Frontend が必要な全要素が揃う）
- **Worker は DB 直読、API クライアント不要**：JSON Schema → quicktype で軽量に Go struct + JSON タグだけ取得（重量級の `ogen` を導入する理由がない）
- CLAUDE.md「規模に応じた選定」原則と整合

### 4. ランタイムバリデーションの一貫性

- Python（Pydantic）/ TypeScript（Zod、Hey API 経由生成）/ Go（必要なら encoding/json + 手書きバリデーション）が**同じ OpenAPI / JSON Schema を起点にバリデート**する
- API 入出力・ジョブペイロード検証で Backend と Frontend が同じスキーマに収束、不整合が原理的に発生しない

### 5. 既存 ADR との整合

- [ADR 0034](./0034-fastapi-for-backend.md)：FastAPI 自動 OpenAPI を SSoT として運用 ✅
- [ADR 0033](./0033-backend-language-pivot-to-python.md)：Python pivot 後の周辺スタックは実装着手時に確定 → 本 ADR で確定
- [ADR 0037](./0037-sqlalchemy-alembic-for-database.md)：SQLAlchemy ORM と Pydantic の分離方針 → 本 ADR の Pydantic-as-SSoT は API スキーマと内部共有データ用途、ORM 用途とは別レイヤ

### 6. ポートフォリオでの訴求

- 「言語間の整合性問題を理解し、構造的に解決する設計力」を ADR + 実装で示せる
- Pydantic-first / OpenAPI-first / 用途別伝送路という現代的な polyglot SSoT 設計は採用面接で説明しやすい

## Alternatives Considered（検討した代替案）

### SSoT 言語の選定

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| **Pydantic（Python）が SSoT（採用）** | Backend で書く Pydantic を起点に各言語へ展開 | — |
| JSON Schema を SSoT（旧 ADR 0006、本書き換え前） | `packages/shared-types/schemas/*.json` を起点 | Python pivot 後は FastAPI で書く Pydantic と二重定義になる。Python のエコシステムが Pydantic 中心に発達しており、Pydantic を「下流」にすると FastAPI / OpenAPI 自動生成と整合しない |
| OpenAPI Spec（YAML/JSON）を手書きで SSoT | API 仕様も同時に表現 | API 以外（ジョブペイロード）の表現が冗長、FastAPI 自動生成と二重管理になる |
| TypeScript（Zod）を SSoT | TS-first | Backend が Python なので Backend へのフィードバックパスが遠回り、TS から Pydantic 生成は datamodel-code-generator が必要だが TS の表現力（Discriminated Union 等）と乖離する |
| TypeBox / valibot 等 TS-first ライブラリ | TS で型 + ランタイム検証 | 多言語生成のエコシステムが未成熟、Backend が Python の構成と相性悪い |
| Protocol Buffers / gRPC | 多言語ネイティブ、コードジェン強力 | gRPC 通信に縛られる、HTTP/JSON 主体の本プロジェクトと相性悪、学習コスト |
| TypeSpec（Microsoft 製） | 中立 IDL 言語、新興 | 2026 時点で成熟度が FastAPI / Pydantic に劣る、Backend Python の利点を活かせない |

### TS（Frontend）の生成ツール

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| **Hey API（`@hey-api/openapi-ts` + Zod プラグイン、採用）** | OpenAPI 3.1 → TS 型 + Zod + HTTP クライアント | — |
| Orval | OpenAPI → React Query / SWR 統合 + Zod | 機能は同等以上だが React Query 等の特定 lib に最適化、Hey API の方がランタイム非依存で柔軟 |
| `openapi-typescript-codegen` | 旧来の OpenAPI クライアント生成 | メンテナンス縮小、Hey API が後継として推奨される |
| `openapi-zod-client`（zodios 系） | Zodios HTTP クライアント生成 | Zodios という特定クライアントに依存、Hey API は標準 fetch 使用で軽量 |
| `pydantic-to-typescript` 単体 | Pydantic → TS 型直接変換 | 型のみ生成、Zod / HTTP クライアントが付かない。OpenAPI を経由した方が Frontend に必要な要素が一括で揃う |

### Go（Worker）の生成ツール

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| **quicktype（採用）** | JSON Schema → Go struct + JSON タグ | Worker は HTTP クライアント不要、struct だけで十分なので軽量に済む |
| `ogen` | OpenAPI 3.1 → Go HTTP サーバ / クライアント | Worker は API を呼ばないため過剰。将来 Worker が API を叩くなら採用検討 |
| `oapi-codegen` | OpenAPI → Go | **OpenAPI 3.1 未対応**、FastAPI と非互換 |
| `datamodel-code-generator`（Go 出力） | JSON Schema → Go | quicktype の方が Go struct 生成の品質が安定 |

## Consequences（結果・トレードオフ）

### 得られるもの

- **3 言語間の型整合性を構造的に保証**：Pydantic 1 箇所変更で全言語が自動追従、食い違いバグの温床を排除
- **Backend が Python である利点を最大化**：FastAPI 自動 OpenAPI / Pydantic JSON Schema 標準出力という Python ecosystem の強みを設計に直結
- **API ドキュメントが副産物**：Swagger UI / Redoc が `/docs` で自動配信、追加コストゼロ
- **ランタイムバリデーションが両端で一貫**：Backend Pydantic / Frontend Zod が同じスキーマから派生
- **適材適所の生成パス**：Frontend は HTTP クライアント込み、Worker は struct のみ。重量級ツールを必要箇所だけに留める

### 失うもの・受容するリスク

- **Pydantic-first ロックイン**：他の Python ORM / バリデーションへの乗り換えコストが上がる（ただし Pydantic は FastAPI と一体で確立しているため低リスク）
- **`apps/api/` が型 SSoT を抱える**：Backend repo に他 app（Frontend / Worker）が依存する構造になる（mise / monorepo 内なので物理的には支障なし）
- **生成スクリプトのメンテナンス**：4 タスク（OpenAPI 出力 / TS 生成 / JSON Schema 出力 / Go 生成）を mise.toml に整備する必要
- **drift 検出の CI ジョブ**：生成物コミット忘れを防ぐ `git diff --exit-code` ジョブが必要（[ADR 0026](./0026-github-actions-incremental-scope.md) の R3 拡張項目に位置付ける）
- **Pydantic / FastAPI / Hey API の各 breaking change**：3 ツールの追従コストが直列に発生

### 将来の見直しトリガー

- **Worker が API クライアントになった場合**：`quicktype` から `ogen`（OpenAPI 3.1 対応）への移行を検討
- **Pydantic v3 / FastAPI 大規模 breaking change**：移行コストを ADR で再評価
- **gRPC / 双方向ストリームが必要になった場合**：Protocol Buffers 移行を検討（極めて低確率）
- **TypeSpec が成熟した場合**：中立 IDL を SSoT とする選択肢を再評価
- **生成ツールチェーンの保守コストが価値を上回った場合**：手動定義への部分的回帰を検討

## References

- [ADR 0033: バックエンドを Python に pivot](./0033-backend-language-pivot-to-python.md)（SSoT 戦略書き換えの契機）
- [ADR 0034: バックエンド API に FastAPI を採用](./0034-fastapi-for-backend.md)（OpenAPI 自動生成を SSoT 化する基盤）
- [ADR 0035: Python のパッケージ管理に uv を採用](./0035-uv-for-python-package-management.md)（Pydantic 周辺ツールの管理基盤）
- [ADR 0037: DB ORM・マイグレーションに SQLAlchemy + Alembic を採用](./0037-sqlalchemy-alembic-for-database.md)（ORM と Pydantic の分離方針）
- [ADR 0003: レイヤ別ポリグロット構成](./0003-phased-language-introduction.md)
- [ADR 0004: Postgres をジョブキューに採用](./0004-postgres-as-job-queue.md)（Worker が DB 直読する設計の前提）
- [ADR 0026: GitHub Actions の段階拡張](./0026-github-actions-incremental-scope.md)（生成物 drift 検出ジョブの追加先）
- [ADR 0039: タスクランナー兼 tool 版数管理に mise を採用](./0039-mise-for-task-runner-and-tool-versions.md)（4 タスク（OpenAPI / TS / JSON Schema / Go）の起動経路）
- [01-data-model.md: ジョブペイロードのスキーマ](../requirements/3-cross-cutting/01-data-model.md)
- [05-runtime-stack.md: 共有型・スキーマ](../requirements/2-foundation/05-runtime-stack.md)
- [FastAPI 公式 - SDK 生成](https://fastapi.tiangolo.com/advanced/generate-clients/)
- [Hey API openapi-ts](https://heyapi.dev/openapi-ts/)
- [Hey API Zod Plugin](https://heyapi.dev/openapi-ts/plugins/zod)
- [Pydantic v2 公式](https://docs.pydantic.dev/)
- [quicktype 公式](https://quicktype.io/)
- [ogen - OpenAPI v3 code generator for Go](https://github.com/ogen-go/ogen)（将来の Worker API クライアント化時の候補）
