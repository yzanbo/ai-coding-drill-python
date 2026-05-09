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

## ディレクトリ構成

```
apps/web/src/
├── app/
│   └── (routing)/
│       ├── (public)/                # 認証不要（ランディング、ログイン）
│       │   ├── page.tsx             # /
│       │   └── login/
│       │       └── page.tsx         # /login
│       └── (authed)/                # 認証必須（layout.tsx でガード）
│           ├── problems/
│           │   ├── page.tsx         # /problems（一覧）
│           │   └── [id]/
│           │       └── page.tsx     # /problems/:id（解答画面）
│           └── history/
│               └── page.tsx         # /history（学習履歴）
├── components/
│   ├── ui/                          # shadcn/ui + カスタム拡張 + 汎用 UI
│   ├── parts/                       # ドメインロジックを含む再利用パーツ
│   └── providers/                   # React プロバイダー
├── lib/
│   ├── api/                         # NestJS API クライアント
│   ├── validation/                  # Zod スキーマ
│   ├── utils/                       # ユーティリティ
│   └── utils.ts                     # cn() ヘルパー
└── hooks/                           # グローバルカスタムフック
```

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

## コマンド

```bash
pnpm --filter @ai-coding-drill/web dev          # 開発サーバー
pnpm --filter @ai-coding-drill/web build        # ビルド
pnpm --filter @ai-coding-drill/web typecheck    # tsc --noEmit
pnpm --filter @ai-coding-drill/web test         # Vitest
pnpm lint                                        # Biome（ルートから全パッケージ）
pnpm format                                      # Biome フォーマット
```

## 環境変数

- `NEXT_PUBLIC_API_URL`：NestJS API の URL（例：`http://localhost:3001`）
- public 変数は `NEXT_PUBLIC_` プレフィックス必須

## CodeMirror 6 の使い方

- `@codemirror/lang-javascript`（TypeScript ハイライト）
- `@typescript/vfs` + `@valtown/codemirror-ts`（ブラウザ内型診断・補完）
- 採点はサーバ側（Vitest）が正、ブラウザの型診断は UX 向上のための即時フィードバック
- 解答コンポーネントはコロケーションで `app/(authed)/problems/[id]/_components/code-editor/` に配置

## importパスの規則

境界は **`page.tsx` が存在するディレクトリ**で決まる。

- **`@/` エイリアス**：以下の場合に使用する
  - `src/` 直下の共通リソース（`components/`, `hooks/`, `lib/` など）
  - 自分の `page.tsx` ディレクトリの外にあるリソース
  - 例：`import { Button } from "@/components/ui/button"`
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

## 型の命名規則

| 種別 | 命名パターン | 例 |
|---|---|---|
| 一般的な型 | `◯◯Type` | `ProblemType`, `SubmissionType` |
| コンポーネントの props | `◯◯Props` | `CodeEditorProps`, `ButtonProps` |
| フックの戻り値型 | `◯◯Return` | `UseGetProblemsReturn` |
| RHF フォームの値型 | `◯◯FormValues` | `LoginFormValues` |

## コーディングルール

- IDE の問題タブにエラー・警告があれば適宜修正
- lint・型チェック・knip 等のコマンド実行時に警告が出たら、即時修正（警告を放置しない）
- ファイル名・ディレクトリ名はケバブケース（例：`use-get-problems.ts`、`code-editor/`）
- 再エクスポート禁止（`export { ... } from "..."` は使わない）
- **`index.ts` の作成禁止**：バレルファイルは作成しない、import は常に具体的なファイルパスを指定する
  - ❌ `import { CodeEditor } from "./_components/code-editor"` (index.ts 経由)
  - ✅ `import { CodeEditor } from "./_components/code-editor/code-editor"` (直接指定)
- 条件付きクラスや複数のクラス変数を結合する場合は `cn()` を使用する
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
- 型は `packages/shared-types/generated/ts/` から import（→ [ADR 0006](../../docs/adr/0006-json-schema-as-single-source-of-truth.md)）

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

- **単一ファイル**：親ディレクトリ直下に配置（`types.ts`, `schema.ts`, `constants.ts`, `utils.ts`, `styles.ts`）
- **フォルダ構成**：同名フォルダ内に同名ファイル（`code-editor/code-editor.tsx`）
- **1 ファイルのみの場合**：`_hooks/` や `_components/` 内にファイルが 1 つしかない場合は、サブディレクトリを作らずに直接配置してよい
  - ✅ `_hooks/use-flow-state.ts`（1 ファイルのみ）
  - ✅ `_hooks/use-flow-state/use-flow-state.ts`（サブディレクトリありも可）

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
