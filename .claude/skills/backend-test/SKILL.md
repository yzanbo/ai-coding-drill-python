---
name: backend-test
description: 要件 .md に基づいて FastAPI のユニット / 結合テストを生成・実行する
argument-hint: "[F-XX-feature-name] (例: F-02-problem-generation, F-04-auto-grading)"
---

# 要件ベースのバックエンドテスト生成・実行

引数 `$ARGUMENTS` を機能名として解釈する。

> **本プロジェクトでは Repository レイヤを採用しない**（Service が `AsyncSession` から SQLAlchemy 2.0 を直接呼ぶ単層構成、→ [.claude/rules/backend.md](../../rules/backend.md)）。テスト戦略は「Service の純粋関数を切り出してユニットテスト + Service+DB の結合テスト」を組み合わせる。**Repository をモックするユニットテストは作らない**（モックでは ORM の挙動を再現できず false positive を生むため）。Repository モックパターンは別プロジェクトでの参考用に §付録 A にコメントとして残してある。

## 手順

### 1. 要件と実装の読み込み

1. `docs/requirements/4-features/$ARGUMENTS.md` を読み込む
2. [.claude/rules/backend.md](../../rules/backend.md) のテスト規約を確認する
3. 対象モジュールの実装コードを読み込む：
   - `apps/api/app/services/$ARGUMENTS.py` — テスト対象のメインロジック（SQLAlchemy クエリも含む）
   - `apps/api/app/routers/$ARGUMENTS.py` — エンドポイントの確認
   - `apps/api/app/schemas/$ARGUMENTS.py` — Pydantic スキーマ
   - `apps/api/app/models/$ARGUMENTS.py` — SQLAlchemy モデル

### 2. テスト方針の提示

以下をユーザーに提示し、承認を得てから生成に着手する：

- テスト対象のサービス・メソッド一覧
- テストケースの概要（正常系・異常系・境界値）
- 単体テスト（純粋関数の切り出し検証）と結合テスト（実 DB + httpx でクエリ動作検証）の使い分け
- 生成するファイルの一覧

### 3. ユニットテスト生成

`apps/api/tests/unit/test_$ARGUMENTS.py` を作成する。

#### テスト規約

- フレームワーク：pytest + pytest-asyncio（→ [ADR 0038](../../../docs/adr/0038-test-frameworks.md)）
- テスト関数名・docstring は日本語：`def test_正常系_一覧取得() -> None:` / `"""異常系: 存在しない ID で 404"""`
- **Service の純粋ロジック（バリデーション・計算・分岐・Pydantic 詰め替え）を切り出して直接検証する**
- SQLAlchemy が絡むメソッドはユニットでモックせず、§4 結合テストで実 DB を使って検証する
- ファイル名：`tests/unit/test_<feature>.py`、機能あたり 1 ファイル

#### テスト構造（純粋関数の単体テスト例）

```python
import pytest
from uuid import uuid4

from app.schemas.problems import ProblemCreate
from app.services.problems import (
    validate_difficulty,            # Service から切り出した純粋関数
    build_problem_response,          # SQLAlchemy モデル → Pydantic 詰め替え
)
from app.core.exceptions import ValidationError


class TestValidateDifficulty:
    def test_正常系_想定値はそのまま返る(self) -> None:
        assert validate_difficulty("easy") == "easy"

    def test_異常系_未知の難易度はValidationError(self) -> None:
        with pytest.raises(ValidationError):
            validate_difficulty("impossible")
```

> SQLAlchemy セッション・クエリが絡む `ProblemsService.create` / `.list_problems` 等は **結合テスト（§4）** で検証する。Service クラス全体をモックでテストせず、ロジック部分を関数として切り出してから単体検証するのが本プロジェクトの方針。

#### LLM プロバイダのモックパターン（将来）

LLM 呼び出しは Worker 側に閉じるため、Backend のテストには通常出てこない（→ [ADR 0040](../../../docs/adr/0040-worker-grouping-and-llm-in-worker.md)）。Backend の責務は enqueue + 結果取得なので、モックするのは NOTIFY 程度（必要時のみ）。

#### テストケースのカバレッジ目安

各サービスメソッドに対して：

