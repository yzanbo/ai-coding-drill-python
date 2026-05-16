---
paths:
  - "apps/web/src/hooks/**"
  - "apps/web/src/app/**/_hooks/**"
  - "apps/web/src/components/**/_hooks/**"
---

# フロントエンドフック開発ルール

`apps/web/src/hooks/` 配下、各ページの `_hooks/` 配下、および各コンポーネントの `_hooks/` 配下に置く React カスタムフックの実装契約。

ディレクトリ構成・import 方向・命名規則の正本は [frontend.md](./frontend.md)。本ファイルは「フック 1 つ」の作り方に絞った契約で、`frontend.md` と矛盾しない。両者が矛盾した場合は **`frontend.md` を真**とする。

コンポーネント側の対応ルールは [frontend-component.md](./frontend-component.md)。

---

## 1. フックの配置（1 ファイル直置き or 同名フォルダを選べる）

コンポーネントとは違い、フックは **JSX を返さずテスト 1 本で十分なケースが多い**ため、1 ファイル直置きを許容する。内部にサブフックや専用ユーティリティが必要になった時点で、同名フォルダにリネームする。

- ✅ `hooks/use-debounce.ts`（1 ファイルだけ、テストもない）
- ✅ `hooks/use-debounce/use-debounce.ts` + `use-debounce.test.ts`（テストを足したらフォルダ化）
- ✅ `hooks/use-get-problems/use-get-problems.ts` + `_hooks/use-page-params/`（内部フックがある）
- ❌ `hooks/use-debounce/use-debounce.ts`（中身がフック本体だけ、フォルダ化が過剰。最初は直置きで作る）

> **判断基準**：「同フォルダ内に置きたい兄弟ファイル（テスト・型・内部フック）が 1 つでもあるか」。あればフォルダ化、無ければ直置き。

---

## 2. フック名はプロジェクト内でグローバル一意

`apps/web/` 配下のすべてのフック（`src/hooks/`、各ページの `_hooks/`、各コンポーネントの `_hooks/` を含む）は、**同じ名前のフックを 2 つ以上作らない**。識別子（`export const useXxx = ...` の `useXxx`）もファイル名・フォルダ名も含めて重複させない。

理由：

- **IDE の自動補完が曖昧化**：`import { useGetProblems }` で複数候補が出ると、間違った方を import して気づかない事故が起きる
- **grep / リファクタが追えなくなる**：`grep -r "useGetProblems"` で複数のファイルにマッチすると、影響範囲が読めない
- **後で共有層に昇格させる時に名前が衝突する**：ページ専用 `_hooks/use-form-state/` を共有 `hooks/use-form-state/` に上げようとしても、同名の別フックがあると衝突する

### 重複しそうな時の付け方

ドメイン語彙・対象・粒度を **フック名の側に**寄せる：

- ❌ ページ A の `_hooks/use-form-state/` とページ B の `_hooks/use-form-state/` を両方作る
- ✅ ページ A は `_hooks/use-login-form-state/`、ページ B は `_hooks/use-answer-form-state/`
- ❌ `hooks/use-get-problems/`（問題一覧用）と `hooks/use-get-problems/`（履歴用）（同名フォルダ衝突）
- ✅ `hooks/use-get-problems/`（問題一覧用）と `hooks/use-get-problem-history/`（履歴用）

### 既存名のチェック方法

新しいフックを作る前に：

```bash
# フック識別子（camelCase）の重複チェック
grep -r "export const useFoo " apps/web/src/

# ファイル名 / フォルダ名（kebab-case）の重複チェック
find apps/web/src -name "use-foo*"
```

両方とも空（または自分自身のみ）であることを確認してから作る。

---

## 3. フックフォルダの中身（フォルダ化した時）

`<name>/` フォルダ内のファイル / サブフォルダ：

| ファイル / フォルダ | 役目 | 必須か |
|---|---|---|
| `<name>.ts` | フック本体 | 必須 |
| `<name>.test.ts` | Vitest + Testing Library（`renderHook`）のテスト | ロジック（条件分岐 / 副作用 / 状態）がある時は必須 |
| `types.ts` | このフックが返す型・受け取る型を切り出す時 | 任意（短いものは `<name>.ts` 冒頭で十分） |
| `_hooks/` | このフックだけが使う子フック | 任意。中身は再帰的に本規約が適用される |
| `_utils/` | このフックだけが使うユーティリティ（純粋関数） | 任意 |
| `_constants/` | このフックだけが使う定数 | 任意 |

> `.stories.ts` は無い（フックは画面を描画しないため）。表示の確認はフックを呼び出すコンポーネント側の `.stories.tsx` で行う。

