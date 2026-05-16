# lib/

## lib/ とは何か

**React / Next.js の機能に依らない** 素のロジック・設定・スキーマ・型ラッパの置き場です。
ここに置くファイルは「`useState` も `useEffect` も使わない、JSX も返さない」純粋な TypeScript。
そうすることで Node 単体テストでもブラウザでも同じように動く、再利用しやすいコードに保てる。

| サブフォルダ | これは何か（役目） |
|---|---|
| `api/` | **手書きの API ラッパ**。Hey API が作る生のクライアント（`__generated__/api/`）に被せる、エラー解釈やトークン処理等の補強。生成物そのものはここに置かない |
| `validation/` | **Zod スキーマ**の置き場。フォーム入力の形を定義し、`@hookform/resolvers/zod` 経由で React Hook Form と組み合わせる |
| `utils/` | **汎用関数**（日付フォーマット・文字列整形・配列処理等）。1 ファイル 1 関数を基本に、テストしやすい純粋関数を集める |
| `constants/` | **サイト全体で使う定数**（ルートパス・列挙値ラベル・ページサイズ既定値等）。マジックナンバー / マジック文字列をコード中に散らさないため |
| `styles/` | **複雑なスタイル定数**（CodeMirror テーマの色配列等、Tailwind だけでは表現しきれないもの）。Tailwind の `className` 文字列で済むものはここに入れない |
| `shared-query/` | **TanStack Query の共有設定**（`queryClient` の生成・既定 `staleTime` 等）。Provider で読み込む |

`lib/utils.ts`（shadcn/ui の `cn()` ヘルパー）のような **1 行小物の単発ファイル**は、無理にフォルダを
作らず lib 直下に直接置いてよい。

## 役目

- React / Next.js から **独立**した素のロジック・設定を集約する
- `__generated__/api/` の生成物を **手書きコードで上書きしない** 形で補強する（薄いラッパだけ書く）
- フォームの入力スキーマ・定数・ユーティリティ等、UI 部品から切り離せるものを引き取る

## やってはいけないこと

- ❌ `lib/` から `components/` や `hooks/` を import（lib は React 非依存に保つ）
- ❌ `lib/api/` 配下に Hey API の生成物を直接置く（生成物は `src/__generated__/api/` 一択）
- ❌ Tailwind の class 文字列で書ける装飾を `styles/` のオブジェクトにする（YAGNI）
- ❌ `index.ts` で再エクスポート（バレル禁止）

詳しい配置・命名・import 方向は [.claude/rules/frontend.md](../../../../.claude/rules/frontend.md) の
**§ディレクトリ構成**・**§API クライアント**・**§フォームバリデーション**。
