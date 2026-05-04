# 0004. バックエンド API に NestJS を採用

- **Status**: Accepted
- **Date**: 2026-04-25
- **Decision-makers**: 神保 陽平

## Context（背景・課題）

API 層のフレームワークを 1 つに決める必要がある。

- 言語は TypeScript で確定
- 機能：認証、問題 CRUD、LLM 呼び出し（生成・Judge）、ジョブ投入、観測性
- 実装速度を最大化したい（MVP 完成を優先）
- ポートフォリオで設計力をアピールしたい
- 実務で NestJS を使用中

## Decision（決定内容）

**NestJS** を採用。Module 構成は `AuthModule` / `ProblemsModule` / `GenerationModule` / `GradingModule` / `ObservabilityModule`。設計スタイルは機能別モジュール + シンプルレイヤード（Controller / Service）で統一し、データアクセスは Service から Drizzle ORM を直接呼び出す（Repository レイヤは設けない）。

## Alternatives Considered（検討した代替案）

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| NestJS | DI / Module / Decorator | （採用） |
| Hono | 超軽量、エッジ対応 | 設計の指針が薄く、規模が大きくなると散らかりやすい。NestJS 経験を活かせない |
| Fastify | 高速、プラグイン式 | 同上、NestJS の中でも内部採用されるレベル |
| Express | 老舗 | モダン感がなく、ポートフォリオで差別化されない |
| tRPC | 型安全 RPC | フロント・バック密結合になる、API 公開を見せにくい |
| Next.js Route Handlers のみ | フロントと同居 | API が複雑化したとき責務が混ざる、設計力アピールが弱い |
| Encore.ts | 新興、インフラ込み | 学習コスト、エコシステムが未成熟 |

## Consequences（結果・トレードオフ）

### 得られるもの
- 実務経験を活かして MVP の実装速度を最大化
- DI / Module / Guard / Interceptor によるレイヤード設計が綺麗に書け、テスタビリティが高い
- 求人市場での評価が最も高いフレームワークの一つ
- `@nestjs/passport` / `class-validator` / `@nestjs/swagger` などの公式エコシステムが充実

### 失うもの・受容するリスク
- 軽量フレームワーク（Hono 等）に比べて起動が重い（cold start で 2〜3 秒）
- バンドルサイズが大きい
- ECS Fargate の最小タスクを 1 で常駐させる必要があり、scale-to-zero 構成を取りづらい

### 将来の見直しトリガー
- cold start が UX 上致命的になる経路（公開 API 等）が出てきた場合は、その経路だけ Hono などの軽量フレームワークで実装することを検討

## References

- [02-architecture.md: Backend API](../requirements/2-foundation/02-architecture.md#backend-apinestjs)
- [05-runtime-stack.md: バックエンド API](../requirements/2-foundation/05-runtime-stack.md#バックエンド-apinestjs--typescript)
