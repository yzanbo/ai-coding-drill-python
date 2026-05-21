// /problems ページ（Server Component）のロジック単体テスト。
//
// 何を担保するか：
//   - 未ログイン時は /login?next=/problems に redirect する。
//   - フィルタ値（category / difficulty）は next クエリに保持される。
//   - ヘッダーに「新規問題を生成」「生成履歴」リンクが描画される。
//   - 取得した items はカテゴリ別にグルーピングされ、難易度昇順で並ぶ。
//
// 仕組み：
//   ProblemsListPage は async な Server Component なので、Testing Library で
//   render するのではなく、関数を直接 await して呼び出し、`redirect()` モック
//   呼び出しや戻り値の React ツリーを観測する。

import { beforeEach, describe, expect, it, vi } from "vitest";

const mockRedirect = vi.fn();
vi.mock("next/navigation", () => ({
  redirect: (...args: unknown[]) => mockRedirect(...args),
}));

// next/headers: cookies() を差し替える。テストごとに「Cookie あり / なし」を切替。
let mockCookieGetReturn: { value: string } | undefined;
vi.mock("next/headers", () => ({
  cookies: () =>
    Promise.resolve({
      get: () => mockCookieGetReturn,
      has: () => mockCookieGetReturn !== undefined,
    }),
}));

// listProblemsApiProblemsGet: 一覧 API クライアント。
//   テストでは items を差し替えてグルーピング / ソートを検証する。
let mockListResponse: {
  items: Array<{ id: string; title: string; category: string; difficulty: string }>;
  page: number;
  totalPages: number;
};
vi.mock("@/__generated__/api/sdk.gen", () => ({
  listProblemsApiProblemsGet: vi.fn(async () => ({
    data: mockListResponse,
    error: undefined,
    response: new Response(null, { status: 200 }),
  })),
}));

vi.mock("@/lib/api/server-api-client", () => ({
  serverApiClient: {},
}));

vi.mock("./_components/problems-filter-form/problems-filter-form", () => ({
  ProblemsFilterForm: () => null,
}));

const { default: ProblemsListPage } = await import("./page");

beforeEach(() => {
  mockRedirect.mockReset();
  mockListResponse = { items: [], page: 1, totalPages: 0 };
  mockCookieGetReturn = { value: "dummy-session" };
});

describe("ProblemsListPage の認証ガード", () => {
  it("Cookie 無し（未ログイン）なら /login?next=/problems に redirect する", async () => {
    mockCookieGetReturn = undefined;

    await ProblemsListPage({ searchParams: Promise.resolve({}) });

    expect(mockRedirect).toHaveBeenCalledWith("/login?next=%2Fproblems");
  });

  it("Cookie 無し + フィルタは next に保持される", async () => {
    mockCookieGetReturn = undefined;

    await ProblemsListPage({
      searchParams: Promise.resolve({ category: "array", difficulty: "easy" }),
    });

    expect(mockRedirect).toHaveBeenCalledWith(
      `/login?next=${encodeURIComponent("/problems?category=array&difficulty=easy")}`,
    );
  });
});

describe("ProblemsListPage のヘッダー導線", () => {
  it("ヘッダーに /problems/new への新規問題を生成リンクを描画する", async () => {
    mockListResponse = { items: [], page: 1, totalPages: 0 };

    const tree = await ProblemsListPage({
      searchParams: Promise.resolve({}),
    });

    expect(findHrefInTree(tree, "/problems/new")).toBe(true);
  });
});

describe("ProblemsListPage のカテゴリ別グルーピング", () => {
  it("カテゴリ別に並び、各カテゴリ内は難易度昇順（easy → medium → hard）で出る", async () => {
    // わざと難易度を逆順で渡し、Frontend 側でソートされることを確認する。
    mockListResponse = {
      items: [
        { id: "a1", title: "配列-hard", category: "array", difficulty: "hard" },
        { id: "a2", title: "配列-easy", category: "array", difficulty: "easy" },
        { id: "a3", title: "配列-medium", category: "array", difficulty: "medium" },
        { id: "s1", title: "文字列-easy", category: "string", difficulty: "easy" },
      ],
      page: 1,
      totalPages: 1,
    };

    const tree = await ProblemsListPage({
      searchParams: Promise.resolve({}),
    });

    // ツリー内に出現する problem-id リンクの順序を取り出す。
    //   ヘッダーの /problems/new リンクは除外（id は UUID 想定なので "new" と一致しない）。
    const order = collectHrefsByPrefix(tree, "/problems/").filter((h) => h !== "/problems/new");
    // 期待: string カテゴリ (s1) → array カテゴリ (a2 easy → a3 medium → a1 hard)
    expect(order).toEqual(["/problems/s1", "/problems/a2", "/problems/a3", "/problems/a1"]);
  });

  it("同一難易度内は title の日本語昇順（localeCompare ja）で並ぶ", async () => {
    // 同一カテゴリ・同一難易度の 3 件を、わざとアルファベット順とは違う順序で渡す。
    //   ja ロケールの localeCompare は仮名・漢字を一定順序でソートする。
    //   期待: あ < い < う。
    mockListResponse = {
      items: [
        { id: "a3", title: "うえ問題", category: "array", difficulty: "easy" },
        { id: "a1", title: "あい問題", category: "array", difficulty: "easy" },
        { id: "a2", title: "いう問題", category: "array", difficulty: "easy" },
      ],
      page: 1,
      totalPages: 1,
    };

    const tree = await ProblemsListPage({
      searchParams: Promise.resolve({}),
    });

    const order = collectHrefsByPrefix(tree, "/problems/").filter((h) => h !== "/problems/new");
    expect(order).toEqual(["/problems/a1", "/problems/a2", "/problems/a3"]);
  });
});

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

// collectHrefsByPrefix: ツリー走査で出現順に href を集める（prefix で絞り込み）。
function collectHrefsByPrefix(node: unknown, prefix: string, acc: string[] = []): string[] {
  if (node == null || typeof node !== "object") return acc;
  if (Array.isArray(node)) {
    for (const n of node) collectHrefsByPrefix(n, prefix, acc);
    return acc;
  }
  const el = node as { props?: Record<string, unknown> };
  if (el.props) {
    const href = el.props.href;
    if (typeof href === "string" && href.startsWith(prefix)) acc.push(href);
    if (el.props.children !== undefined) collectHrefsByPrefix(el.props.children, prefix, acc);
  }
  return acc;
}