- **正常系**：期待通りの結果が返ること
- **異常系（存在チェック）**：存在しないリソースで `NotFoundError`
- **異常系（権限チェック）**：他人のリソースで `ForbiddenError`
- **異常系（バリデーション）**：Pydantic バリデーション、ビジネスルール違反
- **境界値**：空配列、None、最大文字数、最小日付等

### 4. 結合テスト（router レベル）

`apps/api/tests/integration/test_$ARGUMENTS_api.py` で httpx + 実 DB を使う：

```python
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_GET_problems_正常系(client: AsyncClient, authenticated_user) -> None:
    response = await client.get("/problems")
    assert response.status_code == 200
    body = response.json()
    assert "data" in body and "meta" in body


@pytest.mark.asyncio
async def test_POST_problems_異常系_未認証(client: AsyncClient) -> None:
    response = await client.post("/problems", json={"title": "x"})
    assert response.status_code == 401
```

`client` / `authenticated_user` フィクスチャは `tests/conftest.py` で提供する（FastAPI テスト用 lifespan + DB セッション差し替え + テストユーザー作成）。

### 5. テスト実行

```bash
# 全テスト
mise run api:test

# 特定機能のみ（pytest -k で絞り込み）
cd apps/api && uv run pytest -k $ARGUMENTS -v

# 単体のみ
cd apps/api && uv run pytest tests/unit/ -v

# 結合のみ
cd apps/api && uv run pytest tests/integration/ -v

# カバレッジ
cd apps/api && uv run pytest --cov=app --cov-report=term-missing
```

テストが失敗した場合は修正して再実行。全テストがパスするまで繰り返す。

### 6. E2E テスト（必要な場合）

重要なフロー（解答送信 → 採点 → 結果取得）は E2E でも検証する。詳細は [.claude/rules/backend.md](../../rules/backend.md) の「E2E テストの実行方法」を参照。

```bash
docker compose -f docker-compose.test.yml up -d
cd apps/api && uv run pytest tests/e2e/ -v
docker compose -f docker-compose.test.yml down -v
```

### 7. 結果報告

テスト結果をユーザーに報告する：

- パスしたテスト数 / 全テスト数
- カバレッジ概要（`--cov` で取得）
- 要件に対するテストカバレッジの説明
- 該当する場合、要件の「テスト完了」ステータスをチェック

---

## 付録 A: Repository モックパターン（参考・別プロジェクト用）

> **本プロジェクトでは採用しない**。Repository レイヤを採用する別プロジェクトで参照するためのテンプレートとして残してある。本プロジェクトでこのパターンを生成しないこと。

<!--
### Service が Repository を持つ 2 層構成での単体テスト

```python
import pytest
from unittest.mock import AsyncMock
from uuid import uuid4

from app.services.problems import ProblemsService
from app.core.exceptions import NotFoundError


@pytest.fixture
def mock_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_session() -> AsyncMock:
    session = AsyncMock()
    session.begin.return_value.__aenter__.return_value = None
    session.begin.return_value.__aexit__.return_value = None
    return session


@pytest.fixture
def service(mock_session: AsyncMock, mock_repo: AsyncMock) -> ProblemsService:
    s = ProblemsService(mock_session)
    s.repo = mock_repo  # repository を差し替え
    return s


class TestProblemsServiceFindOne:
    @pytest.mark.asyncio
    async def test_正常系_詳細取得(self, service: ProblemsService, mock_repo: AsyncMock) -> None:
        problem_id = uuid4()
        mock_repo.get_by_id.return_value = ...
        result = await service.get_problem(problem_id)
        assert result.id == problem_id

    @pytest.mark.asyncio
    async def test_異常系_存在しないIDでNotFound(self, service: ProblemsService, mock_repo: AsyncMock) -> None:
        mock_repo.get_by_id.return_value = None
        with pytest.raises(NotFoundError):
            await service.get_problem(uuid4())
```

### Repository モックの使い方

```python
# 単純な戻り値
mock_repo.list_problems.return_value = [problem1, problem2]

# 例外を raise
mock_repo.get_by_id.side_effect = NotFoundError("not found")

# call_args で引数検証
mock_repo.create.assert_called_once_with(payload, owner_id=user.id)
```

このパターンが有効な前提：
- Repository が独立クラスで存在する
- ORM 挙動の再現性より「Service ロジックの分岐網羅」を優先したい
- 結合テスト基盤（Testcontainers / docker-compose）の整備コストが高い案件
-->

