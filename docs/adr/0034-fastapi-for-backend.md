# 0034. バックエンド API に FastAPI を採用

- **Status**: Accepted
- **Date**: 2026-05-09
- **Decision-makers**: 神保 陽平

## Context（背景・課題）

[ADR 0033](./0033-backend-language-pivot-to-python.md) でバックエンド API の実装言語を TypeScript (NestJS) → Python に pivot することが決定した。次に必要な判断は **Python の Web framework 選定**である。

選定にあたっての制約・要請：

- **型安全性**：TS 版で享受していた型駆動開発体験（IDE 補完 / ビルド時エラー）に近い水準を Python でも維持したい
- **OpenAPI スキーマ自動生成**：[ADR 0006](./0006-json-schema-as-single-source-of-truth.md) の Pydantic-first SSoT 設計により、FastAPI 自動 OpenAPI 3.1 を Frontend 向け型生成パスの起点として運用できる
- **非同期 I/O**：[ADR 0007](./0007-llm-provider-abstraction.md) で扱う LLM プロバイダ呼び出しは I/O 待ちが支配的。`async/await` ネイティブで並列性を引き出したい
- **エコシステム成熟度**：採用市場 / 求人需要 / 公式 SDK 親和性。ポートフォリオで「採用判断ができる」見せ方ができる framework であること
- **本プロジェクト規模**：小〜中規模（→ [.claude/CLAUDE.md コーディング規約：規模に応じた選定](../../.claude/CLAUDE.md#設計原則)）。Django REST Framework 級の重量級 framework は不要

## Decision（決定内容）

バックエンド API の Web framework に **FastAPI** を採用する。

- バージョン制約は付けない（実装着手時に最新安定版を採用）
- Pydantic をリクエスト/レスポンスのバリデーション・スキーマ定義の前提とする（FastAPI が内部で必須依存しているため事実上一体）
- OpenAPI スキーマは FastAPI が Pydantic から自動生成するものを **HTTP API 境界（Frontend 向け）**の artifact とする。**Job キュー境界（Worker 向け）**には Pydantic から `model.model_json_schema()` で個別 JSON Schema を `apps/api/job-schemas/` に出力する。境界が 2 つあるため伝送路も 2 つ用意する（→ [ADR 0006](./0006-json-schema-as-single-source-of-truth.md) の Pydantic-first SSoT 設計）
- DI（依存性注入）は FastAPI の `Depends` 方式を基本とし、明示的な Module / Provider 構造（NestJS 流）を再現する規律は実装側で別途定める

ORM（SQLAlchemy 2.0 / SQLModel 等）・パッケージ管理（uv / poetry 等）・lint/format（ruff 等）・型チェッカー（mypy / pyright）等の周辺スタックは **本 ADR の対象外**。実装着手時にそれぞれ別 ADR を起票する（[ADR 0033](./0033-backend-language-pivot-to-python.md) の方針）。

## Why（採用理由）

### 1. 型ヒント駆動 + Pydantic 連携で TS 並みの型安全性

- 関数シグネチャの型ヒントがそのままリクエスト / レスポンスのバリデーションに反映される
- Pydantic（Rust 製コア）でランタイムバリデーション性能も実用域
- IDE 補完・mypy / pyright での静的型検査が NestJS + class-validator 構成と同等以上に機能する

### 2. OpenAPI スキーマの自動生成

- ルート定義からそのまま OpenAPI 3.x スキーマが導出される（コード = 仕様）
- Frontend 側の型生成（openapi-typescript 等）・採点ワーカー側の Go 型生成・Swagger UI / Redoc によるドキュメント提供を 1 ソースから配給可能
- [ADR 0006](./0006-json-schema-as-single-source-of-truth.md) の Pydantic-first SSoT 設計と一体化し、API 層と内部共有データの両方が同じ Pydantic モデルから派生する

### 3. async/await ネイティブ

- LLM プロバイダ呼び出し（`openai` / `anthropic` 等の公式 SDK）は async ファースト
- ジョブキュー LISTEN/NOTIFY（→ [ADR 0004](./0004-postgres-as-job-queue.md)）の通知受信ループも async で書ける
- I/O 待ちが支配的な本プロジェクトのワークロードと適合

### 4. エコシステム・採用市場での実勢

- Python Web framework の中で求人・採用面接で言及される頻度が最も高い
- Anthropic / OpenAI / Google の公式 SDK が async ファーストで設計されており、FastAPI と組み合わせる事例・記事が豊富
- LLM 関連の OSS ライブラリ（LangChain / LlamaIndex / Instructor 等）も FastAPI との統合例を公式に提供

### 5. プロジェクト規模との適合

- Django REST Framework は管理画面 / ORM / 認証 / フォーム等のフルスタックを抱え、本プロジェクト（API のみ、認証は GitHub OAuth、ORM は別 ADR で SQLAlchemy 系を想定）には機能過剰
- FastAPI は薄い framework で、必要な機能だけ組み合わせる構成が取れる

## Alternatives Considered（検討した代替案）

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| A. Django REST Framework | Django 上で REST API を構築するエコシステム最大手 | フルスタック前提で本プロジェクト規模に対し過剰。GitHub OAuth・ジョブキュー LISTEN/NOTIFY・LLM 抽象化レイヤといった本プロジェクト固有の構成を組む際、Django の規約（ORM 結合・settings.py / app 構造）が制約として効きすぎる |
| B. Litestar | 型ヒント駆動 + async ネイティブで FastAPI と機能的に競合する後発 framework | 機能・性能は魅力的だが、エコシステム成熟度・採用面接での認知度・LLM SDK 連携事例が FastAPI に劣る。求人 portfolio としての訴求力で FastAPI が優位 |
| C. Flask + 拡張群 | 軽量で実績豊富、`flask-restx` / `apispec` 等で OpenAPI を後付け | 型ヒント・async が後付けで開発体験が劣る。OpenAPI は外付けライブラリ依存で SSoT 化が脆い。FastAPI の存在意義（Flask の弱点を解消する後継）と被る |
| D. Starlette（FastAPI の基盤）を直接使う | より低レベル、router と middleware のみ | リクエスト / レスポンスのバリデーション・OpenAPI 自動生成・依存性注入を自前実装する必要があり、FastAPI が解決済みの問題を再実装することになる |

## Consequences（結果・トレードオフ）

### 得られるもの

- **型安全 + OpenAPI 自動生成 + async ネイティブの揃い踏み**：3 要件を 1 framework で満たす数少ない選択肢
- **Pydantic を共有データ型 SSoT として活用**：[ADR 0006](./0006-json-schema-as-single-source-of-truth.md) で Pydantic を Single Source of Truth と確定。FastAPI 自動 OpenAPI 3.1（Frontend 向け）と `model.model_json_schema()`（Worker 向け）の両出力が Pydantic 1 箇所定義から導出される
- **LLM SDK との async 親和性**：プロバイダ抽象化レイヤ（[ADR 0007](./0007-llm-provider-abstraction.md)）の実装が `async def` で素直に書ける
- **Swagger UI / Redoc を標準同梱**：開発時の API 探索・対外説明素材を追加コストなしで得られる

### 失うもの・受容するリスク

- **NestJS の明示的 Module / DI 構造の再現は別途設計が必要**：FastAPI の `Depends` は関数引数ベースで、Module-Provider-Controller 構造のような階層化は framework 標準では提供されない。レイヤード設計（Controller / Service / Repository 等）を実装側で規律する必要
- **Framework が比較的若い**（2018 〜）：Django や Flask に比べ運用実績の蓄積年数が浅い。breaking change への追従コスト（過去に Pydantic 移行で大規模な追従が発生した実績あり）はある
- **同期 SDK との組み合わせには工夫が必要**：一部のライブラリ（古い ORM 等）は同期前提なので、`run_in_threadpool` 等での吸収が必要になるケースがある
- **「依存性注入を関数引数で表現する」設計に慣れる必要**：NestJS のクラスベース DI からの移行は思考の切替コストを伴う

### 将来の見直しトリガー

- **Pydantic / FastAPI に致命的な breaking change が連発する**：v2 のような大規模移行が頻発し追従コストが運用上 pain になる場合、Litestar 等への乗り換えを再検討
- **Django 的なフルスタック機能（管理画面・ロール管理 UI 等）が本格的に必要になる**：管理者 UI の作り込みが本プロジェクト範囲を超えて重くなった場合、Django REST Framework への部分移行を検討
- **OpenAPI 自動生成が本プロジェクトの SSoT 戦略から外れる**：例えば API 仕様を別ツール（Stoplight / OpenAPI Generator 直書き等）で先に書く運用に切り替える場合、FastAPI の自動生成優位性は薄れる

## References

- [ADR 0033: バックエンドを Python に pivot](./0033-backend-language-pivot-to-python.md)（本 ADR の前提となる言語選定）
- [ADR 0014: バックエンド API に NestJS 採用](./0014-nestjs-for-backend.md)（Superseded by 0033、TS 版時点の対応判断）
- [ADR 0006: Pydantic を SSoT に、用途別伝送路で各言語へ展開](./0006-json-schema-as-single-source-of-truth.md)（OpenAPI 自動生成 + JSON Schema 出力の運用方針）
- [ADR 0007: LLM プロバイダ抽象化戦略](./0007-llm-provider-abstraction.md)（async I/O が支配的な実装の前提）
- [ADR 0004: Postgres をジョブキューに採用](./0004-postgres-as-job-queue.md)（LISTEN/NOTIFY の async 利用を前提）
- [FastAPI 公式](https://fastapi.tiangolo.com/)
- [Pydantic 公式](https://docs.pydantic.dev/)
