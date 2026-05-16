---
paths:
  - "apps/web/src/components/**"
  - "apps/web/src/app/**/_components/**"
---

# フロントエンドコンポーネント開発ルール

`apps/web/src/components/{ui,parts,providers}/` 配下と、各ページの `_components/` 配下、および各コンポーネントの内部 `_components/` 配下に置く React コンポーネントの実装契約。

ディレクトリ構成・import 方向・命名規則の正本は [frontend.md](./frontend.md)。本ファイルは「コンポーネント 1 つ」の作り方に絞った契約で、`frontend.md` と矛盾しない。両者が矛盾した場合は **`frontend.md` を真**とする。

対応する hook 側のルールは [frontend-hooks.md](./frontend-hooks.md)。

## 適用範囲（重要：場所による差分）

本ルールは「コンポーネント本体・命名・フォルダ化・CSS」を**共通**で扱う。違いは **テスト / Storybook 同居の期待度**だけで、それは下表のとおり：

| 配置場所 | フォルダ化（§1） | 名前のグローバル一意性（§2） | テスト同居（§5） | Storybook 同居（§6） |
|---|---|---|---|---|
| `apps/web/src/components/{ui,parts,providers}/<name>/`（共有コンポーネント） | **必須** | **必須** | UI ロジックがあれば **必須** | `parts/` は **推奨**、`ui/` `providers/` は任意 |
| `app/.../page-dir/_components/<name>/`（ページローカル） | **必須** | **必須** | **任意**（書いてもよい、無くてもよい） | **任意**（基本不要） |
| `<component>/<name>/_components/<sub>/`（内部部品） | **必須** | **必須** | **任意** | **任意** |

「**フォルダ化と名前一意は場所に関わらず必須**」が原則で、テスト・Storybook の同居期待度だけが共有コンポーネント側で強くなる。

---

## 1. 全コンポーネントはフォルダで包む

`apps/web/src/` 配下のすべての場所（`components/{ui,parts,providers}/`、各ページの `_components/`、内部 `_components/`）に置く **全てのコンポーネントは、同名フォルダで包む**。

- ✅ `components/ui/button/button.tsx`
- ✅ `app/(authed)/problems/[id]/_components/code-editor/code-editor.tsx`
- ❌ `components/ui/button.tsx`（単一ファイル配置禁止）
- ❌ `app/(authed)/problems/[id]/_components/code-editor.tsx`（単一ファイル配置禁止）

理由：テストコード（`button.test.tsx`）・Storybook カタログ（`button.stories.tsx`）・必要に応じて内部の `_components/` `_hooks/` を、**コンポーネント本体と同じ単位で grep・移動・削除できる**ようにするため。`_components/` 配下では test / story は任意だが、**将来追加される可能性に備えてフォルダで包む**点は共通。

### shadcn/ui の取り扱い

`pnpm dlx shadcn@latest add <name>` の既定出力は `components/ui/<name>.tsx`（単一ファイル）。これは本規約に反するため、生成直後にフォルダ形式へリネームする：

```bash
mkdir -p apps/web/src/components/ui/<name>
mv apps/web/src/components/ui/<name>.tsx apps/web/src/components/ui/<name>/<name>.tsx
```

`shadcn add --overwrite <name>` で再生成した時も同じリネーム手順を踏む。

### 例外

なし。**シンプルな表示専用コンポーネントでも、テスト・ストーリーが将来追加される可能性があるため必ずフォルダで包む**。

---

## 2. コンポーネント名はプロジェクト内でグローバル一意

`apps/web/` 配下のすべてのコンポーネント（`components/{ui,parts,providers}/` 配下と、各ページの `_components/` 配下を含む）は、**同じ名前のコンポーネントを 2 つ以上作らない**。識別子（`export const Xxx = ...` の `Xxx`）もフォルダ名も含めて重複させない。

理由：

- **Storybook の `meta.title` 衝突**：`title: "ui/Button"` と `title: "parts/Button"` のように階層は違っても、サイドバーに同名ノードが並ぶと選びにくい
- **IDE の自動補完が曖昧化**：`import { Button }` で複数候補が出ると、間違った方を import して気づかない事故が起きる
- **grep / リファクタが追えなくなる**：`grep -r "ProblemCard"` で複数のファイルにマッチすると、移動・削除の影響範囲が読めない

