---
name: backend-new-module
description: FastAPI モジュール（router / schema / service / repository）を規約通りにスキャフォールドする
argument-hint: "[feature-name] (例: notifications, ratings)"
---

# バックエンドモジュールのスキャフォールド

引数 `$ARGUMENTS` を機能名（単数形・スネークケース、例：`notification`）として解釈する。FastAPI ディレクトリ構成（→ [.claude/rules/backend.md](../../rules/backend.md)）に従い、機能別フラットでファイルを作成する。

> **Note：Repository レイヤの要否は実装着手時に再判断**（保留）。要件側の SSoT は [02-architecture.md: Backend API 設計スタイル](../../../docs/requirements/2-foundation/02-architecture.md#backend-apifastapi--python) で「Repository レイヤは設けない」と書かれており、本 SKILL の Service + Repository 2 層スキャフォールドと齟齬がある。R1 着手時に決着。Repository を設けない方針が確定したら `repositories/$ARGUMENTS.py` の生成と Service 内 `self.repo` 注入を削除し、Service が `AsyncSession` から SQLAlchemy を直接呼ぶ単層構成に変更する。

## 手順

1. [.claude/rules/backend.md](../../rules/backend.md) を読み、ディレクトリ構成・コーディング規約を確認する
2. 以下のファイルを作成する（既存があれば差分追加）

### 作成するファイル

```
apps/api/app/
├── models/$ARGUMENTS.py         # SQLAlchemy モデル（DB スキーマが必要な場合）
├── schemas/$ARGUMENTS.py        # Pydantic（Create / Update / Response / Query）
├── repositories/$ARGUMENTS.py   # SQLAlchemy クエリ集約
├── services/$ARGUMENTS.py       # ビジネスロジック
└── routers/$ARGUMENTS.py        # APIRouter（prefix + tags）
```

### 各ファイルの雛形

#### `routers/$ARGUMENTS.py`

```python
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps.db import get_async_session
from app.deps.auth import get_current_user
from app.models.users import User
from app.schemas.<ARGS> import <Args>Create, <Args>Response
from app.services.<ARGS> import <Args>Service

router = APIRouter(prefix="/<args>", tags=["<args>"])


@router.post("", response_model=<Args>Response, status_code=status.HTTP_201_CREATED)
async def create_<args>(
    payload: <Args>Create,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> <Args>Response:
    service = <Args>Service(session)
    return await service.create(payload, owner_id=current_user.id)
```

#### `schemas/$ARGUMENTS.py`（Pydantic）

```python
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class <Args>Create(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class <Args>Update(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)


class <Args>Response(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    created_at: datetime
    updated_at: datetime


class <Args>Query(BaseModel):
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=20, ge=1, le=100)
```

#### `services/$ARGUMENTS.py`

```python
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.<ARGS> import <Args>Repository
from app.schemas.<ARGS> import <Args>Create, <Args>Response

logger = logging.getLogger(__name__)


class <Args>Service:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = <Args>Repository(session)

    async def create(self, payload: <Args>Create, *, owner_id) -> <Args>Response:
        async with self.session.begin():
            obj = await self.repo.create(payload, owner_id=owner_id)
        return <Args>Response.model_validate(obj)
```

#### `repositories/$ARGUMENTS.py`

```python
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.<ARGS> import <Args>
from app.schemas.<ARGS> import <Args>Create


class <Args>Repository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, payload: <Args>Create, *, owner_id) -> <Args>:
        obj = <Args>(name=payload.name, owner_id=owner_id)
        self.session.add(obj)
        await self.session.flush()
        return obj
```

#### `models/$ARGUMENTS.py`（DB スキーマが必要な場合）

```python
from datetime import datetime
from uuid import UUID
from sqlalchemy import String, text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class <Args>(Base):
    __tablename__ = "<args>s"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    name: Mapped[str] = mapped_column(String, nullable=False)
    owner_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()"))
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()"))
```

### 準拠するルール（[.claude/rules/backend.md](../../rules/backend.md) より）

- **Router**：`APIRouter(prefix=..., tags=[...])` で prefix と Swagger タグを必ず付ける。`response_model` を必ず明示。認証必須が既定（`dependencies=[Depends(get_current_user)]` を APIRouter で適用、public は `dependencies=[]` で上書き）
- **Pydantic**：命名は `<Args>Create / Update / Response / Query`。レスポンス用は `model_config = ConfigDict(from_attributes=True)` で SQLAlchemy モデルから組み立て可
- **Service**：トランザクション境界は Service が握る（`async with session.begin():`）。Repository を呼んでビジネスロジックを構築。直接 SQLAlchemy を呼ばない
- **Repository**：SQLAlchemy クエリの集約。戻り値はモデルのまま。Service / Router 側で Pydantic に詰め替える
- **エラー**：`HTTPException` ではなくドメイン例外を投げ、`app/core/exceptions.py` の handler で HTTPException に変換。メッセージは日本語
- **ハードデリート方針**（必要に応じて検討）

3. `apps/api/app/main.py` で router を登録：

```python
from app.routers import <args>

app.include_router(<args>.router)
```

4. **DB スキーマが必要な場合**：
   - `apps/api/app/models/$ARGUMENTS.py` を作成（上記雛形）
   - `mise run api:db-revision -- "add <args> table"` でマイグレーション雛形生成
   - 生成された Alembic revision を確認・微修正してコミット
   - 適用：`mise run api:db-migrate`
   - 詳細は [.claude/rules/alembic-sqlalchemy.md](../../rules/alembic-sqlalchemy.md)

5. **HTTP API 境界 / Job キュー境界の artifact 更新**（→ [ADR 0006](../../../docs/adr/0006-json-schema-as-single-source-of-truth.md)）：
   - 新規ルート追加 → `mise run api:openapi-export` で `apps/api/openapi.json` を更新 → Web 側は `mise run web:types-gen` で TS / Zod / HTTP クライアント再生成
   - 新規ジョブペイロード型 → `app/schemas/jobs/<job_type>.py` の Pydantic を追加 → `mise run api:job-schemas-export` → Worker 側は `mise run worker:types-gen` で Go struct 再生成

6. 作成したファイルの一覧をユーザーに提示する

7. ユーザーがこの後 `/backend-implement $ARGUMENTS` で実装に進められる旨を伝える
