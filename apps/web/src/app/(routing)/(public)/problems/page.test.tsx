// /problems ページ（Server Component）のロジック単体テスト。
//
// 何を担保するか：
//   - `?page=999` のように totalPages を超える page で踏まれたら、最終ページに
//     `redirect()` で寄せる（page.tsx §「ページ範囲外」）。
//   - totalPages=0（条件に合う問題ゼロ）の時は寄せ先が無いので redirect しない。
//   - 範囲内（1..totalPages）は redirect しない。
//
// 仕組み：
//   ProblemsListPage は async な Server Component なので、Testing Library で
//   render するのではなく、関数を直接 await して呼び出し、`redirect()` モックが
//   呼ばれたかを観測する。実際の Next.js ランタイムでは redirect() は内部例外を
//   throw して制御を抜くが、テストでは vi.fn() に置き換えて副作用だけ拾えれば
//   検証目的を満たす（redirect 後の JSX レンダリングは検証対象外）。

import { beforeEach, describe, expect, it, vi } from "vitest";

// next/navigation: Server Component の redirect だけ差し替え。
//   redirect は通常 throw するが、テストでは spy だけ取りたいので何もしないモックにする。
const mockRedirect = vi.fn();
vi.mock("next/navigation", () => ({
  redirect: (...args: unknown[]) => mockRedirect(...args),
}));

// next/headers: cookies() を差し替える。テストごとに「Cookie あり / なし」を切替。
//   既定はログイン済み（cookie あり）にしておく。未ログイン分岐は専用ブロックで上書き。
//   hasSessionCookie ヘルパは内部で .has() を呼ぶため、get と連動させて両方差し替える。
let mockCookieGetReturn: { value: string } | undefined;
vi.mock("next/headers", () => ({
  cookies: () =>
    Promise.resolve({
      get: () => mockCookieGetReturn,
      has: () => mockCookieGetReturn !== undefined,
    }),
}));

// listProblemsApiProblemsGet: 一覧 API クライアント。
//   各テストで totalPages / items を差し替えてページネーション分岐を再現する。
let mockListResponse: {
  items: Array<{ id: string; title: string; category: string; difficulty: string }>;
  total: number;
  page: number;
  totalPages: number;
};
// throwIfError は response.ok を見て分岐するため、ダミーの ok レスポンスも併せて返す。
vi.mock("@/__generated__/api/sdk.gen", () => ({
  listProblemsApiProblemsGet: vi.fn(async () => ({
    data: mockListResponse,
    error: undefined,
    response: new Response(null, { status: 200 }),
  })),
}));

// serverApiClient: Server Component から呼ばれる Hey API クライアント。
//   ロード時に env validation を走らせて throw するため、テストでは無害な値に差し替える。
vi.mock("@/lib/api/server-api-client", () => ({
  serverApiClient: {},
}));

// 子の Client Component（フィルタフォーム）も render したいだけなのでスタブ。
vi.mock("./_components/problems-filter-form/problems-filter-form", () => ({
  ProblemsFilterForm: () => null,
}));

// import は vi.mock の後に置く（Vitest が hoisting する mock を先に効かせるため）。
const { default: ProblemsListPage } = await import("./page");

beforeEach(() => {
  mockRedirect.mockReset();
  mockListResponse = { items: [], total: 0, page: 1, totalPages: 0 };
  // 既定はログイン済み（cookie あり）。未ログインの認証ガード分岐は
  // 別 describe で明示的に undefined に上書きする。
  mockCookieGetReturn = { value: "dummy-session" };
});

