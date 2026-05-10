# 0033. バックエンドを Python に pivot

- **Status**: Accepted
- **Date**: 2026-05-09
- **Decision-makers**: 神保 陽平

## Context（背景・課題）

本プロジェクトは TS 版 (`yzanbo/ai-coding-drill`) として設計フェーズを完遂し、`v1.0.0-typescript` タグで凍結済み。設計フェーズの成果物（ADR 全 32 件 / 要件定義書 5 バケット / アーキテクチャ図 / プロダクトバックログ）は実装着手可能な水準にある。

ただし以下の事情からバックエンド言語の再選定が必要になった：

- **採用面接駆動**：Python バックエンド経験が問われる選考機会が複数発生しており、ポートフォリオの戦力化が間に合わない
- **Python エコシステムの portfolio 価値**：FastAPI / SQLAlchemy / LangChain / Pydantic 等は LLM アプリ領域で求人需要が高く、設計判断・実装経験を示せる素材として有力
- **設計の言語非依存性検証の機会**：[ADR 0001](./0001-requirements-as-5-buckets.md) ／ [ADR 0006](./0006-json-schema-as-single-source-of-truth.md) ／ [ADR 0007](./0007-llm-provider-abstraction.md) 等で意識した「言語に縛られない設計」を、実際に別言語で実装し直すことで構造的に検証できる

これらの判断を反映するため、TS 版を `v1.0.0-typescript` タグ時点で fork した別リポジトリ (`yzanbo/ai-coding-drill-python`) を作成し、本リポジトリでバックエンドのみ Python に切り替える方針を採る。本 ADR はその戦略判断を Tier 1 として記録する。

## Decision（決定内容）

バックエンド API の実装言語を **TypeScript (NestJS) から Python に pivot** する。具体構成は以下：

1. **バックエンド API**：Python に切替。**Web framework は FastAPI を採用**（→ [ADR 0034](./0034-fastapi-for-backend.md) で詳述）
2. **Frontend (Next.js / TypeScript)** と **採点ワーカー (Go)** は維持。前者はユーザ向け実装体験、後者は採点ワーカーの軽量並列性とサンドボックス制御の実装済み価値（→ [ADR 0016](./0016-go-for-grading-worker.md)）を踏まえての判断
3. **TS 版リポジトリは凍結保持**：`yzanbo/ai-coding-drill` を `v1.0.0-typescript` タグ時点で凍結し、ポートフォリオ素材として残す。本リポジトリ (`yzanbo/ai-coding-drill-python`) は同タグから派生
4. **Python の残スタック**（ORM / 型チェッカー / モノレポ管理 / 依存整合性 / lint/format / マイグレーション / パッケージ管理）は**実装着手時に確定し、それぞれ別 ADR を起票**する（可逆な判断の遅延、→ [ADR 0007](./0007-llm-provider-abstraction.md) と同方針）
5. **TS 版の改善追従**：TS 版に有用な改善が入った場合は `upstream-ts` remote 経由で cherry-pick 可能とする

