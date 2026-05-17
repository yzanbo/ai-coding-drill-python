# 0043. フロントエンドの UI / スタイリングスタック：Tailwind CSS v4 + shadcn/ui + React Hook Form + Zod

- **Status**: Accepted
- **Date**: 2026-05-17
- **Decision-makers**: 神保

## Context（背景・課題）

apps/web（Next.js 16+ / React 19 / TypeScript、→ [ADR 0036](./0036-frontend-monorepo-pnpm-only.md)）で画面・フォームを構成する技術を確定する必要がある。R1-4（[問題表示・解答入力](../requirements/4-features/problem-display-and-answer.md)）でログイン・問題一覧・解答画面・フォームが本格化するため、その手前で UI プリミティブ・スタイリング・フォーム handling・入力検証の 4 つを束ねて凍結したい。

選択肢の組み合わせ（CSS 戦略・コンポーネントライブラリ・フォーム lib・バリデーション lib）が掛け算で膨らむため、**個別判断を後で寄せ集める形よりセットでの選定理由を先に固定する**ほうが整合性が取りやすい。

現状：

- [apps/web/package.json](../../apps/web/package.json) には既に `tailwindcss ^4` / `@tailwindcss/postcss ^4` が dev dep に入っている
- [apps/web/src/app/globals.css](../../apps/web/src/app/globals.css) は v4 の CSS-first 形式（`@import "tailwindcss"` + `@theme inline`）で構成済
- [apps/web/postcss.config.mjs](../../apps/web/postcss.config.mjs) は `@tailwindcss/postcss` プラグインのみ
- shadcn/ui / React Hook Form / Zod は未インストール
- [.claude/rules/frontend.md](../../.claude/rules/frontend.md) には 4 点セットが実装契約として記載済（ADR で背景を分離して書き残す）

関連既存 ADR：

- [ADR 0006](./0006-json-schema-as-single-source-of-truth.md)：Hey API + openapi-zod-client で `apps/web/src/__generated__/api/` に Zod スキーマが自動生成される。フォーム入力検証で同じ Zod を再利用できる前提
- [ADR 0015](./0015-codemirror-over-monaco.md)：コードエディタは CodeMirror。本 ADR の対象外
- [ADR 0042](./0042-frontend-data-fetching-tanstack-query.md)：サーバ状態管理は TanStack Query。本 ADR の対象外

## Decision（決定内容）

apps/web の UI / スタイリングスタックを以下 4 点で固定する：

1. **Tailwind CSS v4**（CSS-first 設定、PostCSS プラグイン経由、`@import "tailwindcss"` 形式）
2. **shadcn/ui**（Radix UI ベースのアクセシブルなコンポーネントをコードコピー形式で `apps/web/src/components/ui/` 配下に追加）
3. **React Hook Form**（uncontrolled・field-level 購読のフォーム handling）
4. **Zod + zodResolver**（フォーム入力検証 / URL クエリパース / 必要に応じて API レスポンスの最終検証。Hey API 生成の Zod スキーマと整合）

導入タイミング：

- Tailwind v4 は R0 で既に導入済（apps/web の scaffold 時点）
- shadcn/ui + React Hook Form + Zod は **R1-1（GitHub OAuth ログイン画面）着手時**にまとめてインストール（ログイン画面が最初のフォーム実装で、shadcn の Form / Button / Input / Label が同時に必要になるため）

shadcn/ui のコンポーネント追加運用は **必要になったタイミングで都度 `npx shadcn-ui@latest add <component>` を実行**する（先取りで一括追加しない）。生成されたコードは `components/ui/` 配下に**自前ソース**として保持し、変更履歴は通常の git に乗せる。

## Why（採用理由）

### Tailwind CSS v4

- **CSS-first 設定**：`tailwind.config.js` が廃止され、テーマ・カラー・フォントは `globals.css` の `@theme inline` で完結する。設定の SSoT が 1 ファイルに集約され、新規参画者が「どこを見れば設計トークンが分かるか」を迷わない
- **Oxide engine**：ビルド速度が v3 比で 5〜10 倍速いとされ、Next.js 16 の Turbopack と組み合わせた DX が良好
- **shadcn/ui が v4 をサポート済**：2025 年中盤に追従済で、CLI 生成テンプレートも v4 前提
- **ポートフォリオ価値**：「最新メジャー版を採用し、CSS-first 移行のメリット / 制約を語れる」差別化軸

### shadcn/ui

