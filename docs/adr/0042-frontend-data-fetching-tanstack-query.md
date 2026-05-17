# 0042. フロントエンドのデータフェッチ戦略：TanStack Query を R1-4 で導入

- **Status**: Accepted
- **Date**: 2026-05-17
- **Decision-makers**: 神保

## Context（背景・課題）

Next.js 16+（App Router）でフロントエンドを実装する際、サーバ状態（API レスポンス）の取得・キャッシュ・再取得をどう扱うかを決める必要がある。本サービスは非同期ジョブ中心（問題生成 / 採点）で、解答送信後に **採点結果をポーリング** する UX が R1-5（[F-04: 自動採点](../requirements/4-features/F-04-auto-grading.md)）で必須となる。

選択肢は大きく 3 つ：(1) 導入なし（RSC + `fetch` のみ） / (2) SWR / (3) TanStack Query。[05-runtime-stack.md](../requirements/2-foundation/05-runtime-stack.md#フロントエンド) では TanStack Query を採用すると既に明記しているが、**いつ導入するか** が未定で、Provider セットアップだけが先行すると R1-1〜R1-3 で不要な複雑度を抱え込むリスクがある。

関連：
- 型同期パイプライン（→ [ADR 0006](./0006-json-schema-as-single-source-of-truth.md)）で Hey API から `@tanstack/react-query` プラグイン経由で `*Options` / query key を生成可能
- フロントエンドフック規約（→ [.claude/rules/frontend-hooks.md](../../.claude/rules/frontend-hooks.md)）で `useGet*` 命名と `isLoading` 初期値の方針が既にある

## Decision（決定内容）

フロントエンドのサーバ状態管理は **TanStack Query を採用** し、**R1-4（[F-03: 問題表示・解答入力](../requirements/4-features/F-03-problem-display-and-answer.md)）着手時に導入**する。R1-1〜R1-3 では Server Component + `fetch` 直呼びのみで貫通させ、Provider セットアップは行わない。

導入時の作業：

1. `apps/web/` で `pnpm add @tanstack/react-query @tanstack/react-query-devtools`
2. ルートレイアウトに `QueryClientProvider` を追加（Server / Client 境界に合わせたラッパー作成）
3. [apps/web/openapi-ts.config.ts](../../apps/web/openapi-ts.config.ts) の `plugins` に `@tanstack/react-query`（`queryOptions: true, mutationOptions: true`）を追加し `mise run web:types-gen` 再実行
4. [.claude/rules/frontend-hooks.md](../../.claude/rules/frontend-hooks.md) の `useGet*` 命名規約と擦り合わせ（生成された `*Options` を `useGet*` フックでラップする方針）

用途は [05-runtime-stack.md: フロントエンド](../requirements/2-foundation/05-runtime-stack.md#フロントエンド) のとおり**ポーリング / `useMutation` / クライアント側キャッシュに限定**し、問題一覧・問題詳細の単純取得は Server Component の `fetch` で行う。

## Why（採用理由）

### TanStack Query を選んだ理由

- **ポーリングが標準装備**：R1-5（F-04 自動採点）でジョブステータスを polling する際、`useQuery` の `refetchInterval` で書くのが最も素直。素手で polling を書くと負債化しやすい
- **Hey API 公式プラグインがある**：型同期パイプライン（ADR 0006）と直結し、`*Options` / query key / mutation が自動生成される。SWR には Hey API 公式プラグインがなく、ラッパーを手書きする必要がある
- **mutation + cache invalidation**：解答送信後の履歴更新、F-05 学習履歴の楽観的更新など、R1〜R2 で出てくるパターンに合う

### R1-4 で導入する理由（タイミング）

- R1-1（OAuth）/ R1-3（問題生成 enqueue を 1 回叩くだけ）では fetch 1 発で済み、TanStack Query を入れても恩恵がなく Provider セットアップの先行コストだけが発生する
- R1-4 で「問題一覧 / 問題詳細」の表示が始まり、キャッシュ・再取得・遷移時の保持が効き始める
- R1-5 の polling が必須化する直前のタイミングで足場を作るのが、追加複雑度と DX のバランスが最良

## Alternatives Considered（検討した代替案）

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| 導入なし（RSC + `fetch` のみ） | Server Component と form action で貫通 | R1-5 の採点結果 polling を素手で書くのが負債化しやすい。R2 でジョブ状態可視化が入る前提でも足場が無いと辛い |
| SWR | 軽量なデータフェッチライブラリ | Hey API 公式プラグインがなく、生成 SDK を SWR fetcher に手動で渡すラッパーが必要。中間的で「わざわざ選ぶ強い理由」が無い |
| TanStack Query を R0 / R1-1 で先行導入 | 最初から Provider を立てる | R1-1〜R1-3 では使い道がなく、Provider セットアップだけが先行する。YAGNI |
| TanStack Query を R2 以降に遅らせる | R1 は素 fetch で完走 | R1-5 の polling を素手で書く負債が残る |

## Consequences（結果・トレードオフ）

### 得られるもの
- R1-5 の polling、R2 のジョブ状態可視化、R1-5 以降の mutation + invalidation を標準パターンで書ける
- Hey API 公式プラグインで型・query key・mutation が自動生成され、`useGet*` フック実装が薄くなる
- Server Component の単純 fetch と Client Component の状態管理が役割分担で住み分けられる

### 失うもの・受容するリスク
- バンドルサイズ増（TanStack Query 本体 + devtools）。Client Component 限定なので Server Component 側のバンドルには影響しない
- `QueryClientProvider` セットアップ・`staleTime` / `gcTime` 等の概念学習コスト
- Server Component と Client Component でデータ取得方法が二系統になる（一覧・詳細は RSC、ポーリング系は TanStack Query）

### 将来の見直しトリガー
- Next.js App Router の標準 cache API が成熟し、polling / mutation も標準でカバーされるようになった場合
- バンドルサイズが Lighthouse 指標で問題化した場合
- R6 以降で SSR / RSC の比率を上げる方向に大きく舵を切る場合

## References

- [05-runtime-stack.md: フロントエンド](../requirements/2-foundation/05-runtime-stack.md#フロントエンド)
- [01-roadmap.md: R1-4](../requirements/5-roadmap/01-roadmap.md)
- [F-03: 問題表示・解答入力](../requirements/4-features/F-03-problem-display-and-answer.md)
- [F-04: 自動採点](../requirements/4-features/F-04-auto-grading.md)
- [ADR 0006: JSON Schema を SSoT とする型同期](./0006-json-schema-as-single-source-of-truth.md)
- [.claude/rules/frontend-hooks.md](../../.claude/rules/frontend-hooks.md)
- Hey API TanStack Query プラグイン公式ドキュメント
