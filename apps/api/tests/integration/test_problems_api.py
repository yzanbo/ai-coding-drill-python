# /api/problems 系（一覧 / 詳細）ルーターの結合テスト。
#
# テスト方針：
#   - 実 FastAPI（main.app）+ 実 Postgres + fakeredis の組み合わせ
#   - 認証不要のルートのためログインスタブは使わない（ゲスト経路を直接叩く）
#   - DB に直接 Problem を INSERT して、API 経由で読み取れることを観察
#
# 関わる要件：
#   - docs/requirements/4-features/problem-display-and-answer.md §API / §受け入れ条件
#   - docs/requirements/3-cross-cutting/02-api-conventions.md

import uuid
from collections.abc import AsyncIterator

import fakeredis.aioredis
import pytest
from httpx import AsyncClient
from sqlalchemy import delete

from app.db.session import AsyncSessionLocal
from app.models.problems import Problem


@pytest.fixture(autouse=True)
async def reset_problems_table() -> AsyncIterator[None]:
    """各テスト前に problems を空にする（テスト間の独立性）。"""
    async with AsyncSessionLocal() as session:
        await session.execute(delete(Problem))
        await session.commit()
    yield


async def _insert_problem(
    *,
    title: str = "配列の合計を返す",
    category: str = "array",
    difficulty: str = "easy",
    description: str = "数値配列を受け取り、その合計を返す関数 solve を実装してください。",
    examples: list[dict] | None = None,
    test_cases: list[dict] | None = None,
    deleted: bool = False,
) -> uuid.UUID:
    """テスト用に problems に 1 行 INSERT して id を返す。"""
    async with AsyncSessionLocal() as session:
        problem = Problem(
            title=title,
            description=description,
            category=category,
            difficulty=difficulty,
            language="typescript",
            examples=examples or [{"input": "[1,2,3]", "output": "6"}],
            # test_cases.input は Worker 側 TestCase 契約に合わせて配列で入れる
            # （文字列を入れると grading Worker が json unmarshal で落ちて即 dead 行きになる）。
            test_cases=test_cases
            or [
                {"input": [[1, 2, 3]], "expected": 6},
                {"input": [[]], "expected": 0},
                {"input": [[-1, 1]], "expected": 0},
            ],
            reference_solution="const solve = (a: number[]) => a.reduce((s, n) => s + n, 0);",
            judge_scores={"correctness": 5, "difficulty_fit": 5},
        )
        session.add(problem)
        await session.flush()
        problem_id = problem.id
        if deleted:
            # ソフトデリート印を立てる（updated_at 等は server_default に任せる）。
            from datetime import UTC, datetime

            problem.deleted_at = datetime.now(UTC)
        await session.commit()
    return problem_id