- **「ライブラリ」ではなく「コードをコピーする」方式**：依存パッケージとしてバージョンロックされず、必要な部品だけ自前ソースとして所有する。デザイン要件の変化に対して、生成された components/ui/ 配下を直接編集できる
- **Radix UI 由来のアクセシビリティ**：キーボード操作・スクリーンリーダー・focus management が標準装備で、自前で WAI-ARIA を組まなくてよい
- **Tailwind ベース**：CSS-in-JS との二重管理を避けられ、`cn()` ヘルパー（`clsx` + `tailwind-merge`）の作法が rules（[.claude/rules/frontend.md](../../.claude/rules/frontend.md)）と整合
- **Next.js App Router + RSC との親和性**：Server Component で使えるコンポーネントが多く、`"use client"` 境界を意識しやすい
- **学習素材としての可視性**：採用面接で「shadcn のコードを読んだ」と話せる強み

### React Hook Form

- **uncontrolled + field-level 購読**：フォーム規模が大きくなっても再レンダーが特定 field に限定される。CodeMirror（→ [ADR 0015](./0015-codemirror-over-monaco.md)）の重い editor を含む解答画面で再レンダー coalescing が効きやすい
- **shadcn/ui の Form コンポーネントと公式統合**：shadcn 公式 docs の Form パターンは RHF 前提で書かれており、`FormField` / `FormItem` / `FormControl` / `FormMessage` がそのまま使える
- **バリデーションは外部 lib に委譲**：本体は handling に集中し、検証ロジックは Zod へ。関心の分離が明確

### Zod + zodResolver

- **Hey API 生成 Zod スキーマと同じ shape**：[ADR 0006](./0006-json-schema-as-single-source-of-truth.md) で `apps/web/src/__generated__/api/` に生成された Zod スキーマを、フォーム入力検証でそのまま継ぎ足し / 再利用できる
- **TypeScript 型推論**：`z.infer<typeof schema>` で型を 1 箇所から導出でき、型と検証の二重定義を排除
- **discriminated union / transform / refinement** が組み込みで使え、複雑な検証ロジック（パスワード強度・依存 field・条件付き必須）が同じ DSL で書ける
- **コミュニティ規模**：Yup / Joi / Valibot に対し採用事例・記事・型エコシステムが最も厚い

## Alternatives Considered（検討した代替案）

### スタイリング層

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| Tailwind CSS v3（`tailwind.config.js` 形式） | 従来の JS 設定 | v4 が安定版・shadcn 公式も追従済。あえて旧スタイルを採る合理性なし |
| CSS Modules | コンポーネント scoped CSS | Tailwind utility-first 思想と相反。shadcn/ui との衝突 |
| Panda CSS | 型安全な CSS-in-TS（build-time 抽出） | Tailwind v4 + shadcn の組み合わせより採用事例・記事数が少なく、ポートフォリオ評価で語りにくい |
| vanilla-extract | 型安全な CSS-in-TS | 同上。トレードオフが Panda と類似で優位性が薄い |
| Emotion / styled-components | runtime CSS-in-JS | React 19 + RSC との相性が悪く、SSR ハマりが既知 |

### コンポーネントライブラリ層

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| MUI (Material UI) | フル機能コンポーネント | バンドルサイズ大、デザイントークン分離コスト、Tailwind との二重管理 |
| Chakra UI | コンポーネントライブラリ | v3 から CSS-in-JS を離脱したが Tailwind 統合の自然さで shadcn に劣る |
| Mantine | コンポーネントライブラリ | 同上。フル機能だが「コードを所有しない」前提で柔軟性が落ちる |
| Headless UI 単体 + 自前スタイル | プリミティブのみ採用、スタイルは自作 | アクセシビリティと一貫したスタイルを自前で再発明するコストに対し、shadcn が提供する初期テンプレートのほうが効率的 |
| Radix UI 直使い + 自前スタイル | shadcn の手前で止める | shadcn は Radix のラッパで、ラッパ層を自前で書き直す価値が薄い |

### フォーム handling 層

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| Formik | controlled 主体のフォーム lib | RHF より再レンダー多。メンテナンスペースの鈍化と shadcn との統合事例の薄さ |
| React Final Form | フォーム lib | RHF よりコミュニティ規模・記事数で劣り、shadcn 統合の Form コンポーネントも非対応 |
| 素の useState + 手書きハンドラ | ライブラリ不使用 | フォーム数 5+ で破綻。バリデーション・touched / dirty / error 状態を自前で組むコストが見合わない |
| `<form action={...}>` + Server Action（React 19 標準） | フレームワーク標準のフォーム送信 | progressive enhancement 用途には強いが、クライアント側 reactive バリデーション・ポーリング系（採点結果）との結合が薄い。ただし R6 以降の見直し候補（→ §Consequences） |

