---
name: backend-test
description: 要件 .md に基づいて FastAPI のユニット / 結合テストを生成・実行する
argument-hint: "[<name>] (例: problem-generation, grading)"
---

# 要件ベースのバックエンドテスト生成・実行

引数 `$ARGUMENTS` を機能名として解釈する。

> **本プロジェクトでは Repository レイヤを採用する**（Service / Repository / ORM の 3 層分離、→ [ADR 0044](../../../docs/adr/0044-backend-repository-pattern-adoption.md) / [.claude/rules/backend.md](../../rules/backend.md)）。テスト戦略は「Service の単体テスト（Repository を `AsyncMock` でスタブ化）+ Repository の結合テスト（実 DB で SQL 挙動を検証）+ Router の結合テスト（実 Service / 実 Repository / 実 DB の end-to-end）」を組み合わせる。Repository を明示的なインタフェース境界として置く設計のため、Repository モックでも false positive を生まない。**Service の純粋関数を切り出して単体テストするパターン（Service 単層構成での代替）は別プロジェクト参考用に §付録 A にコメントとして残してある**。

## 手順

### 1. 要件と実装の読み込み

1. `docs/requirements/4-features/$ARGUMENTS.md` を読み込む
2. [.claude/rules/backend.md](../../rules/backend.md) のテスト規約を確認する
3. 対象モジュールの実装コードを読み込む：
   - `apps/api/app/services/$ARGUMENTS.py` — テスト対象のビジネスロジック（認可・分岐・Pydantic 詰め替え、→ [ADR 0044](../../../docs/adr/0044-backend-repository-pattern-adoption.md)）
   - `apps/api/app/repositories/$ARGUMENTS.py` — SQLAlchemy クエリの実装（Service の単体テストではモック、Repository 自体は実 DB で結合テスト）
   - `apps/api/app/routers/$ARGUMENTS.py` — エンドポイントの確認
   - `apps/api/app/schemas/$ARGUMENTS.py` — Pydantic スキーマ
   - `apps/api/app/models/$ARGUMENTS.py` — SQLAlchemy モデル

### 2. テスト方針の提示

以下をユーザーに提示し、承認を得てから次の手順に進む：

- テスト対象のサービス・メソッド一覧
- テストケースの概要（正常系・異常系・境界値）
- 単体テスト（純粋関数の切り出し検証）と結合テスト（実 DB + httpx でクエリ動作検証）の使い分け
- 生成するファイルの一覧

### 3. 要件 vs 実装 vs テストの事前判断（観測対象の整合を取る）

手順 2 の方針提示で**ユーザーと対話的に確定した観測対象**について、要件・実装・テストの 3 者間にズレがあれば、**どれを変えるべきかを工数を無視して純粋なメリット観点から判断**する。「要件 .md 更新ありき」では進めない。

判断軸（工数は度外視）：

- 観測対象が業務として正しい新しい受け入れ条件 → 要件 .md を更新（**受け入れ条件**節 / **バリデーション**節 に追加）
- 要件 .md の記述が既に正しく、実装の挙動だけがズレている → 実装側を直す（テストは要件通りに書く。**後方互換 NG**、最新状態に合わせて修正、→ CLAUDE.md「後方互換性について」）
- テスト方針側が要件・実装と噛み合わない（過剰な細粒度・観測不能な内部状態への依存等） → テスト方針を見直す

反映対象例（要件側を直す場合）：

- 機能要件 .md の**受け入れ条件**節（観測可能な境界値・異常系・状態遷移の追加）、必要なら**バリデーション**節（業務上の理由があるルール）にも追記
- 機械的検証（型・必須・最大長）は Pydantic / Zod 側が SSoT のため要件 .md には書かない（→ `_template.md` 冒頭の長期運用原則）

判断結果を反映してから手順 4 のテスト生成に進む。

### 4. ユニットテスト生成

`apps/api/tests/unit/test_$ARGUMENTS.py` を作成する。