本 pivot により失効する TS 系 ADR の取り扱いは [影響を受ける ADR](#影響を受ける-adr) を参照。

## Why（採用理由）

### 採用面接駆動

- Python バックエンド経験を問う選考機会が複数発生しており、TS のままでは面接対応の機会損失が大きい
- ポートフォリオは「動かない設計だけ」だと評価が頭打ちになる時期に差し掛かっており、実装着手の前提条件として言語選定をやり直す必要がある

### Python エコシステムの portfolio 価値

- LLM アプリ領域では Python の比重が高い（OpenAI / Anthropic / Google の SDK、LangChain / LangGraph、評価ツール等）
- FastAPI + Pydantic + SQLAlchemy 2.0 の組み合わせは型安全性と非同期 I/O を兼ね備えた現代的構成で、求人市場の需要も大きい
- Python は採用ワーカー候補として Go と並ぶ言語であり、LLM 連携・データ処理の実装経験は応用範囲が広い

### 設計の言語非依存性を実証

- 設計フェーズで意識した「言語に縛られない判断」（5 バケット要件定義書 / JSON Schema SSoT / LLM プロバイダ抽象化 / Postgres ジョブキュー）が、別言語で再実装できることを構造的に証明する素材になる
- TS 版（`v1.0.0-typescript`）と Python 版を**同時に閲覧可能**にすることで、「同じ設計を 2 言語で実装した」差別化軸が成立する

### 採点ワーカーは Go を維持

- [ADR 0016](./0016-go-for-grading-worker.md) で確立した Go 採用判断（シングルバイナリ / goroutine / Docker SDK 親和性）は実装着手前でも妥当性が変わっていない
- ワーカーまで Python にすると採点並列性とサンドボックス実装の Go 投資が無駄になる
- 言語別の役割分担（Python = アプリケーション層、Go = システム層）はポリグロット構成として説明しやすい

## Alternatives Considered（検討した代替案）

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| A. TS のまま継続 | `v1.0.0-typescript` 設計をそのまま実装に持ち込む | 採用面接対応の機会損失、Python エコシステム portfolio 価値の取りこぼし。設計のみ完成 → 実装に進む段階で言語を再考しないと "ポートフォリオの戦力化が間に合わない" |
| B. 全部 Python（Worker も Python に） | バックエンド・採点ワーカーともに Python | 採点ワーカーの軽量並列性と Docker SDK 親和性は Go の比較優位（→ [ADR 0016](./0016-go-for-grading-worker.md)）が大きい。`v1.0.0-typescript` 時点で確立済みの Go 設計を捨てる合理性は無い |
| C. TS リポジトリを Python に上書き | 単一リポジトリで Python に書き換える | TS 版の portfolio 価値（設計フェーズ完了の証拠）が消える。`v1.0.0-typescript` タグでも履歴は残るが、リポジトリ単位での "完成形" としての提示性が落ちる |
| D. TS 版と Python 版を mono repo に統合 | 1 リポジトリ内で `apps/api-ts/` と `apps/api-py/` を併存 | バックエンドが 2 系統存在する整合性の維持コストが高い。"設計凍結 → 別言語で再実装" の意図が伝わりにくい |

## 影響を受ける ADR

本 pivot により以下の TS 系 ADR は失効・修正対象となる。**Status 変更と本文修正は本 ADR と同 PR 内で実施**する。

### Superseded by 0033（5 件、以後の派生 ADR で追加 supersede 連鎖）

> 本 ADR が起点。後続の派生 ADR（0034〜0040）で個別領域が再判断されると、各 ADR の Status は `Superseded by 0033, NNNN, ...` と複数連結される。最終的な Status は各 ADR 本体を参照。

| ADR | 元タイトル | 最終 Status | 措置 |
|---|---|---|---|
| [0014](./0014-nestjs-for-backend.md) | NestJS for backend | `Superseded by 0033` | 本文は移行判断軌跡として保持。代替判断は [ADR 0034](./0034-fastapi-for-backend.md) |
| [0017](./0017-drizzle-orm-over-prisma.md) | Drizzle ORM over Prisma | `Superseded by 0033, 0037` | 代替判断は [ADR 0037](./0037-sqlalchemy-alembic-for-database.md)（SQLAlchemy 2.0 + Alembic） |
| [0018](./0018-biome-for-tooling.md) | Biome for tooling | `Superseded by 0033` | Frontend 用途（apps/web/）として継続採用、Python 側は [ADR 0020](./0020-python-code-quality.md)（ruff）で代替 |
| [0023](./0023-turborepo-pnpm-monorepo.md) | Turborepo + pnpm workspaces | `Superseded by 0033, 0036` | Frontend モノレポは [ADR 0036](./0036-frontend-monorepo-pnpm-only.md)（pnpm のみ）、Python 側は [ADR 0035](./0035-uv-for-python-package-management.md)（uv workspace）、tool 版数 / タスクランナーは [ADR 0039](./0039-mise-for-task-runner-and-tool-versions.md)（mise）に分離 |
| [0024](./0024-syncpack-package-json-consistency.md) | syncpack | `Superseded by 0033, 0036` | 採用判断は維持、配置を `apps/web/.syncpackrc.ts` に移しルールセット縮小 |

### 本文修正（Status は維持）

| ADR | 措置 |
|---|---|
| [0003](./0003-phased-language-introduction.md) | 「MVP は TS+Go、R7 で Python 追加」→「Python (FastAPI) + Go + TS (Frontend) のレイヤ別ポリグロット構成」に書き換え。Decision 表 / Why の段階導入論点 / Alternatives を現状に合わせて更新。Status は Accepted のまま |
| [0029](./0029-commit-scope-convention.md) | scope `api` の対応領域説明を NestJS → FastAPI に微修正。scope-enum 自体は維持 |
| [0020](./0020-python-code-quality.md) | 「R7 分析パイプライン用」→「バックエンド本体に役割変更」に書き換え。Status は Accepted のまま |

### 維持（変更なし）

[0001](./0001-requirements-as-5-buckets.md) / [0002](./0002-aws-single-cloud.md) / [0004](./0004-postgres-as-job-queue.md) / [0005](./0005-redis-not-for-job-queue.md) / [0006](./0006-json-schema-as-single-source-of-truth.md) / [0007](./0007-llm-provider-abstraction.md) / [0008](./0008-custom-llm-judge.md) / [0009](./0009-disposable-sandbox-container.md) / [0010](./0010-w3c-trace-context-in-job-payload.md) / [0011](./0011-github-oauth-with-extensible-design.md) / [0012](./0012-upstash-redis-over-elasticache.md) / [0013](./0013-vercel-for-frontend-hosting.md) / [0015](./0015-codemirror-over-monaco.md) / [0016](./0016-go-for-grading-worker.md) / [0019](./0019-go-code-quality.md) / [0021](./0021-r0-tooling-discipline.md) / [0022](./0022-config-file-format-priority.md) / [0025](./0025-github-actions-as-ci-cd.md) / [0026](./0026-github-actions-incremental-scope.md) / [0027](./0027-github-actions-sha-pinning.md) / [0028](./0028-dependabot-auto-update-policy.md) / [0030](./0030-commitlint-base-commit-fetch.md) / [0031](./0031-ci-success-umbrella-job.md) / [0032](./0032-github-repository-settings.md)

## Consequences（結果・トレードオフ）

### 得られるもの

- **Python ecosystem の portfolio 経験**：FastAPI / SQLAlchemy / Pydantic / LangChain 等の実装判断・運用経験を直接示せる
- **2 言語実装の差別化軸**：同じ設計仕様（要件定義書 5 バケット）を TS と Python の両方で実装した経験は希少。「設計の言語非依存性」を構造的に証明できる
- **TS 版凍結の portfolio 効果**：`v1.0.0-typescript` タグで「設計フェーズ完了」を明示でき、設計と実装の役割分担を視覚化できる
- **採用面接対応の即応性**：Python 面接機会に対して "今書いている" 実装として提示できる

### 失うもの・受容するリスク

- **TS R0 ツーリングの流用不可**：[Biome](./0018-biome-for-tooling.md) / [syncpack](./0024-syncpack-package-json-consistency.md) / [Knip](./0021-r0-tooling-discipline.md) / [Turborepo](./0023-turborepo-pnpm-monorepo.md) は Python では使えず、Python 等価ツール（ruff / uv 等）の選定 ADR を改めて起票する必要
- **Drizzle 採用判断（[ADR 0017](./0017-drizzle-orm-over-prisma.md)）の実装機会の損失**：型推論・生 SQL 親和性の Drizzle 設計判断は実装で確かめられない。Python ORM（SQLAlchemy 2.0 等）に置換
- **NestJS の DI / Module 設計（[ADR 0014](./0014-nestjs-for-backend.md)）の実装機会の損失**：FastAPI は依存性注入を関数引数ベースで提供するため、Module-Provider-Controller 構造の体験は失われる。代替の規律は実装側で設計
- **2 リポジトリ運用のメンテ手間**：TS 版に有用な改善（要件定義書修正・ADR 追加）が入った場合の cherry-pick コスト。`upstream-ts` remote で物理的には吸収可能だが運用リソース消費は残る
- **設計フェーズ完了とのギャップ**：要件定義書 5 バケットの一部記述（例：[05-runtime-stack.md](../requirements/2-foundation/05-runtime-stack.md) のバックエンド章、[06-dev-workflow.md](../requirements/2-foundation/06-dev-workflow.md) の TS ツーリング章）は Python 用に書き換えが必要。本 PR では README のみを Python 化し、要件定義書本体の追従は後続 PR で扱う

### 将来の見直しトリガー

- **採用先決定 / Python 経験の portfolio 化が完了**：本 pivot の起点だった採用駆動の動機が消滅した場合、TS 版に戻す合理性が出る可能性は理屈上ある（ただし実装が進んだ段階での再 pivot コストは大きく、現実的には不可逆）
- **Python エコシステムが LLM 領域で陳腐化**：例えば LLM SDK が Go-first / Rust-first に大きくシフトした場合、再選定の余地が出る
- **TS 版改善の cherry-pick コストが運用上 pain になる**：TS 版で大きな改善（例：要件定義書の構造変更）が入り Python 版への取り込みが追いつかなくなった場合、TS 版の凍結深度を上げる（ハードフォーク化）か、要件定義書を Python 版主管に切替する判断が必要

## References

- TS 版リポジトリ：[`yzanbo/ai-coding-drill`](https://github.com/yzanbo/ai-coding-drill)（`v1.0.0-typescript` タグで凍結）
- [ADR 0003: 言語の段階導入](./0003-phased-language-introduction.md)（TS+Go → Python の段階導入方針。本 ADR でバックエンドが Python に前倒し）
- [ADR 0016: 採点ワーカーを Go で実装](./0016-go-for-grading-worker.md)（Worker 維持判断の根拠）
- [ADR 0034: バックエンド API に FastAPI を採用](./0034-fastapi-for-backend.md)（Web framework 選定の詳細）
- [ADR 0001: 要件定義書を 5 バケット時系列構造に再編](./0001-requirements-as-5-buckets.md)（言語非依存設計の前提）
- [ADR 0006: JSON Schema を SSoT に](./0006-json-schema-as-single-source-of-truth.md)（言語非依存設計の前提）
- [ADR 0007: LLM プロバイダ抽象化戦略](./0007-llm-provider-abstraction.md)（可逆な判断の遅延の方針）
