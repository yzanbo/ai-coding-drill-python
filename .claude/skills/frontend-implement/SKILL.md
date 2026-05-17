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

### 5. 要件 vs 実装の事前判断（方針の質疑で確定した決定を SSoT 側に反映）

手順 4 の方針提示で**ユーザーと対話的に確定した決定**について、**要件 .md を変えるべきか、実装を変えるべきかを工数を無視して純粋なメリット観点から判断**する。要件 .md の追従ありきで進めず、要件の方が正しい場合は実装側を直す前提に立つ。実装中に決めるとズレが残るため、**着手前に SSoT 側を確定**させる。

判断軸（工数は度外視）：

- 要件 .md の記述が UX・業務として正しい → 実装をそれに合わせる
- 既存実装の挙動が UX・業務として正しい / 要件記述が陳腐化している → 要件 .md を更新（ステータス・受け入れ条件含む）
- 双方が並行進化していて整合しない → 正しい側を選んで他方を直す

反映先：

- 要件側を変える場合：機能要件 .md の該当節（ビジネスルール / 画面 / API / バリデーション 等）、必要なら横断要件（`3-cross-cutting/`）にも追記。観測可能な振る舞いは**受け入れ条件**にも追加
- 実装側を変える場合：手順 6 の実装で対応。**後方互換は取らない**（旧コンポーネント / 旧フックの併存禁止、最新状態に合わせて直接修正、→ CLAUDE.md「後方互換性について」）
- 実装詳細（依存ライブラリ / 設定値 等）は要件 .md に書かない（SSoT は package.json / 設定ファイル側、→ `_template.md` 冒頭の長期運用原則）

設計判断レベルの決定は ADR 起票も検討する。判断結果を反映してから手順 6 の実装に進む。

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
- **後方互換は取らない**：旧コンポーネント / 旧フック / re-export shim 等の併存を作らない。型 / API クライアントの再生成で signature が変わった呼び出し元も同じコミット内で最新形に直接修正（→ CLAUDE.md「後方互換性について」）

#### 実装中のコミット粒度

- **適切な粒度で適宜コミット**する（このスキルの実行自体がユーザの明示指示として `git add` / `git commit` を許容する）。ページ骨組み / API フック / 個別コンポーネント / スタイル / 型再生成 など論理単位で区切る
- 1 コミット ≒ 1 レビュー単位を意識：再生成 artifact（`apps/web/src/lib/api/generated/`）と手書きコードは分離するのが望ましい
- コミットメッセージは CLAUDE.md「コミットメッセージ」の規約（`<type>(<scope>): <subject>`、本文必須）に従う。AI 生成文言（`Co-Authored-By` / `Generated with` 等）は入れない
- `git push` / PR 作成はユーザの明示指示があるまで行わない

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

### 10. 要件 vs 実装の事後判断（動作確認で出た差分をどちら側で吸収するか）

動作確認まで通った段階で、実装と要件 .md の間に差分があれば、**ステータス更新の前に**「要件を直す / 実装を直す」を**工数を無視して純粋なメリット観点から判断**して解消する。「実装が SSoT だから要件側を書き換える」と機械的に決めない。

判断軸（工数は度外視）：

- 実装の振る舞いが UX・業務として正しい → 要件 .md を更新（受け入れ条件・画面節・使用 API 節など）
- 要件 .md の記述が UX・業務として正しい / 実装が要件から外れている → 実装を直す（**後方互換 NG、最新状態に合わせて修正**、→ CLAUDE.md「後方互換性について」）
- 実装中に「これも担保すべき」と気付いた振る舞いは、要件側に受け入れ条件として追加する候補

確認対象の差分例：

- **追加された振る舞い / 契約**：画面の挙動・遷移・状態表示、エラーケース 等
- **画面節 / 使用 API の追従**：最終的なパス・コンポーネント構成・使用 API

軽微な追従はこのスキル内で直接更新してよい。差分の規模が大きい場合は `/update-requirements` で対話的に進める。

### 11. ステータス更新

動作確認と要件追従まで完了したら、`docs/requirements/4-features/$ARGUMENTS.md` のステータスチェックボックスのうち**フロントエンド実装完了**にチェックを入れる。

ステータス節の項目構成は `docs/requirements/4-features/_template.md` を踏襲し、機能固有の補足が括弧書きで追加されているケースもある。**項目の追加・削除はしない**（テンプレからの drift を作らない）。テンプレ本体の更新が必要なら `_template.md` を直し、既存機能ファイルにも同じ構造を反映する。