---

## 4. フック本体（`<name>.ts`）の書き方

```ts
import { useState } from "react";
import { getProblems } from "@/__generated__/api/client";

// UseGetProblemsReturn: フックが返す値の形。
//   呼び出し側はこの型を頼りに「何が取れるか」を把握する。
type UseGetProblemsReturn = {
  problems: ProblemType[];
  isLoading: boolean;
  error: Error | null;
};

// useGetProblems: 問題一覧を取得するフック。
//   内部で __generated__/api/client の getProblems を呼ぶだけ。
//   ページ側はこのフックの戻り値を表示するだけにする。
export const useGetProblems = (): UseGetProblemsReturn => {
  // isLoading の初期値: fetch 実行条件を満たすなら true で開始する
  //   （表示直後の「データ無し」状態を空表示でなくスケルトン等に倒せる）
  const [isLoading, setIsLoading] = useState(true);
  // ...
};
```

ルール：

- **名前付き export**（`export const useXxx = ...`）。`export default` は使わない（grep / 自動補完しやすさのため）
- **アロー関数で宣言**（プロジェクト内で統一）
- **戻り値型は `UseXxxReturn`**（[frontend.md §命名規則](./frontend.md)）
- **API 通信を伴うフックは `__generated__/api/` の HTTP クライアントを内部で呼ぶ**。手書きの `fetch` / `axios` は使わない（[ADR 0006](../../docs/adr/0006-json-schema-as-single-source-of-truth.md)）
- **`useGet*` フックの `isLoading` 初期値は `true`**（fetch 実行条件を満たす場合）。`false` 開始だと表示直後の「データ無し」状態を空表示として描画してしまう
- **エラーは戻り値の `error` フィールドに保持**して呼び出し側に渡す（フォームのインラインエラー表示等に使う、[frontend.md §エラーハンドリング](./frontend.md)）

### 命名パターン

| 種類 | 接頭辞 | 例 |
|---|---|---|
| データ取得（GET） | `useGet*` | `useGetProblems` / `useGetCurrentUser` |
| データ作成（POST） | `usePost*` | `usePostSubmission` |
| データ更新（PATCH / PUT） | `usePatch*` / `usePut*` | `usePatchProfile` |
| データ削除（DELETE） | `useDelete*` | `useDeleteSubmission` |
| UI 状態・タイミング制御 | `use*` | `useDebounce` / `useHoverPopover` |

---

## 5. テスト（`<name>.test.ts`）

- Vitest + Testing Library の `renderHook` を使う
- API モックは MSW（生成物のクライアントが叩く URL を握る）
- ファイル名は `<name>.test.ts`、配置はコロケーション（フック本体と同じフォルダ）
- テスト名・docstring は日本語：

```ts
import { renderHook, waitFor } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { useGetProblems } from "./use-get-problems";

describe("useGetProblems", () => {
  it("正常系: 問題一覧を返す", async () => {
    const { result } = renderHook(() => useGetProblems());
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.problems).toHaveLength(3);
  });
});
```

- 非同期は `waitFor` で待つ
- 各テストは独立させる（MSW のハンドラはテストごとに reset）

---

## 6. やってはいけないこと

- ❌ `hooks/` から `@/components/...` を import（フックは JSX を返さない、[frontend.md §レイヤ間の import 方向](./frontend.md)）
- ❌ 同名のフックを 2 つ以上作る（本規約 §2 違反、`grep` / IDE 補完が壊れる）
- ❌ `export default useFoo;`（名前付き export を使う、本規約 §4）
- ❌ 条件分岐の中で React のフック（`useState` / `useEffect` 等）を呼ぶ（React のルール違反）
- ❌ サーバー状態（API レスポンス）を `useState` で長期保持する（TanStack Query / SWR 等のサーバー状態管理に任せる）
- ❌ 手書きの `fetch` / `axios` を使う（`__generated__/api/` の生成クライアントを使う、[ADR 0006](../../docs/adr/0006-json-schema-as-single-source-of-truth.md)）
- ❌ 1 ページでしか使わないフックを `src/hooks/` に置く（コロケーションを使う、`app/.../_hooks/`）

---

## 関連

- ディレクトリ全体規約・import 方向・命名規則：[.claude/rules/frontend.md](./frontend.md)
- コンポーネント側の対応ルール（フォルダ化必須・グローバル一意）：[.claude/rules/frontend-component.md](./frontend-component.md)
- ルールファイルの書き方そのもの：[.claude/rules/claude-rules-authoring.md](./claude-rules-authoring.md)
- 人間向けレイヤ概要：[apps/web/src/hooks/README.md](../../apps/web/src/hooks/README.md)
