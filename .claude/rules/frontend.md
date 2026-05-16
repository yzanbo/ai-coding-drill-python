---
paths:
  - "apps/web/**/*"
---

# フロントエンド開発ルール（Next.js + CodeMirror）

Next.js 16+（App Router）+ React + TypeScript のフロントエンド。

## 技術スタック

- Next.js 16+（App Router、フロント専用、API Route は最小限）
- React + TypeScript（strict）
- Tailwind CSS + shadcn/ui
- React Hook Form + Zod（フォームバリデーション）
- TanStack Query（Client Component 側のサーバー状態管理）
- **CodeMirror 6**（コード入力エディタ、`@typescript/vfs` でブラウザ内型診断）
- date-fns（日付操作、日本語ロケール）
- Biome（lint / format）
- Vitest + Testing Library（テスト）

詳細な選定理由は [05-runtime-stack.md](../../docs/requirements/2-foundation/05-runtime-stack.md#フロントエンド) と [ADR 0015](../../docs/adr/0015-codemirror-over-monaco.md)。

## ディレクトリ構成（実装契約）

機能別フラット構成。ファイル配置・import 方向は本セクションが SSoT で、R1 以降の機能実装は
この契約に従う。人間向け概要は [apps/web/src/README.md](../../apps/web/src/README.md) を参照。

```
apps/web/src/
├── app/                             # Next.js App Router（URL とファイル配置を 1:1 にする箱）
│   └── (routing)/
│       ├── (public)/                # 認証不要（ランディング、ログイン）
│       │   ├── page.tsx             # /
│       │   └── login/
│       │       └── page.tsx         # /login
│       └── (authed)/                # 認証必須（layout.tsx でガード）
│           ├── problems/
│           │   ├── page.tsx         # /problems（一覧）
│           │   └── [id]/
│           │       ├── page.tsx     # /problems/:id（解答画面）
│           │       ├── _components/ # ページ固有部品（コロケーション）
│           │       └── _hooks/      # ページ固有フック（コロケーション）
│           └── history/
│               └── page.tsx         # /history（学習履歴）
├── components/                      # 複数ページで使い回す画面部品
│   ├── ui/                          # shadcn/ui + 汎用ラッパ（ドメイン語彙なし、lint 切る）
│   ├── parts/                       # ドメイン語彙を含む再利用ブロック（problem-card 等）
│   └── providers/                   # React の Provider 群（QueryClient / ApiError / Theme）
├── hooks/                           # 複数ページで使い回すカスタムフック（use-*）
├── lib/                             # React / Next.js 非依存の素のロジック・設定
│   ├── api/                         # 手書きの API ラッパ（error interceptor 等。生成物は __generated__/api/）
│   ├── validation/                  # Zod スキーマ（フォーム入力検証）
│   ├── utils/                       # 汎用関数（純粋関数、テスト容易）
│   ├── constants/                   # サイト全体の定数（ルートパス / 列挙ラベル / 既定値）
│   ├── styles/                      # CodeMirror テーマ等、Tailwind で表現できない構造化スタイル
│   ├── shared-query/                # TanStack Query の QueryClient + 既定 options
│   └── utils.ts                     # cn() ヘルパー（lib 直下の単発ファイル、shadcn 規約）
└── __generated__/                   # 自動生成物（人手で編集しない、lint / knip / biome で除外）
    └── api/                         # Hey API output（apps/api/openapi.json → TS / Zod / HTTP クライアント、ADR 0006）
```

> **ページ固有 vs 共有の境界**：1 ページでしか使わない部品・フックは `app/.../page-dir/_components/`
> `_hooks/` 等にコロケーションで置く。**複数ページに昇格して初めて** `src/{components,hooks,lib}/` に
> 引き上げる。先取りで `src/components/` に置かない（YAGNI）。
>
> **コンポーネントは必ずフォルダで包む + 名前はプロジェクト内でグローバル一意**：
> `components/{ui,parts,providers}/` 配下と各ページの `_components/` 配下の
> **全コンポーネントは同名フォルダ + 同名ファイル**で配置する（`components/ui/button/button.tsx`）。
> テスト（`button.test.tsx`）・Storybook（`button.stories.tsx`）をコロケーションで同居させるため。
> また、`apps/web/` 配下のすべてのコンポーネント名は**重複させない**（IDE 補完・grep 容易性のため）。
> 詳細は [.claude/rules/frontend-component.md](./frontend-component.md)。
>
> **フックも名前はプロジェクト内でグローバル一意**：`src/hooks/` / 各ページの `_hooks/` /
> 各コンポーネントの `_hooks/` を含めて、**同名のフックは作らない**。フックの配置は
> 1 ファイル直置きとフォルダ化を選べる（テスト・内部フックが要るならフォルダ化）。
> 詳細は [.claude/rules/frontend-hooks.md](./frontend-hooks.md)。

### レイヤ間の import 方向

新規実装時、各レイヤから何を import してよいかを下記の表で固定する。

#### 各レイヤの import 可 / 禁止

| レイヤ | import してよい | import 禁止 |
|---|---|---|
| `app/` | `components` / `hooks` / `lib` / `__generated__` | （上位なし） |
| `components/` | 他の `components` / `hooks` / `lib` / `__generated__` | `app` |
| `hooks/` | 他の `hooks` / `lib` / `__generated__` | `app` / `components` |
| `lib/` | 他の `lib` / `__generated__` | `app` / `components` / `hooks`（React 非依存に保つ） |
| `__generated__/` | （何も import しない、終端） | 全て |

#### 補足ルール

- **依存は一方向**：A → B かつ B → A を作らない。`components/parts/` 内・`hooks/` 内など同レイヤの兄弟も同じ
- **`__generated__/` を終端に保つ**：手書きの interceptor / エラー解釈は `lib/api/` 側に置き、生成物には手を入れない（[ADR 0006](../../docs/adr/0006-json-schema-as-single-source-of-truth.md)）
- **`lib/` を React 非依存に保つ**：`useState` / `useEffect` / JSX を含む実装は `hooks/` か `components/` に置く（lib/ は Node 単体テストでも回せる純粋ロジックに限定）
- **ページ固有は `app/.../_components/` 等**：コロケーション、複数ページで使うようになってから `src/components/` に昇格する
- **`index.ts` 再エクスポート禁止**：バレル禁止（[ADR は無いがプロジェクト規約]）。例外は `__generated__/api/` 配下（Hey API が自動で生成するため）

#### OK / NG 例

```typescript
// ✅ OK: page.tsx が下位レイヤを使う
// src/app/(authed)/problems/page.tsx
import { ProblemCard } from "@/components/parts/problem-card/problem-card";
import { useGetProblems } from "@/hooks/use-get-problems/use-get-problems";
import { DIFFICULTY_LABELS } from "@/lib/constants/difficulty-labels";
```

```typescript
// ✅ OK: 共有フックが lib と __generated__ を使う
// src/hooks/use-get-problems/use-get-problems.ts
import { getProblems } from "@/__generated__/api/client";
import { interceptApiError } from "@/lib/api/api-error-interceptor";
```

```typescript
// ❌ NG: hooks が components を import（フックは JSX を返さない）
// src/hooks/use-something/use-something.ts
import { Button } from "@/components/ui/button";    // NG
```

```typescript
// ❌ NG: lib が React に依存（lib は素のロジックに保つ）
// src/lib/utils/something.ts
import { useState } from "react";                    // NG（hooks/ へ移す）
import { ProblemCard } from "@/components/parts/...";// NG（lib は components を呼ばない）
```

```typescript
// ❌ NG: __generated__/ から src/ を import（終端違反）
// src/__generated__/api/client.ts（人手で改変しない前提だが、念のため）
import { interceptApiError } from "@/lib/api/api-error-interceptor";  // NG（lib/api/ 側で被せる）
```

```typescript
// ❌ NG: バレル経由の import
// src/components/parts/index.ts                     // ファイル自体を作らない
import { ProblemCard } from "@/components/parts";    // NG（具体パスを書く）
import { ProblemCard } from "@/components/parts/problem-card/problem-card";  // OK
```

### 命名規則（実装契約）

| 種別 | 命名パターン | 例 |
|---|---|---|
| ファイル名・ディレクトリ名 | ケバブケース | `use-get-problems.ts` / `problem-card/` |
| React コンポーネント | PascalCase | `ProblemCard` / `DifficultyBadge` |
| 関数・変数 | camelCase | `formatDate` / `queryClient` |
| 定数 | SCREAMING_SNAKE_CASE | `DIFFICULTY_LABELS` / `MAX_PAGE_SIZE` |
| 一般的な型 | `◯◯Type` | `ProblemType` / `SubmissionType` |
| コンポーネントの props | `◯◯Props` | `ProblemCardProps` / `ButtonProps` |
| フックの戻り値型 | `◯◯Return` | `UseGetProblemsReturn` |
| RHF フォームの値型 | `◯◯FormValues` | `LoginFormValues` |
| Zod スキーマ変数 | `<formName>Schema` | `loginFormSchema` |
| フック名（GET/POST/PATCH/DELETE） | `useGet*` / `usePost*` / `usePatch*` / `useDelete*` | `useGetProblems` / `usePostSubmission` |
| フック名（UI 状態） | `use*` | `useDebounce` / `useHoverPopover` |

## ルーティング規約

- ルートグループ `(名前)` は URL 構造に影響しない
- `(routing)` — 全ルートの共通親
- `(authed)` — `layout.tsx` で認証チェック
- `(public)` — 認証不要ページ
- ページ固有コンポーネント：`_components/` に配置（コロケーション）
- ページ固有フック：`_hooks/` に配置

## 画面構成（MVP）

| パス | 役割 | 認証 |
|---|---|---|
| `/` | ランディング | 不要 |
| `/login` | GitHub OAuth ログイン | 不要 |
| `/problems` | 問題一覧（カテゴリ・難易度フィルタ） | 推奨 |
| `/problems/:id` | 問題詳細・解答画面（CodeMirror、採点ポーリング） | 必須 |
| `/history` | 学習履歴・正答率 | 必須 |

→ 詳細は [01-overview.md](../../docs/requirements/1-vision/01-overview.md)

## デスクトップ優先方針

- レスポンシブ対応（Tailwind の `sm:` `md:` `lg:` を使用）
- ただし**コードエディタ画面（`/problems/:id`）はデスクトップ優先**
- モバイルでは「問題閲覧のみ可能、解答送信はデスクトップで」を表示

## RSC と Client Component の使い分け

- **一覧・詳細の単純取得は RSC（Server Components）で直接 `fetch`**
- **採点結果ポーリング・ジョブステータス監視・解答送信は Client Component + TanStack Query**
- 理由：データ取得方法を役割で分け、TanStack Query を「非同期ジョブ周り」に集中させる（→ [05-runtime-stack.md](../../docs/requirements/2-foundation/05-runtime-stack.md#フロントエンド)）

## コマンド（mise）

タスク命名は `<scope>:<sub>:<verb>` 階層コロン形式（→ [ADR 0039](../../docs/adr/0039-mise-for-task-runner-and-tool-versions.md)）：

```bash
mise run web:dev          # next dev
mise run web:test         # vitest
mise run web:lint         # biome check
mise run web:format       # biome check --write
mise run web:typecheck    # tsc --noEmit
mise run web:knip         # 未使用検出
mise run web:syncpack     # package.json 整合性
mise run web:types-gen    # Hey API で OpenAPI から TS / Zod / HTTP クライアント生成
mise run web:e2e          # Playwright E2E
```

`apps/web/` 配下では pnpm を直接使う（pnpm workspaces 単一構成、→ [ADR 0036](../../docs/adr/0036-frontend-monorepo-pnpm-only.md)）。`mise` 経由が標準だが必要に応じて `cd apps/web && pnpm dev` 等も可。

## 環境変数

- `NEXT_PUBLIC_API_URL`：FastAPI の URL（例：`http://localhost:8000`）
- public 変数は `NEXT_PUBLIC_` プレフィックス必須

## CodeMirror 6 の使い方

- `@codemirror/lang-javascript`（TypeScript ハイライト）
- `@typescript/vfs` + `@valtown/codemirror-ts`（ブラウザ内型診断・補完）
- 採点はサーバ側（Worker のサンドボックス内 Vitest）が正、ブラウザの型診断は UX 向上のための即時フィードバック
- 解答コンポーネントはコロケーションで `app/(authed)/problems/[id]/_components/code-editor/` に配置

## importパスの規則

境界は **`page.tsx` が存在するディレクトリ**で決まる。

- **`@/` エイリアス**：以下の場合に使用する（`@/*` → `src/*`、定義は [tsconfig.json](../../apps/web/tsconfig.json) の `paths`）
  - `src/` 直下の共通リソース（`components/`, `hooks/`, `lib/`, `__generated__/`）
  - 自分の `page.tsx` ディレクトリの外にあるリソース
  - 例：`import { Button } from "@/components/ui/button"`
  - 例：`import { getProblems } from "@/__generated__/api/client"`
- **相対パス**：自分の `page.tsx` ディレクトリ内のリソースに使用する
  - 対象：同じ page 配下の `_components/`, `_hooks/`, `_constants/` 等
  - 例：`import { CodeEditor } from "./_components/code-editor/code-editor"`

## フォームバリデーション

- React Hook Form + Zod + zodResolver
- バリデーションの発火タイミング：`mode: "onTouched"`（初回 blur で発火、以降リアルタイム）

```typescript
const form = useForm({
  resolver: zodResolver(schema),
  mode: "onTouched",
});
```

## コーディングルール

> ファイル名・ディレクトリ名・型名・フック名・`index.ts` 禁止・再エクスポート禁止は **§ディレクトリ構成（実装契約）**
> および同セクション配下の **§命名規則** が SSoT。ここではそれ以外の運用上の細則のみを書く。

- IDE の問題タブにエラー・警告があれば適宜修正
- lint・型チェック・knip 等のコマンド実行時に警告が出たら、即時修正（警告を放置しない）
- 条件付きクラスや複数のクラス変数を結合する場合は `cn()` を使用する（[lib/utils.ts](../../apps/web/src/lib/) の `cn()`）
- コンポーネント内で同じクラス文字列が複数回使われる場合は、コンポーネント内に定数として定義する
- `useGet*` フックの `isLoading` 初期値は、fetch 実行条件を満たす場合に `true` とする

## デザインルール

- サイト全体でデザインの統一性を重視
- 新規コンポーネント作成時は既存の類似コンポーネントのスタイルを参照
- 統一対象：
  - 枠線：`border-border`
  - 影：`shadow-sm`（通常）, `shadow-md`（ホバー）, `shadow-lg`（モーダル）
  - 角丸：`rounded-lg`（小）, `rounded-xl`（カード）
  - トランジション：`transition-colors duration-200`、`transition-all duration-200`
  - フォントサイズ：`text-xs` / `text-sm` / `text-base` / `text-lg`〜`text-3xl`
- 色の使い分け（セマンティックカラー、Tailwind 生カラーは原則不使用）：
  - `primary` — ブランド・主要アクション
  - `destructive` — 削除・エラー
  - `muted` — 無効・補足
  - `border` — 枠線
  - `ring` — フォーカス

## API クライアント

### 認証

- セッション Cookie（HttpOnly + Secure + SameSite=Lax）
- 全リクエストに `credentials: "include"` を付ける
- 401 レスポンスで `/login` へリダイレクト

### API 通信

- API 通信は必ずカスタムフック（`_hooks/_fetch/`）に切り出す。コンポーネントから直接 `fetch` しない
- フック名は HTTP メソッド対応：`useGet*` / `usePost*` / `usePatch*` / `useDelete*`
- 型・Zod スキーマ・HTTP クライアントは Hey API が `apps/api/openapi.json` から生成したコードを利用（出力先は `apps/web/src/__generated__/api/`、→ [ADR 0006](../../docs/adr/0006-json-schema-as-single-source-of-truth.md)）。手書きの型定義は使わない
- 生成物には手を入れず、エラー解釈・認証 Cookie 同梱・リトライ等の **横断処理は `src/lib/api/` 側で被せる**（生成物の更新で消えないように分離する）

### エラーハンドリング

- API エラーは `ApiErrorProvider` で一元的に処理（トースト表示）
- 個別フックは `error` state を必ず保持・返却（呼び出し側でフォームのインラインエラーに使う）

## テスト

- Vitest + Testing Library + MSW
- React 関連はテスト Library 必須、Vitest のみで完結するのは純粋な TS 関数のみ
- テストファイルは対象と同じ場所に配置（コロケーション）

| 種類 | ファイル名 | 技術 |
|---|---|---|
| 単体（関数） | `*.test.ts` | Vitest |
| 単体（フック・コンポーネント） | `*.test.ts(x)` | Vitest + Testing Library |
| 結合 | `*.test.tsx` | Vitest + Testing Library + MSW |

### 結合テストのルール

- `fireEvent` ではなく `userEvent` を使用
- API モックは MSW
- 非同期は `findBy*` / `waitFor` で待機
- 各テストは独立させる

## コロケーション原則

| 使用範囲 | 配置場所 |
|---|---|
| 1 つのコンポーネント内のみ | そのコンポーネントの `_components/`, `_hooks/` 等 |
| 同じページ内の複数コンポーネント | そのページの `_components/`, `_hooks/` 等 |
| 複数ページで共有 | 共通の祖先、または `src/components/`, `src/hooks/`, `src/lib/` |

### ディレクトリ命名（`_` プレフィックス）

| ディレクトリ | 用途 |
|---|---|
| `_layout/` | layout.tsx 専用コンポーネント |
| `_components/` | ローカルコンポーネント |
| `_hooks/` | ローカルカスタムフック |
| `_hooks/_fetch/` | API 呼び出し用フック |
| `_constants/` | ローカル定数 |
| `_utils/` | ローカルユーティリティ |

### ファイル配置

- **コンポーネント（`.tsx`）**：**必ず同名フォルダ + 同名ファイル**（`button/button.tsx` / `code-editor/code-editor.tsx`）。
  テスト・Storybook をコロケーションで同居させるため、単一ファイル配置は禁止
  （詳細は [.claude/rules/frontend-component.md](./frontend-component.md)）
- **フック（`.ts`）**：**1 ファイル直置きとフォルダ化を選べる**。フックは JSX を返さずテスト 1 本で十分なケースが多いため、サブフックや内部部品が無い間は直置きでよい
  - ✅ `_hooks/use-flow-state.ts`（1 ファイルのみ）
  - ✅ `_hooks/use-flow-state/use-flow-state.ts`（テストや内部 `_hooks/` が必要になったらフォルダ化）
- **コンポーネント / フック以外の素のファイル**：親ディレクトリ直下に直接配置（`types.ts`, `schema.ts`, `constants.ts`, `utils.ts`, `styles.ts`）

### 再帰的なコロケーション

`_components/` や `_hooks/` は再帰的にネストする。コンポーネントが子コンポーネントや専用フックを持つ場合、そのコンポーネントディレクトリ内にさらに `_components/` や `_hooks/` を配置する。

**スコープルール**：内側の `_components/` や `_hooks/` は、その直上の親コンポーネントからのみ参照すること。兄弟コンポーネントや上位ディレクトリから直接参照してはいけない。

```
code-editor/
├── code-editor.tsx                ← ここから _components/, _hooks/ を参照
├── _components/
│   └── diagnostic-panel/
│       ├── diagnostic-panel.tsx   ← ここから自身の _hooks/ を参照
│       └── _hooks/
│           └── use-diagnostics/
│               └── use-diagnostics.ts
└── _hooks/
    └── use-editor-state/
        └── use-editor-state.ts
```

- `code-editor.tsx` → `_components/diagnostic-panel/` や `_hooks/use-editor-state/` を参照 OK
- `diagnostic-panel.tsx` → 自身の `_hooks/use-diagnostics/` を参照 OK
- `diagnostic-panel.tsx` → 親の `_hooks/use-editor-state/` を直接参照 NG（親経由で props として渡す）