#### テスト規約

- フレームワーク：pytest + pytest-asyncio（→ [ADR 0038](../../../docs/adr/0038-test-frameworks.md)）
- テスト関数名・docstring は日本語：`def test_正常系_一覧取得() -> None:` / `"""異常系: 存在しない ID で 404"""`
- **Service の単体テストでは Repository を `AsyncMock` でスタブ化**してビジネスロジック分岐（バリデーション・認可・計算・分岐・Pydantic 詰め替え）を網羅する（→ [ADR 0044](../../../docs/adr/0044-backend-repository-pattern-adoption.md)）
- SQLAlchemy セッションも `AsyncMock` でスタブ化（`session.begin().__aenter__` / `__aexit__` を `None` 返却に設定してトランザクション境界をパススルー）
- ファイル名：`tests/unit/test_<feature>.py`、機能あたり 1 ファイル

#### テスト構造（Repository を `AsyncMock` でスタブ化、ADR 0044）

```python
import pytest
from unittest.mock import AsyncMock
from uuid import uuid4

from app.services.problems import ProblemService
from app.core.exceptions import NotFoundError


@pytest.fixture
def mock_session() -> AsyncMock:
    session = AsyncMock()
    # async with session.begin(): を素通りさせる
    session.begin.return_value.__aenter__.return_value = None
    session.begin.return_value.__aexit__.return_value = None
    return session


@pytest.fixture
def mock_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(mock_session: AsyncMock, mock_repo: AsyncMock) -> ProblemService:
    s = ProblemService(mock_session)
    s.repo = mock_repo                        # 内部の Repository を差し替え
    return s


class TestProblemServiceGetById:
    @pytest.mark.asyncio
    async def test_正常系_詳細取得(
        self, service: ProblemService, mock_repo: AsyncMock
    ) -> None:
        problem_id = uuid4()
        mock_repo.get_by_id.return_value = SomeOrmObject(id=problem_id)  # ORM を返す
        result = await service.get_by_id(problem_id)
        assert result.id == problem_id

    @pytest.mark.asyncio
    async def test_異常系_存在しないIDでNotFound(
        self, service: ProblemService, mock_repo: AsyncMock
    ) -> None:
        mock_repo.get_by_id.return_value = None
        with pytest.raises(NotFoundError):
            await service.get_by_id(uuid4())
```

#### Repository モックの使い方

```python
# 単純な戻り値（ORM オブジェクトを返す）
mock_repo.list_all.return_value = [problem1, problem2]

# 例外を raise
mock_repo.get_by_id.side_effect = NotFoundError("not found")

# call_args で引数検証
mock_repo.create.assert_called_once_with(payload, owner_id=user.id)
```

> Service クラス内部の `self.repo` を `AsyncMock` で差し替えることで、SQLAlchemy 依存なしに Service のビジネスロジック分岐を網羅できる。Repository 自体の SQL 挙動は §4 結合テストで実 DB に対して検証する（責務分離の 2 段構成、→ [ADR 0044](../../../docs/adr/0044-backend-repository-pattern-adoption.md)）。

#### LLM プロバイダのモックパターン（将来）

LLM 呼び出しは Worker 側に閉じるため、Backend のテストには通常出てこない（→ [ADR 0040](../../../docs/adr/0040-worker-grouping-and-llm-in-worker.md)）。Backend の責務は enqueue + 結果取得なので、モックするのは NOTIFY 程度（必要時のみ）。

#### テストケースのカバレッジ目安

各サービスメソッドに対して：

- **正常系**：期待通りの結果が返ること
- **異常系（存在チェック）**：存在しないリソースで `NotFoundError`
- **異常系（権限チェック）**：他人のリソースで `ForbiddenError`
- **異常系（バリデーション）**：Pydantic バリデーション、ビジネスルール違反
- **境界値**：空配列、None、最大文字数、最小日付等

### 5. 結合テスト（router レベル）

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