describe("ProblemsListPage の認証ガード", () => {
  it("Cookie 無し（未ログイン）なら /login?next=/problems に redirect する", async () => {
    mockCookieGetReturn = undefined;

    await ProblemsListPage({ searchParams: Promise.resolve({}) });

    expect(mockRedirect).toHaveBeenCalledWith("/login?next=%2Fproblems");
  });

  it("Cookie 無し + フィルタ / ページ番号は next に保持される", async () => {
    mockCookieGetReturn = undefined;

    await ProblemsListPage({
      searchParams: Promise.resolve({ category: "array", difficulty: "easy", page: "2" }),
    });

    expect(mockRedirect).toHaveBeenCalledWith(
      `/login?next=${encodeURIComponent("/problems?category=array&difficulty=easy&page=2")}`,
    );
  });
});

describe("ProblemsListPage の page 範囲外リダイレクト", () => {
  it("?page=999 を踏むと、最終ページ（totalPages=3）に redirect する", async () => {
    mockListResponse = {
      items: [{ id: "p1", title: "x", category: "array", difficulty: "easy" }],
      total: 50,
      page: 999,
      totalPages: 3,
    };

    await ProblemsListPage({
      searchParams: Promise.resolve({ page: "999" }),
    });

    expect(mockRedirect).toHaveBeenCalledWith("/problems?page=3");
  });

  it("フィルタ付きで範囲外を踏むと、redirect 先 URL にフィルタが保持される", async () => {
    mockListResponse = {
      items: [{ id: "p1", title: "x", category: "array", difficulty: "easy" }],
      total: 5,
      page: 10,
      totalPages: 1,
    };

    await ProblemsListPage({
      searchParams: Promise.resolve({ category: "array", difficulty: "easy", page: "10" }),
    });

    // category / difficulty を保持しつつ最終ページに寄せる（page=1 はクエリから省略される）。
    expect(mockRedirect).toHaveBeenCalledWith("/problems?category=array&difficulty=easy");
  });

  it("totalPages=0（ヒット無し）の時は redirect しない", async () => {
    mockListResponse = { items: [], total: 0, page: 999, totalPages: 0 };

    await ProblemsListPage({
      searchParams: Promise.resolve({ page: "999" }),
    });

    expect(mockRedirect).not.toHaveBeenCalled();
  });

  it("範囲内（page=2, totalPages=3）は redirect しない", async () => {
    mockListResponse = {
      items: [{ id: "p1", title: "x", category: "array", difficulty: "easy" }],
      total: 50,
      page: 2,
      totalPages: 3,
    };

    await ProblemsListPage({
      searchParams: Promise.resolve({ page: "2" }),
    });

    expect(mockRedirect).not.toHaveBeenCalled();
  });
});

describe("ProblemsListPage のヘッダー導線", () => {
  it("ヘッダーに /problems/new への新規問題を生成リンクを描画する", async () => {
    // 要件: problem-display-and-answer.md §受け入れ条件「一覧画面のヘッダー領域に
    //   新規問題を生成ボタン」/ problem-generation.md §到達経路
    mockListResponse = { items: [], total: 0, page: 1, totalPages: 0 };

    const tree = await ProblemsListPage({
      searchParams: Promise.resolve({}),
    });

    // JSX ツリーを再帰探索して href="/problems/new" を含む Link/anchor を探す。
    //   Server Component なので Testing Library を介さず、戻り値の React ノードを
    //   そのまま辿る形で確認する（既存テストの直接 await パターンを踏襲）。
    const found = findHrefInTree(tree, "/problems/new");
    expect(found).toBe(true);
  });
});

// findHrefInTree: React node を再帰的に走査し、props.href === target を含むかを返す。
//   Server Component の戻り値検証用の小道具。Link / a / Button asChild のいずれでも
//   最終的に href prop で識別できれば足りる。
function findHrefInTree(node: unknown, target: string): boolean {
  if (node == null || typeof node !== "object") return false;
  if (Array.isArray(node)) return node.some((n) => findHrefInTree(n, target));
  const el = node as { props?: Record<string, unknown> };
  if (el.props) {
    if (el.props.href === target) return true;
    if (el.props.children !== undefined && findHrefInTree(el.props.children, target)) {
      return true;
    }
  }
  return false;
}