### 重複しそうな時の付け方

ドメイン語彙や用途を **コンポーネント名の側に**寄せる：

- ❌ `ui/button/button.tsx` と `parts/button/button.tsx` を両方作る
- ✅ `ui/button/button.tsx`（汎用）と `parts/submit-button/submit-button.tsx`（解答送信専用）
- ❌ `parts/problem-card/problem-card.tsx` と `parts/history/problem-card/problem-card.tsx` を作る
- ✅ `parts/problem-card/problem-card.tsx`（問題一覧用）と `parts/history-problem-card/history-problem-card.tsx`（履歴用）

ページ固有の `_components/` 内でも同じ。`app/(authed)/problems/[id]/_components/code-editor/` と `app/(authed)/sandbox/_components/code-editor/` を両方作るのは禁止。片方を `editor` 等に変えるか、共有部品として `src/components/parts/code-editor/` に昇格させて 1 つに揃える。

### 既存名のチェック方法

新しいコンポーネントを作る前に：

```bash
# コンポーネント名（PascalCase）の重複チェック
grep -r "export const Foo " apps/web/src/

# フォルダ名（kebab-case）の重複チェック
find apps/web/src -type d -name "foo"
```

両方とも空（または自分自身のみ）であることを確認してから作る。

---

## 3. コンポーネントフォルダの中身

`<name>/` フォルダ内のファイル / サブフォルダ：

| ファイル / フォルダ | 役目 | `src/components/` での扱い | `_components/`（ページ・内部）での扱い |
|---|---|---|---|
| `<name>.tsx` | コンポーネント本体 | 必須 | 必須 |
| `<name>.test.tsx` | Vitest + Testing Library のテスト | UI ロジックがあれば **必須** | 任意 |
| `<name>.stories.tsx` | Storybook の状態カタログ | `parts/` は推奨、`ui/` `providers/` は任意 | 任意（基本不要） |
| `types.ts` | このコンポーネント専用の型を切り出す時 | 任意（短いものは `<name>.tsx` 冒頭で十分） | 任意 |
| `_components/` | このコンポーネントだけが使う子部品 | 任意。中身は再帰的に本規約が適用される | 任意。中身は再帰的に本規約が適用される |
| `_hooks/` | このコンポーネントだけが使うフック | 任意 | 任意 |
| `_constants/` | このコンポーネントだけが使う定数 | 任意 | 任意 |
| `_utils/` | このコンポーネントだけが使うユーティリティ | 任意 | 任意 |

> 内側の `_components/` `_hooks/` 等の再帰スコープルール（**親からしか参照できない**）は [frontend.md §コロケーション原則](./frontend.md) を参照。

---

## 4. コンポーネント本体（`<name>.tsx`）の書き方

```tsx
// "use client": ユーザー操作（クリック・入力）を扱うのでブラウザで動かす指定。
//   表示だけで操作が無いなら付けない（Server Component のままにする）。
"use client";

// ProblemCardProps: 受け取る入力の形。型は同じファイル先頭で宣言する。
type ProblemCardProps = {
  title: string;
  difficulty: "easy" | "medium" | "hard";
  onClick?: () => void;
};

// ProblemCard: 問題カードを表示する部品。
//   props で受け取った値を表示するだけ。データ取得は呼び出し側の hook で行う。
export const ProblemCard = ({ title, difficulty, onClick }: ProblemCardProps) => {
  return (
    <button type="button" onClick={onClick}>
      <h3>{title}</h3>
      <span>{difficulty}</span>
    </button>
  );
};
```

ルール：

- **名前付き export** を使う（`export const ComponentName = ...`）。`export default` は使わない（grep / 自動補完しやすさのため）
- **アロー関数で宣言**（プロジェクト内で統一）
- **props 型はコンポーネント名 + Props**（[frontend.md §命名規則](./frontend.md)）
- **props の型はファイル冒頭**で宣言する。`types.ts` への切り出しは、複数の関連型がある時だけ

---

## 5. テスト（`<name>.test.tsx`）

> **適用範囲**：主に `src/components/` 配下の共有コンポーネント。`app/.../_components/` および
> `<component>/_components/` のページローカル / 内部部品では任意（書いても書かなくても可）。

