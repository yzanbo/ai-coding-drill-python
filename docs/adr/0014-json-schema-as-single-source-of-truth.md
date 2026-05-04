# 0014. 共有データ型は JSON Schema を Single Source of Truth とし、各言語向けに自動生成する

- **Status**: Accepted
- **Date**: 2026-04-25
- **Decision-makers**: 神保 陽平

## Context（背景・課題）

このプロジェクトは複数言語を横断する設計：
- TypeScript（NestJS API、Next.js フロント）
- Go（採点ワーカー）
- Python（Phase 7：RAG・評価パイプライン）

これら 3 言語が**同じデータ構造**を扱う必要がある：
- ジョブペイロード（採点・問題生成）
- ジョブ結果
- 問題スキーマ
- API リクエスト/レスポンス

各言語で型を**手動で書くと食い違いが発生**し、デバッグ困難なバグの温床になる。型の整合性を構造的に保証する仕組みが必要。

## Decision（決定内容）

**JSON Schema を Single Source of Truth（SSoT）として 1 か所に置き、各言語向けの型を自動生成する**設計を採用する。

### 配置
```
packages/shared-types/
├── schemas/                  ← ★ Single Source of Truth
│   ├── job.schema.json
│   ├── problem.schema.json
│   └── grading-result.schema.json
├── generated/
│   ├── ts/                   ← Zod スキーマ + TS 型（コミットする）
│   ├── go/                   ← Go struct（gitignore、build 時生成）
│   └── python/               ← Pydantic モデル（gitignore、build 時生成）
├── scripts/
│   └── generate.ts
└── package.json
```

### 言語別の生成ツール（初期想定、実装時再評価）
| 言語 | 生成ツール | 出力 |
|---|---|---|
| TypeScript | `json-schema-to-zod` | Zod スキーマ + 型推論 |
| Go | `quicktype` | Go struct + JSON タグ |
| Python | `datamodel-code-generator` | Pydantic v2 モデル |

### コミット方針
- **TS は生成物をコミットする**：ビルド前に型が必要、IDE 補完の即時性、`workspace:*` 参照のため
- **Go / Python は gitignore**：`go generate` / `uv build` 時に都度生成、各言語慣習に従う

## Alternatives Considered（検討した代替案）

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| JSON Schema を SSoT とし各言語生成 | （採用） | — |
| 各言語で手動定義 | シンプル | 型の食い違いが必発、メンテナンス地獄 |
| Protocol Buffers / gRPC | 多言語ネイティブ、コードジェン強力 | gRPC 通信に縛られる、HTTP/JSON 主体の本プロジェクトと相性悪、学習コスト |
| OpenAPI Spec を SSoT | API 仕様も同時に表現可 | API 以外（ジョブペイロード等）の型表現が冗長、JSON Schema の方が汎用 |
| TypeScript を SSoT（zod-to-json-schema） | TS-first | Go / Python への変換ツールが少ない、TS が「正」になると他言語が二級扱い |
| TypeBox / valibot 等の TS-first ライブラリ | TS で型 + ランタイム検証 | 多言語生成のエコシステムが未成熟 |

## Consequences（結果・トレードオフ）

### 得られるもの
- 3 言語間の型整合性を**構造的に保証**（食い違いバグの温床を排除）
- スキーマ変更が 1 箇所、生成で全言語が自動追従
- Phase 7 で Python を追加する際のコスト最小化（既存 schema をそのまま流用）
- ランタイムバリデーション（Zod / Pydantic）が同じスキーマで実現
- API 仕様書（OpenAPI）への変換も容易（JSON Schema → OpenAPI コンポーネント）
- 「言語間の整合性問題を理解し、解決する設計力」をポートフォリオで語れる

### 失うもの・受容するリスク
- 生成ツールチェーンのセットアップコスト（初期）
- 各生成ツールの仕様差分による微妙なズレ（型の表現方法）
- 各言語独自の型表現（例：TS の Discriminated Union）は JSON Schema で表現が複雑になる
- 生成スクリプトのメンテナンス

### 将来の見直しトリガー
- gRPC が必要な機能（双方向ストリーム等）が出た場合は Protocol Buffers 移行を検討
- 生成ツールチェーンの保守コストが価値を上回った場合は手動定義に戻す判断もあり
- TypeSpec（Microsoft 製、新興）が成熟したら SSoT 言語の見直し

## References

- [01-data-model.md: ジョブペイロードのスキーマ](../requirements/3-cross-cutting/01-data-model.md)
- [05-runtime-stack.md: 共有型・スキーマ](../requirements/2-foundation/05-runtime-stack.md)
- [ADR 0010: 言語の段階導入](./0010-phased-language-introduction.md)
- [ADR 0012: モノレポツール](./0012-turborepo-pnpm-monorepo.md)