### バリデーション層

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| Yup | バリデーション lib | TypeScript 型推論の精度で Zod 優位。Hey API 公式 Zod プラグインとの非整合 |
| Valibot | 軽量バリデーション（modular import） | バンドルサイズで Zod を上回るが、Hey API 公式プラグイン・shadcn 公式統合がともに Zod 前提 |
| io-ts | 関数型 codec | DX が硬く採用事例が薄い |
| ArkType | 高速・型直接記述 | 新興でコミュニティ規模・ecosystem が薄い |

## Consequences（結果・トレードオフ）

### 得られるもの

- **stack の整合性**：Tailwind v4 → shadcn/ui → RHF → Zod の連鎖が公式統合で繋がり、glue code が薄い
- **同じ Zod を再利用**：フォーム入力検証・URL クエリ検証・API 入出力検証で同じ DSL が使える（Hey API 生成 Zod との shape 一致、→ [ADR 0006](./0006-json-schema-as-single-source-of-truth.md)）
- **アクセシビリティの担保**：Radix UI（shadcn 基盤）由来でキーボード操作・スクリーンリーダー対応が標準装備
- **自前所有のコンポーネント**：`components/ui/` 配下が自前コードなのでカスタマイズが自由。npm のメジャー breaking change を待たずに直接修正できる
- **ポートフォリオ価値**：「最新の Tailwind v4 CSS-first を採用」「shadcn/ui を選んだ理由を語れる」差別化軸

### 失うもの・受容するリスク

- **shadcn/ui の自動更新が無い**：npm パッケージではなくコードコピーのため、shadcn 側の改善（バグ修正・新コンポーネント追加）を自動で受けられない。必要時に CLI 再実行 + diff レビューで明示的に取り込む運用コストを受容
- **Tailwind v4 の edge case**：リリース直後で「v3 では動いたが v4 では挙動が違う」プラグイン / 記事が混在する。stack overflow 等の検索ヒットが v3 寄りになる時期がある
- **RHF + Zod の学習コスト**：Zod の discriminated union・transform・refinement、RHF の Controller / register の使い分け、shadcn の `<FormField>` パターンの 3 段で習熟が要る
- **バンドルサイズ**：RHF（~10 KB gzip）+ Zod（~14 KB gzip）+ Radix の必要 primitive 群が乗る。Lighthouse / Core Web Vitals 指標化される段階で再評価
- **React 19 標準フォームとの重複**：`<form action>` + Server Action と RHF は概念的に重なる領域があり、将来「サーバ側バリデーション中心」に寄せる場合は構成が冗長化する

### 将来の見直しトリガー

- **React 19+ の `<form action>` + Server Action がクライアント側バリデーション・ポーリングまで含めて成熟**し、RHF を置き換えられるエコシステムが形成された場合
- **Tailwind v5 のリリース時**に v4 → v5 の breaking change が大きい、または CSS-first 設定の前提が崩れた場合
- **shadcn/ui が npm パッケージ配布に方針転換**した場合（自前所有メリットが消える）
- **フォーム画面数が極端に少ない**（< 5 画面で頭打ち）状態が続き、RHF が overkill になった場合
- **Valibot 等のバンドルサイズ優位 lib が Hey API 公式サポート**を獲得し、Zod から乗り換える価値が出た場合

## References

- [.claude/rules/frontend.md](../../.claude/rules/frontend.md) — 実装契約（コンポーネント配置・命名・フォーム規約・`cn()` ヘルパー）
- [.claude/rules/frontend-component.md](../../.claude/rules/frontend-component.md) — コンポーネント単位の規約
- [05-runtime-stack.md: フロントエンド](../requirements/2-foundation/05-runtime-stack.md#フロントエンド)
- [01-roadmap.md: R1-1 / R1-4](../requirements/5-roadmap/01-roadmap.md)
- [GitHub OAuth ログイン](../requirements/4-features/authentication.md) — shadcn/ui + RHF + Zod を導入する最初の画面
- [問題表示・解答入力](../requirements/4-features/problem-display-and-answer.md) — 解答フォームの本実装
- [ADR 0006](./0006-json-schema-as-single-source-of-truth.md) — Hey API + Zod 生成パイプライン
- [ADR 0015](./0015-codemirror-over-monaco.md) — コードエディタ（本 ADR の対象外）
- [ADR 0042](./0042-frontend-data-fetching-tanstack-query.md) — サーバ状態管理（本 ADR の対象外）
- Tailwind CSS v4 公式ドキュメント
- shadcn/ui 公式ドキュメント
- React Hook Form 公式ドキュメント
- Zod 公式ドキュメント
