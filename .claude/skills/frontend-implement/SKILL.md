---
name: frontend-implement
description: 要件 .md を読んで Next.js のフロントエンドを実装する
argument-hint: "[<name>] (例: problem-display-and-answer, learning)"
---

# 要件ベースのフロントエンド実装

引数 `$ARGUMENTS` を機能名として解釈する。

## 手順

### 1. 要件の読み込み

- 機能要件：`docs/requirements/4-features/$ARGUMENTS.md`
- ベース要件：[01-overview.md](../../../docs/requirements/1-vision/01-overview.md)、[02-architecture.md](../../../docs/requirements/2-foundation/02-architecture.md)、[02-api-conventions.md](../../../docs/requirements/3-cross-cutting/02-api-conventions.md)
- フロントエンドルール：[.claude/rules/frontend.md](../../rules/frontend.md)

ファイルが存在しない場合は、ユーザーに `/new-requirements` で先に作成することを提案する。

### 2. 画面の確認

要件 .md の「画面」セクション（`_template.md` のセクション名）を確認する。画面が空または不足している場合は、先に記入するようユーザーに促す。

以下を抽出する：

- **画面**：パス、概要、主要コンポーネント、使用 API
- **ユーザーフロー**：ステップの流れ
- **バリデーションルール**：FE/BE 共通のルール

### 3. 既存 FE コードの確認

- 関連するページ（`apps/web/src/app/(routing)/` 配下の `page.tsx`）を確認
- 関連する `_components/`、`_hooks/` を確認
- 既存の共通コンポーネント（`components/ui/`、`components/parts/`）の再利用可能性を確認
- API クライアント（`lib/api/`）と型（Hey API が `apps/api/openapi.json` から生成、既定の出力先 `apps/web/src/lib/api/generated/`、→ [ADR 0006](../../../docs/adr/0006-json-schema-as-single-source-of-truth.md)）を確認

### 4. 実装方針の提示

[.claude/rules/frontend.md](../../rules/frontend.md) の規約に従い、実装方針をユーザーに提示する：

- 新規作成するファイルの一覧（ページ、コンポーネント、フック）
- 変更するファイルの一覧
- 再利用する既存コンポーネントの一覧
- RSC（Server Component）と Client Component の使い分け
- 実装の順序（ページ骨組み → API フック → コンポーネント詳細 → スタイル）

ユーザーの承認を待ってから次の手順に進む。

### 5. 要件 .md の事前更新（実装方針の質疑で確定した決定を反映）

手順 4 の方針提示で**ユーザーと対話的に確定した決定**を、実装に入る前に要件 .md に反映する。実装中に決めると要件・コード・テストの 3 者にズレが残るため、**先に要件側を SSoT として確定**させる。

- 反映先：機能要件 .md の該当節（ビジネスルール / 画面 / API / バリデーション 等）、必要なら横断要件（`3-cross-cutting/`）にも追記
- 観測可能な振る舞いとして表せる決定は**受け入れ条件**にも追加
- 実装詳細（依存ライブラリ / 設定値 等）は要件 .md に書かない（SSoT は package.json / 設定ファイル側、→ `_template.md` 冒頭の長期運用原則）

設計判断レベルの決定は ADR 起票も検討する。差分を要件側に反映してから手順 6 の実装に進む。

### 6. 実装

[.claude/rules/frontend.md](../../rules/frontend.md) のコーディング規約に従って実装する：

- ページ固有コンポーネントは `_components/` に配置
- ページ固有フックは `_hooks/` に配置（API 呼び出しは `_hooks/_fetch/`）
- 型は Hey API 生成コードから import（既定の出力先 `apps/web/src/lib/api/generated/`、手書き型は使わない）
- フォームは React Hook Form + Zod、`mode: "onTouched"`
- API 呼び出しはカスタムフックで（`useGet*` / `usePost*` / `usePatch*` / `useDelete*`）
- API エラーは `ApiErrorProvider` で一元処理（個別フックは `error` state を保持）
- `cn()` でクラス名結合、デザインルール（`primary` / `destructive` 等のセマンティックカラー）を遵守
- 認証必須ページは `(authed)` ルートグループ配下に配置
- ファイル名・ディレクトリ名はケバブケース、`index.ts` 禁止

### 7. CodeMirror の使い方（解答画面）

`/problems/:id` の解答画面では：

- `_components/code-editor/` に CodeMirror ラッパーを配置
- `@codemirror/lang-javascript` で TS ハイライト
- `@typescript/vfs` + `@valtown/codemirror-ts` でブラウザ内型診断
- 型診断はサーバ採点の事前フィードバック、最終正誤はサーバが正

### 8. 採点結果ポーリング（TanStack Query）

```tsx
const { data: submission } = useGetSubmission(submissionId, {
  refetchInterval: (query) =>
    query.state.data?.status === 'graded' ? false : 1500,
});
```

### 9. 動作確認

- `mise run web:typecheck` で型エラーなし
- `mise run web:lint` で Biome 警告なし
- ローカルで http://localhost:3000 から手動疎通確認
- レスポンシブ確認（コードエディタ画面はデスクトップ優先）

問題があれば修正してから次の手順に進む。

### 10. 要件 .md の事後追従（動作確認で確定した差分を反映）

動作確認まで通った段階で、実装中に明らかになった以下があれば**ステータス更新の前に**要件 .md へ反映する（実装が SSoT、要件側は契約の鏡として揃える、→ `_template.md` の長期運用原則）：

- **追加された振る舞い / 契約**：画面の挙動・遷移・状態表示の追加、エラーケースの追加 等
- **観測可能な受け入れ条件**：実装中に「これも担保すべき」と気付いた振る舞いを受け入れ条件に追加
- **画面節 / 使用 API の追従**：実装で確定した最終的なパス・コンポーネント構成・使用 API を反映

軽微な追従はこのスキル内で直接更新してよい。差分の規模が大きい場合は `/update-requirements` で対話的に進める。

### 11. ステータス更新

動作確認と要件追従まで完了したら、`docs/requirements/4-features/$ARGUMENTS.md` のステータスチェックボックスのうち**フロントエンド実装完了**にチェックを入れる。

ステータス節の項目構成は `docs/requirements/4-features/_template.md` を踏襲し、機能固有の補足が括弧書きで追加されているケースもある。**項目の追加・削除はしない**（テンプレからの drift を作らない）。テンプレ本体の更新が必要なら `_template.md` を直し、既存機能ファイルにも同じ構造を反映する。
