import pytest
from httpx import AsyncClient


@pytest.mark.integration
async def test_post_then_get_health_returns_inserted_row(
    client: AsyncClient,
    reset_health_check_table: None,
) -> None:
    """POST で 1 行 INSERT した後、GET で同じ id を取得できる（router → DB → router の往復）。"""
    post_response = await client.post("/health")
    assert post_response.status_code == 200
    created = post_response.json()
    assert "id" in created
    assert "created_at" in created

    get_response = await client.get("/health")
    assert get_response.status_code == 200
    items = get_response.json()
    assert len(items) == 1
    assert items[0]["id"] == created["id"]


@pytest.mark.integration
async def test_get_health_returns_at_most_10_newest_first(
    client: AsyncClient,
    reset_health_check_table: None,
) -> None:
    """11 件 INSERT して、GET が 10 件で created_at desc 順になることを確認。"""
    for _ in range(11):
        post_response = await client.post("/health")
        assert post_response.status_code == 200

    response = await client.get("/health")
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 10
    timestamps = [item["created_at"] for item in items]
    assert timestamps == sorted(timestamps, reverse=True)
