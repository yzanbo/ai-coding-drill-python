# src/

Next.js 16+ のフロントエンドアプリ本体の置き場。URL（`app/`）から、画面部品（`components/`）、
ロジックの取り出し口（`hooks/`）、React に依らない素のロジック（`lib/`）、自動生成された型・関数
（`__generated__/`）まで、役割ごとにフォルダを分けている。

各フォルダの役目は、それぞれの README.md を見る。レイヤ全体の規約・配置・命名・import 方向の
正本（実装契約）は [.claude/rules/frontend.md](../../../.claude/rules/frontend.md) が SSoT。

| フォルダ | これは何か（役目） |
|---|---|
| `app/` | Next.js の **App Router**（URL とファイル配置を 1:1 にする仕組み）の置き場。`page.tsx` / `layout.tsx` / `loading.tsx` のような **役割が決まったファイル**を置くと、フォルダ名がそのまま URL になる。ルートグループ `(authed)` / `(public)` で認証要否を分ける |
| [components/](./components/README.md) | 複数ページで使い回す **画面部品**（ボタン・カード・モーダル等）の置き場。中身は **汎用 UI** / **ドメイン文脈付きパーツ** / **React の Provider** の 3 種類に分ける |
| [hooks/](./hooks/README.md) | 複数ページで使い回す **カスタムフック**（`use-xxx` 関数）の置き場。ページ固有のフックは置かない（それは `app/.../page-dir/_hooks/` に置く） |
| [lib/](./lib/README.md) | **React / Next.js の機能に依らない** 素のロジック・設定・スキーマ・型ラッパの置き場。手書きの API クライアント補強 / Zod スキーマ / 定数 / ユーティリティ関数等 |
| [__generated__/](./__generated__/README.md) | **人手で編集しない** 自動生成物の集積場所。Hey API が `apps/api/openapi.json` から作った TS 型 / Zod / HTTP クライアントを `api/` 配下に置く（[ADR 0006](../../../docs/adr/0006-json-schema-as-single-source-of-truth.md)） |

## レイヤ間の呼び出しの向き

新しい画面・部品を作る時、どのフォルダから どのフォルダを呼んでよいかを下図で固定する。
**矢印の向きにのみ呼び出し可、逆向きは禁止**（循環依存を防ぐため）。

```
                       [ブラウザ画面]
                            │
                            ▼
                     ┌─────────────┐
                     │    app/     │   URL とファイル配置を 1:1 にする箱
                     │ (page.tsx)  │   （Next.js App Router）
                     └──────┬──────┘
                            │ page.tsx が下のレイヤを呼ぶ
              ┌─────────────┼─────────────┐
              ▼             ▼             ▼
       ┌────────────┐  ┌────────┐  ┌─────────┐
       │ components/│  │ hooks/ │  │  lib/   │
       │ (ui/parts/ │  │(use-*) │  │ (api /  │
       │ providers) │  │        │  │ utils / │
       │            │  │        │  │  ...)   │
       └─────┬──────┘  └────┬───┘  └────┬────┘
             │              │           │
             │ 画面部品は    │ hook は    │
             │ hooks/lib を  │ lib を     │
             │ 呼んでよい    │ 呼んでよい  │
             └──────┬───────┴─────┬─────┘
                    ▼             ▼
                ┌──────────────────────┐
                │   __generated__/api/ │  Hey API が作る型 / Zod /
                │  （人が触らない）     │  HTTP クライアント（ADR 0006）
                └──────────────────────┘
```

> ページ固有の部品・フック（複数ページで使い回さないもの）は `app/.../_components/` や
> `_hooks/` に置く（コロケーション、[frontend.md](../../../.claude/rules/frontend.md) §コロケーション原則）。
> ここでの「上の層から下の層を呼ぶ」ルールは、`src/{components,hooks,lib}/` に**昇格させた共有部品**の話。

### 読み方（具体例）

- **正常な流れ**：`app/(authed)/problems/page.tsx`（問題一覧画面）が
  `components/parts/problem-card/problem-card.tsx` を import → そのカード内で
  `hooks/use-get-problems/use-get-problems.ts` を呼んで一覧を取る → フック内で
  `__generated__/api/` の `getProblems()` を叩く。
- **lib/ は素のロジック専用**：日付フォーマット・Zod スキーマ・定数等は `lib/` に置く。
  React のフック（`useState` 等）を含むコードは `hooks/` に置く（lib に React 依存を持ち込まない）。
- **`__generated__/` は終端**：他の `src/` 配下を import してはいけない（生成器が壊れる）。
  逆に他のフォルダから自由に import してよい。
- **同レベル内の呼び出し**：`components/parts/` 内で `components/ui/` を呼ぶのは OK。
  `hooks/` 内で別の `hooks/` を呼ぶのも OK（ただし循環しないこと）。

### やってはいけないこと（よくある間違い）

- ❌ `hooks/` から `components/` を import（フックは JSX を返さない）
- ❌ `lib/` から `components/` や `hooks/` を import（lib は React 非依存に保つ）
- ❌ `__generated__/` を手で編集する（次の `mise run web:types-gen` で消える）
- ❌ ページ固有の部品を `src/components/` に置く（コロケーションを使う、`app/.../_components/`）
- ❌ `index.ts` で再エクスポート（バレルファイル禁止、[frontend.md](../../../.claude/rules/frontend.md)）
- ❌ A → B かつ B → A の関係（循環）

ルールの正本（表形式・コード例付き）は [.claude/rules/frontend.md: レイヤ間の import 方向](../../../.claude/rules/frontend.md)。
