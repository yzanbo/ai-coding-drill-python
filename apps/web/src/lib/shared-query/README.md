# lib/shared-query/

## lib/shared-query/ とは何か

**TanStack Query の共有設定**を置くフォルダ。`QueryClient` のインスタンス生成と、サイト全体で
共通させたい既定値（`staleTime` / `retry` / `refetchOnWindowFocus` 等）を 1 か所にまとめます。

[components/providers/tanstack-query-provider/](../../components/providers/) はここで作った
`queryClient` を読み込んで `<QueryClientProvider>` で配るだけにします（生成は lib 側、配布は
providers 側、という分担）。

代表例（このプロジェクトで想定）：

- `query-client.ts`（`new QueryClient({ defaultOptions: { queries: { staleTime: ... } } })`）
- `query-keys.ts`（クエリキーを `["problems", { page: 1 }]` のようなタプル定数で集約）

## 役目

- `QueryClient` の **生成** と既定値を 1 か所にまとめる
- クエリキーを `as const` で集約し、key の typo を防ぐ
- React の Provider 本体（JSX）は持たない。それは [components/providers/](../../components/providers/) 側

## やってはいけないこと

- ❌ ここで `useQuery` を呼ぶ（フックは [hooks/](../../hooks/) 側）
- ❌ JSX（`<QueryClientProvider>`）をここに書く（Provider は components/providers/ 側）
- ❌ 1 つの画面でしか使わないクエリキーを集約する（ローカルに留める）

## 採用タイミング

R0 時点では未導入。TanStack Query を **採点ジョブのポーリング等で初めて使う時**（採点機能着手時）
にこのフォルダを使い始める。それまではフォルダだけ用意して、`query-client.ts` を置くのは後回しでよい。