# ----------------------------------------------------------------------------
# GET /api/problems （一覧）
# ----------------------------------------------------------------------------
class TestListProblems:
    async def test_正常系_ゲストでも200で一覧が返る(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        """ゲスト閲覧可（problem-display-and-answer.md §ビジネスルール）。
        Cookie / 認証ヘッダなしでも 401 にならず 200 が返る。
        """
        del fake_redis
        await _insert_problem(title="A", category="array", difficulty="easy")
        await _insert_problem(title="B", category="string", difficulty="hard")

        res = await client.get("/api/problems")

        assert res.status_code == 200
        body = res.json()
        assert "items" in body
        assert body["page"] == 1
        assert body["totalPages"] == 1
        assert len(body["items"]) == 2
        # 各 item に title / category / difficulty が camelCase で詰まっている。
        for item in body["items"]:
            assert set(item.keys()) == {"id", "title", "category", "difficulty"}

    async def test_正常系_カテゴリと難易度でフィルタできる(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        del fake_redis
        await _insert_problem(title="A", category="array", difficulty="easy")
        await _insert_problem(title="B", category="array", difficulty="hard")
        await _insert_problem(title="C", category="string", difficulty="easy")

        res = await client.get("/api/problems?category=array&difficulty=easy")

        assert res.status_code == 200
        body = res.json()
        titles = [item["title"] for item in body["items"]]
        assert titles == ["A"]

    async def test_正常系_ソフトデリート済みは一覧に出ない(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        del fake_redis
        await _insert_problem(title="生きてる", category="array", difficulty="easy")
        await _insert_problem(
            title="削除済み", category="array", difficulty="easy", deleted=True
        )

        res = await client.get("/api/problems")

        body = res.json()
        titles = [item["title"] for item in body["items"]]
        assert titles == ["生きてる"]

    async def test_正常系_0件でも200で_items_は空配列_total_pages_は0(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        del fake_redis
        res = await client.get("/api/problems")

        assert res.status_code == 200
        body = res.json()
        assert body["items"] == []
        assert body["page"] == 1
        assert body["totalPages"] == 0

    async def test_正常系_最終ページに残りの_items_が返る(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        """1 ページ 20 件の境界：total=21 で page=2 を踏むと 1 件返る。
        Frontend は totalPages=2 を信じてページネーション UI を出すので、
        最終ページに items が確実に返る契約を担保する。
        """
        del fake_redis
        for i in range(21):
            await _insert_problem(title=f"P{i:02d}", category="array", difficulty="easy")

        res = await client.get("/api/problems?page=2")

        assert res.status_code == 200
        body = res.json()
        assert body["page"] == 2
        assert body["totalPages"] == 2
        # 21 件 - 20 件（page 1 で消費） = 1 件が最終ページに残る。
        assert len(body["items"]) == 1

    async def test_正常系_page超過時は200で_items_空配列_を返す(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        """page > totalPages を直接踏んだ時の挙動：
          - 404 ではなく 200 + items=[] を返す（Frontend 側で最終ページへ redirect する前提）
          - totalPages は実体に基づく値（例：5 件しか無いなら totalPages=1）

        この契約が壊れると `/problems/page.tsx` の redirect ロジック（page.tsx:106-108）が
        前提を失い、無限 redirect / 真っ白画面の事故になる。
        """
        del fake_redis
        for i in range(5):
            await _insert_problem(title=f"P{i:02d}", category="array", difficulty="easy")

        res = await client.get("/api/problems?page=999")

        assert res.status_code == 200
        body = res.json()
        assert body["page"] == 999
        assert body["totalPages"] == 1
        assert body["items"] == []

    async def test_異常系_未定義カテゴリは422(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        del fake_redis
        res = await client.get("/api/problems?category=unknown")
        assert res.status_code == 422

    async def test_異常系_page_0以下は422(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        del fake_redis
        res = await client.get("/api/problems?page=0")
        assert res.status_code == 422

    async def test_異常系_page_size_1001以上は422(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        # 未認証で叩けるエンドポイントのため、page_size は上限 1000 で頭打ち。
        #   攻撃面を絞る目的（FE の ALL_FETCH_PAGE_SIZE と一致）。
        del fake_redis
        res = await client.get("/api/problems?page_size=1001")
        assert res.status_code == 422


# ----------------------------------------------------------------------------
# GET /api/problems/:problemId （詳細）
# ----------------------------------------------------------------------------
class TestGetProblemDetail:
    async def test_正常系_ゲストでも200で詳細が返り_テストケースが漏れない(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        """マスキング契約：API レスポンスから完全な test_cases が読み出せない
        （problem-display-and-answer.md §受け入れ条件）。
        """
        del fake_redis
        # examples は 1 件のみ、test_cases は 3 件用意 → レスポンスには examples だけ。
        problem_id = await _insert_problem(
            examples=[{"input": "[1,2,3]", "output": "6"}],
            test_cases=[
                {"input": [[1, 2, 3]], "expected": 6},
                {"input": [[]], "expected": 0},
                {"input": [[-1, 1]], "expected": 0},
            ],
        )

        res = await client.get(f"/api/problems/{problem_id}")

        assert res.status_code == 200
        body = res.json()
        assert body["id"] == str(problem_id)
        # 公開キーのみ。test_cases / reference_solution / judge_scores が
        # camelCase / snake_case のどちらでも漏れていないことを確認。
        assert set(body.keys()) == {
            "id",
            "title",
            "description",
            "examples",
            "category",
            "difficulty",
        }
        assert len(body["examples"]) == 1

    async def test_異常系_存在しないIDは404(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        del fake_redis
        res = await client.get(f"/api/problems/{uuid.uuid4()}")
        assert res.status_code == 404

    async def test_異常系_ソフトデリート済みは404(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        del fake_redis
        problem_id = await _insert_problem(deleted=True)
        res = await client.get(f"/api/problems/{problem_id}")
        assert res.status_code == 404

    async def test_異常系_不正なUUIDは422(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        del fake_redis
        res = await client.get("/api/problems/not-a-uuid")
        assert res.status_code == 422
