# hooks/

## hooks/ とは何か

複数のページで使い回す **カスタムフック**（名前が `use-` で始まる関数）の置き場です。
React の状態（`useState`）や副作用（`useEffect`）を内側で使う、画面と裏側のロジックを繋ぐ部品。

ページ 1 つでしか使わないフックはここに置きません（それは `app/.../page-dir/_hooks/` に置く、
コロケーション、→ [frontend.md](../../../../.claude/rules/frontend.md)）。

代表例：

- **データ取得系**：`use-get-problems/`、`use-get-current-user/`（API を叩いて結果を保持）
- **UI 状態系**：`use-debounce/`、`use-hover-popover/`（複数画面で共通する操作・タイミング制御）
- **共通ガード系**：`use-leave-confirm-dialog/`（未保存変更の離脱確認）

## 役目

- React のフック規約（フック呼び出しは関数本体の先頭・条件分岐の外）を守った関数を提供する
- API 通信を伴うフックは `__generated__/api/` の HTTP クライアントを内側で呼ぶ
  （[ADR 0006](../../../../docs/adr/0006-json-schema-as-single-source-of-truth.md)）
- JSX は返さない（部品は `components/`、フックは値とハンドラだけを返す）

## ファイル配置

実装契約の正本は [.claude/rules/frontend-hooks.md](../../../../.claude/rules/frontend-hooks.md)。要点：

- **1 ファイルだけのフック**：直接 `.ts` を置いてよい（`hooks/use-debounce.ts`）
- **フォルダ化する場合**：同名フォルダ内に同名ファイル（`hooks/use-get-problems/use-get-problems.ts`）
  - 内部にテスト（`use-get-problems.test.ts`）や下位フック（`_hooks/`）を置けるようになる
- **判断基準**：「同フォルダ内に置きたい兄弟ファイル（テスト・型・内部フック）が 1 つでもあるか」。あればフォルダ化、無ければ直置き
- **戻り値の型名**：`UseXxxReturn`（例：`UseGetProblemsReturn`）

## フック名はプロジェクト内でグローバル一意

`apps/web/` 配下のすべてのフック（`src/hooks/`、各ページの `_hooks/`、各コンポーネントの `_hooks/` を含む）は **同じ名前を 2 つ以上作らない**。重複しそうな時はドメイン語彙・対象・粒度をフック名の側に寄せる（`use-form-state` → `use-login-form-state` / `use-answer-form-state`）。詳細は [frontend-hooks.md §2](../../../../.claude/rules/frontend-hooks.md)。

## 命名規則

| 種類 | 接頭辞 | 例 |
|---|---|---|
| データ取得（GET） | `useGet*` | `useGetProblems` |
| データ作成（POST） | `usePost*` | `usePostSubmission` |
| データ更新（PATCH/PUT） | `usePatch*` / `usePut*` | `usePatchProfile` |
| データ削除（DELETE） | `useDelete*` | `useDeleteSubmission` |
| UI 状態 | `use*` | `useDebounce` / `useHoverPopover` |

ファイル名・フォルダ名はケバブケース（`use-get-problems.ts` / `use-get-problems/`）。
camelCase は関数名 / 型名にだけ使う。

## やってはいけないこと

- ❌ `hooks/` から `components/` を import（フックは JSX を返さない）
- ❌ React の `useState` などをフックの中で **条件分岐の中**で呼ぶ（React のルール違反）
- ❌ ページ 1 つでしか使わないフックを置く（`app/.../_hooks/` を使う）
- ❌ `index.ts` で再エクスポート（バレル禁止）

詳しい配置・命名・import 方向は [.claude/rules/frontend.md](../../../../.claude/rules/frontend.md) の **§コロケーション原則**・**§命名規則（実装契約）**・**§API クライアント**。
