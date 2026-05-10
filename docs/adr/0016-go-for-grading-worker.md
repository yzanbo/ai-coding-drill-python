# 0016. 採点ワーカーを Go で実装

- **Status**: Accepted
- **Date**: 2026-05-09 <!-- ADR 0040 で apps/grading-worker → apps/workers/grading にリネーム、Worker 群への拡張方針を明記 -->
- **Decision-makers**: 神保 陽平

> **2026-05-09 追記**：[ADR 0040](./0040-worker-grouping-and-llm-in-worker.md) で以下が変更された。Go 採用判断そのものは維持。
> - **ディレクトリ構造**：`apps/grading-worker/` → `apps/workers/grading/`（`apps/workers/<name>/` グループ配下パターンに統一）。本文中の「採点ワーカー」「`apps/grading-worker`」は新パスに読み替える
> - **LLM 呼び出しの所在**：API 側集中ではなく **Worker 側で judge / generation の LLM を呼び出す** 方針に変更。本文 §Why 4 の「LLM 関連は API 側に集中」は ADR 0040 で覆ったため、§将来の見直しトリガーが発火済み。Go の Anthropic SDK 成熟度は当時より改善しており、Go から直接 LLM を呼ぶ構成で問題ないと判断
> - 新規 Worker（generation 等）も同じ Go 採用パターンを継承する（ADR 0040 §将来の見直しトリガー参照）

> **2026-05-09 追記（Backend pivot）**：[ADR 0033](./0033-backend-language-pivot-to-python.md) で API は NestJS → FastAPI（Python）に変更された。本文の「NestJS 開発との文脈切替」は「FastAPI（Python）開発との文脈切替」と読み替える。ポリグロット（Python / Go / TS）構成での Go 採用判断はむしろ強化された。

## Context（背景・課題）

採点ワーカーの実装言語を決める必要がある。

- 役割：Postgres からジョブ取得 → Docker API でサンドボックスコンテナ起動 → Vitest で TS コード実行 → 結果書き戻し
- 特性：高頻度・短命・並列、Docker 操作が中心
- ランニングコストを抑えたい
- ポートフォリオで TypeScript 以外の言語も見せたい
- 採点対象コードは TS で確定

## Decision（決定内容）

**Go** で採点ワーカーを実装する。Web フレームワークは使わず、標準 `net/http` + 必要ライブラリ（`docker/docker/client`, `pgx/v5`, `go-redis`, `log/slog`, `otel`, `testify`）で構成。

## Why（採用理由）

1. **採点ワーカーの特性（高頻度・短命・並列）に最適**
   - シングルバイナリ・低メモリ・高速起動でランニングコストを最小化
   - goroutine による軽量並列採点が Node.js / Python のメモリフットプリントを大幅に下回る
2. **Docker クライアントの公式サポート**
   - `github.com/docker/docker/client` が公式提供されており、Docker Engine API 操作の生態系が最も成熟
   - Rust や Python は Docker SDK の成熟度・更新頻度で Go に劣る
3. **ポリグロット設計の見せ場**
   - TypeScript と並走させることで「言語を使い分ける設計判断」をポートフォリオで語れる
   - Node.js に統一すると言語選定の見せ場が消える
4. **採点対象コードが TS で確定しているため、ワーカー言語と採点対象言語を分離できる**
   - ワーカー側で LLM 呼び出しが発生しないため、Anthropic SDK 成熟度の差は影響しない
   - LLM 関連は API 側（FastAPI / Python、→ [ADR 0034](./0034-fastapi-for-backend.md)）に集中させ、ワーカーは「Docker 操作と DB アクセスに特化したシンプルな存在」に留められる
5. **過剰なフレームワーク採用を避ける判断も見せられる**
   - 標準 `net/http` + 必要最小ライブラリで構成し、Echo / Gin / Fiber のようなフレームワークは規模に対して不要と判断
   - 「規模に応じた選定」をワーカー単位でも体現
6. **Claude Code・LLM ツールチェーンの Go サポートが厚い**
   - Rust に対する Go の優位として、AI 補完・静的解析・テストツールチェーンの実用度が高い

## Alternatives Considered（検討した代替案）

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| Go | シングルバイナリ、低メモリ、Docker クライアント公式 | （採用） |
| Node.js | 言語統一でシンプル（Backend が TS だった `v1.0.0-typescript` 時点での仮想代替案。Backend は ADR 0033 で Python に pivot 済） | メモリフットプリントが大きい、起動が遅い、Docker 操作の生態系が弱い、ポリグロットの見せ場が消える |
| Rust | 高性能・型安全 | 学習コスト高、Docker クライアントの成熟度が Go より低い、Claude Code のサポートも Go ほど厚くない |
| Python | LLM エコシステムと親和性 | メモリフットプリントが大きい、採点ワーカーの特性（軽量・並列）に合わない |

## Consequences（結果・トレードオフ）

### 得られるもの
- シングルバイナリ配布、小さな Docker イメージ、高速起動でランニングコスト削減
- `github.com/docker/docker/client` による公式の Docker 操作
- goroutine による軽量並列採点
- ポートフォリオで「言語を使い分ける設計判断」を語れる
- 標準ライブラリで十分な規模に保ち、過剰なフレームワーク採用を避ける判断も見せられる

### 失うもの・受容するリスク
- 言語が増えることによる学習・運用コスト（FastAPI / Python 開発との文脈切替）
- 各社 LLM SDK の Go 実装は TS/Python に比べて成熟度が劣る。ADR 0040 で LLM 呼び出しを Worker 側に集約したため、`net/http` 直接呼び出し + `LlmProvider` 抽象化レイヤで吸収する方針

### 将来の見直しトリガー
- ワーカー側で複雑な LLM 呼び出しが必要になった場合（その時は LLM 関連のみ TS / Python に切り出す）

## References

- [02-architecture.md: 採点ワーカー](../requirements/2-foundation/02-architecture.md#採点ワーカーgo)
- [05-runtime-stack.md: 採点ワーカー](../requirements/2-foundation/05-runtime-stack.md#採点ワーカーgo)