### 6. テスト実行

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

### 7. E2E テスト（必要な場合）

重要なフロー（解答送信 → 採点 → 結果取得）は E2E でも検証する。詳細は [.claude/rules/backend.md](../../rules/backend.md) の「E2E テストの実行方法」を参照。

```bash
docker compose -f docker-compose.test.yml up -d
cd apps/api && uv run pytest tests/e2e/ -v
docker compose -f docker-compose.test.yml down -v
```

### 8. 要件 vs 実装 vs テストの事後判断（テストが暴いた差分を整える）

テスト生成・実行中に明らかになった差分は、**結果報告の前に**「要件 / 実装 / テスト のどれを直すか」を**工数を無視して純粋なメリット観点から判断**して解消する。テスト失敗を要件追従で機械的に丸めない。

判断軸（工数は度外視）：

- 実装の振る舞いが業務として正しい → 要件 .md を更新（受け入れ条件 / バリデーション節）。テストはその振る舞いを担保する形で残す
- 要件の記述が業務として正しい / 実装が要件から外れている → 実装を直す（**後方互換 NG**、最新状態に合わせて修正、→ CLAUDE.md「後方互換性について」）。テストは要件通りに通るのが正
- テスト自身が観測対象を取り違えていた → テスト側を直す

確認対象の差分例：

- **新たに見つかった観測可能な振る舞い**：境界値・異常系・状態遷移
- **業務上の制約として発見されたバリデーション**：「バリデーション」節候補（機械的検証は対象外）

軽微な追従はこのスキル内で直接更新してよい。差分の規模が大きい場合は `/update-requirements` で対話的に進める。

#### テスト・実装中のコミット粒度

- **適切な粒度で適宜コミット**する（このスキルの実行自体がユーザの明示指示として `git add` / `git commit` を許容する）。ユニットテスト / 結合テスト / fixture / 実装修正 / 要件更新は別コミットで区切る
- コミットメッセージは CLAUDE.md「コミットメッセージ」の規約（`<type>(<scope>): <subject>`、本文必須）。AI 生成文言（`Co-Authored-By` / `Generated with` 等）禁止
- `git push` / PR 作成はユーザの明示指示があるまで行わない

### 9. 結果報告

テスト結果をユーザーに報告する：

- パスしたテスト数 / 全テスト数
- カバレッジ概要（`--cov` で取得）
- 要件に対するテストカバレッジの説明
- 該当する場合、要件の「ユニットテスト完了」「E2E テスト完了」ステータスをチェック（`_template.md` 準拠の項目のみ、追加・削除はしない）

---

## 付録 A: Service 純粋関数切り出しパターン（参考・別プロジェクト用）

> **本プロジェクトでは採用しない**。Service 単層構成（Repository 不採用）を採る別プロジェクトで、SQLAlchemy 依存なしに Service ロジックを単体検証するためのテンプレートとして残してある。本プロジェクトの方針は [ADR 0044](../../../docs/adr/0044-backend-repository-pattern-adoption.md) に従い、本プロジェクトでこのパターンを生成しないこと。

<!--
### Service の純粋関数を切り出してユニットテストするパターン（Service 単層構成での代替手段）

Repository を採用しない場合、Service が直接 SQLAlchemy を呼ぶため `AsyncMock` でセッション全体をモックすると false positive を生みやすい。代わりに **ビジネスロジック部分を Service クラス外の純粋関数として切り出して**、その関数を直接テストする：

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

SQLAlchemy セッション・クエリが絡むメソッドは実 DB を使った結合テストで動作確認する。Service クラス全体をモックでテストせず、ロジック部分を関数として切り出してから単体検証する。

このパターンが有効な前提：
- Repository クラスを置かない単層構成
- Service が SQLAlchemy 2.0 を直接呼ぶ
- ORM 挙動の再現性を担保するため、SQLAlchemy 絡みは実 DB 結合テストに寄せたい案件
-->