- Vitest + Testing Library + MSW を使う（[frontend.md §テスト](./frontend.md)）
- ファイル名は `<name>.test.tsx`、配置はコロケーション（コンポーネント本体と同じフォルダ）
- テスト名・docstring は日本語：

```tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { ProblemCard } from "./problem-card";

describe("ProblemCard", () => {
  it("タイトルが表示される", () => {
    render(<ProblemCard title="二分探索" difficulty="easy" />);
    expect(screen.getByText("二分探索")).toBeInTheDocument();
  });
});
```

- 結合テストで API を叩く時は MSW でモック
- 操作の発火は `userEvent`（`fireEvent` は使わない）
- 非同期は `findBy*` / `waitFor` で待つ

---

## 6. Storybook（`<name>.stories.tsx`）

> **適用範囲**：主に `src/components/parts/` 配下の共有コンポーネント（推奨）。`src/components/ui/`
> （shadcn 由来）と `src/components/providers/` は任意。`app/.../_components/` および
> `<component>/_components/` のページローカル / 内部部品では基本不要（必要時のみ書く）。

各状態（loading / error / 通常 / 長文 / 空 等）を 1 story に分けて並べる。

```tsx
import type { Meta, StoryObj } from "@storybook/react";
import { ProblemCard } from "./problem-card";

const meta = {
  // title: Storybook サイドバーで表示される階層パス。「フォルダ階層 / コンポーネント名」の形。
  title: "parts/ProblemCard",
  component: ProblemCard,
} satisfies Meta<typeof ProblemCard>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Easy: Story = { args: { title: "二分探索", difficulty: "easy" } };
export const Hard: Story = { args: { title: "編集距離", difficulty: "hard" } };
```

ルール：

- **`meta.title`** は「フォルダ階層 / コンポーネント名」の形（例：`ui/Button` / `parts/ProblemCard` / `providers/ThemeProvider`）
- **全 props を網羅しない**。「画面で違いが見える代表ケース」を 2〜5 個
- **export 名は意味のあるラベル**（`Easy` / `Hard` / `WithIcon` / `Disabled`）。`Story1` `Story2` のような番号付けは禁止

> Storybook は R0 では未導入。導入は別フェーズで決定する（R2 以降目安）。本ファイルの規約は導入時に従う前提として書いておく。導入前は `<name>.stories.tsx` を作らなくてよい。

---

## 7. CSS / className

- Tailwind の class 文字列を直接書く
- 条件付き class / 結合は [`cn()`](../../apps/web/src/lib/) ヘルパー（shadcn 由来）を使う：
  ```tsx
  <button className={cn("px-4 py-2", isPrimary && "bg-primary")}>
  ```
- 同じクラス文字列が同コンポーネント内で複数回現れる時は、ファイル冒頭で定数化：
  ```tsx
  const buttonBaseClass = "px-4 py-2 rounded-lg transition-colors duration-200";
  ```

---

## 8. やってはいけないこと

- ❌ `components/ui/button.tsx`（フォルダ化していない、本規約 §1 違反）
- ❌ 同名のコンポーネントを 2 つ以上作る（本規約 §2 違反、`grep` / IDE 補完 / Storybook が壊れる）
- ❌ `export default ProblemCard;`（名前付き export を使う、本規約 §4）
- ❌ Storybook の story export を `Story1` / `Story2` 等の番号付けで書く（意味のあるラベルにする、本規約 §6）
- ❌ コンポーネント内で `useState` を使って **サーバー状態**（API レスポンス）を保持する（TanStack Query 等に任せる、[frontend.md](./frontend.md)）
- ❌ Tailwind の class 文字列を `lib/styles/` に切り出す（`cn()` で十分、[lib/styles/](../../apps/web/src/lib/styles/) は CodeMirror テーマ等の構造化スタイル専用）
- ❌ テストで `fireEvent` を使う（`userEvent` を使う）

---

## 関連

- ディレクトリ全体規約・import 方向・命名規則：[.claude/rules/frontend.md](./frontend.md)
- ルールファイルの書き方そのもの：[.claude/rules/claude-rules-authoring.md](./claude-rules-authoring.md)
- 人間向けレイヤ概要：[apps/web/src/components/README.md](../../apps/web/src/components/README.md)
