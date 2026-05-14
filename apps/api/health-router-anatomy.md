# `apps/api/app/routers/health.py` の構成要素

学習用ドキュメント：health router に登場するシンボルを「自作 / ライブラリ提供」に分類し、新機能追加時に何を自作する必要があるかを整理する。

対象ファイル：[apps/api/app/routers/health.py](./app/routers/health.py)

---

## 1. 自作（このプロジェクトで書いたもの）

### 1.1 別ファイルで定義して router で import するもの

| シンボル | 種類 | 定義場所 |
|---|---|---|
| `get_async_session` | 関数 | [apps/api/app/db/session.py](./app/db/session.py) |
| `HealthCheck` | SQLAlchemy モデルクラス | [apps/api/app/models/health_check.py](./app/models/health_check.py) |
| `HealthCheckResponse` | Pydantic スキーマクラス | [apps/api/app/schemas/health.py](./app/schemas/health.py) |

### 1.2 health.py 内で定義しているもの

| シンボル | 種類 | 役割 |
|---|---|---|
| `router` | 変数（`APIRouter` インスタンス） | このファイル内のルートをまとめる箱 |
| `SessionDep` | 型エイリアス | `Annotated[AsyncSession, Depends(get_async_session)]` の略記 |
| `create_health_check` | 関数（POST /health のハンドラ） | 1 行 INSERT して返す |
| `list_health_checks` | 関数（GET /health のハンドラ） | 直近 10 件を返す |
| `record` | ローカル変数 | INSERT する `HealthCheck` インスタンス |
| `stmt` | ローカル変数 | 組み立てた SELECT 文 |
| `result` | ローカル変数 | execute の戻り値 |

→ 計 **10 個** が自作。

---

## 2. ライブラリ提供（既製品）

### 2.1 Python 標準

| シンボル | 提供元 |
|---|---|
| `Annotated` | `typing` |
| `list` / `dict` 等の組み込み型 | Python 組み込み |

### 2.2 FastAPI

`fastapi` パッケージが提供する部品。

| シンボル | 種類 | 役割 |
|---|---|---|
| `APIRouter` | クラス | URL をグループ単位でまとめる箱。`main.py` で `include_router` する |
| `Depends` | 関数 | 引数に値を自動注入する仕組みの印（DB セッション / 認証ユーザ等） |
| `@router.post` / `@router.get` | `APIRouter` インスタンスのメソッド | エンドポイントを登録するデコレータ |
| `response_model=...` | デコレータのキーワード引数 | 返り値を指定形に整えてから JSON 化する指示 |

### 2.3 SQLAlchemy

`sqlalchemy` / `sqlalchemy.ext.asyncio` パッケージが提供する部品。

| シンボル | 種類 | 役割 |
|---|---|---|
| `select` | SQL 構築関数 | SELECT 文を組み立てる |
| `AsyncSession` | クラス | DB と非同期でやり取りするためのセッションの型 |
| `session.add` / `session.commit` / `session.refresh` / `session.execute` | `AsyncSession` のメソッド | DB 操作（追加 / 確定 / 取り直し / SQL 実行） |
| `.order_by` / `.limit` / `.desc()` | クエリビルダのメソッド | SELECT 文に並び順や件数制限を足す |
| `result.scalars()` / `.all()` | 実行結果のメソッド | 取得結果を取り出す |

---

## 3. 新機能追加時に自作が必要なもの

新しい機能（例：`/problems` エンドポイント）を追加するとき、**必ず自作する**のは以下：

| # | 何を | どこに |
|---|---|---|
| 1 | **SQLAlchemy モデルクラス** | `app/models/<feature>.py` |
| 2 | **Pydantic スキーマクラス**（`<Model>Create` / `<Model>Update` / `<Model>Response` / `<Model>Query`） | `app/schemas/<feature>.py` |
| 3 | **router 変数**（`APIRouter(prefix=..., tags=...)` でインスタンス化） | `app/routers/<feature>.py` |
| 4 | **router 関数**（`async def xxx(...)`、`@router.get/post/...` を付ける） | 同上 |
| 5 | **`include_router` 呼び出し** | `app/main.py` |

> **`/backend-new-module` スキル** が上記 3 点セット（model / schema / router）を雛形生成してくれる。

### 自作しなくてよいもの（共通基盤として 1 回作って使い回す）

| シンボル | 場所 | 備考 |
|---|---|---|
| `get_async_session` | `app/db/session.py` | プロジェクトに 1 個用意済み、全 router で使い回す |
| `SessionDep` | 各 router 内で定義 | 複数 router で使うなら共通モジュール（例：`app/deps/db.py`）に切り出してもよい |

### 自作不要（ライブラリが提供）

- FastAPI 部品：`APIRouter` / `Depends` / `response_model` / `@router.<verb>` 等
- SQLAlchemy 部品：`select` / `AsyncSession` / `session.*` メソッド群

---

## 4. `get_async_session` の解説

router で頻出する自作関数。FastAPI + SQLAlchemy の組み合わせでは**ほぼ全プロジェクトが同じ形で書く定型句**だが、フレームワーク標準ではなく自前で用意する必要がある。

### 4.1 実体

[apps/api/app/db/session.py](./app/db/session.py) で定義：

```python
async def get_async_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session
```

### 4.2 役割

**「リクエストごとに DB セッションを作って渡し、リクエスト終了時に閉じる」関数**。

| タイミング | やること |
|---|---|
| リクエスト受信時 | `AsyncSessionLocal()` で新しい `AsyncSession` を作る |
| `yield session` | router 関数に session を渡す（`with` ブロックで保持） |
| router 関数の終了後 | `async with` の終了処理で session を自動 close |

### 4.3 まず `yield` について

このコードを読むには Python の `yield` キーワードを知っておく必要がある。

**`yield` ＝「値を 1 個渡して、関数の途中で一時停止する」キーワード**。普通の `return`（関数を完全に終了する）と違い、**呼び出し元に値を渡したあと、後で続きから再開できる**。

```python
def normal():
    return "A"      # ← 値を返して関数終了。これ以降は実行されない

def with_yield():
    print("前")
    yield "A"       # ← 値を渡して一時停止
    print("後")     # ← 再開すると、ここから実行される
```

比喩で言うと：

| | 動き | 例え |
|---|---|---|
| `return` | 値を返して終了。もう戻ってこない | 「ハイどうぞ」と渡して立ち去る |
| `yield` | 値を渡して一時停止。後で続きを実行 | 「ちょっと預けるから使ってて」と渡して**待機** |

**`get_async_session` で `yield` を使う理由**：

`yield` のおかげで「セッションを**渡す**」と「セッションを**片付ける**」を 1 つの関数にまとめられる：

```python
async def get_async_session():
    async with AsyncSessionLocal() as session:
        yield session            # ← ここで一時停止 → router 関数に使わせる
        # ↑ router 関数が終わるとここに戻ってくる
    # ↑ async with の終了処理で session を片付ける（rollback + 接続返却）
```

もし `return session` にすると、その瞬間に `async with` ブロックを抜けて session が即破棄される → router 関数が使う前に無効になってしまう。`yield` なら「router 関数が使い終わるまで session を保持し、終わったら片付ける」を 1 関数で実現できる。

他言語との対応：

| 言語 | 似たキーワード |
|---|---|
| Python | `yield` |
| TypeScript / JavaScript | `yield`（generator） |
| C# | `yield return` |

### 4.4 使われ方

router 側では `Depends(get_async_session)` で参照する：

```python
SessionDep = Annotated[AsyncSession, Depends(get_async_session)]

async def create_health_check(session: SessionDep) -> HealthCheck:
    # ↑ session には毎リクエスト新しい AsyncSession が自動で入る
    session.add(...)
    await session.commit()
```

FastAPI が裏でやってくれる流れ：

```
1. リクエスト到着
2. FastAPI: 引数の型 SessionDep を覗き込み「Depends(get_async_session) で値を作れ」と読み取る
3. FastAPI: get_async_session() を呼び出す
4. get_async_session の中:
     - 接続プールから DB 接続を 1 本拝借し、それをくるんだ AsyncSession を作る（変数 session）
     - yield session で「この session を使ってください」と FastAPI に渡し、自分は一時停止する
5. FastAPI: 受け取った session を router 関数の引数（session）に差し込んで実行開始
6. router 関数: session.add / commit / execute 等で DB 操作
7. router 関数: 終了 → レスポンス返却
8. FastAPI: 「使い終わりました」と get_async_session の続きへ制御を戻す
9. get_async_session の中:
     - yield で止まっていた箇所から再開
     - async with の終了処理で未 commit を rollback、接続を**プールへ返却**（close ではなく返却）
```

ポイント：
- **作る** = 接続プールから接続を借りて `AsyncSession` を組み立てる（DB にはまだ問い合わせない）
- **yield** = 作った session を FastAPI に渡して関数を一時停止（router 関数が使い終わるまで待機）
- **戻ってくる** = `async with` の終了処理で session を片付ける（rollback + 接続返却）

### 4.5 なぜ「定型句」なのか

- FastAPI も SQLAlchemy も DB セッションの作り方を強制しない（疎結合）
- そのため**接続プールから新しいセッションを取り出して、終わったら返す**という橋渡しを自前で書く必要がある
- ただし書き方はほぼ固定（`async with ... yield`）なので、プロジェクトに 1 個用意して使い回すのが正解

### 4.6 自作の構成要素

`get_async_session` の中で使っている部品（こちらは SQLAlchemy 提供）：

| 部品 | 提供元 | 役割 |
|---|---|---|
| `create_async_engine` | SQLAlchemy | DB 接続プールを管理するエンジンを作る |
| `async_sessionmaker` | SQLAlchemy | 「セッションを作る工場」を作る関数 |
| `AsyncSession` | SQLAlchemy | 非同期セッションのクラス |
| `AsyncSessionLocal` | 自作（変数） | 上記工場のインスタンス（プロジェクト共通） |

`engine` と `AsyncSessionLocal` はモジュールトップで 1 回だけ作って、毎リクエストの `get_async_session()` 呼び出しで使い回す。

---

## 5. `SessionDep` の解説

router 関数の引数を短く書くための **型エイリアス**。`get_async_session` とセットで使う。

### 5.1 実体

[apps/api/app/routers/health.py](./app/routers/health.py) で定義：

```python
SessionDep = Annotated[AsyncSession, Depends(get_async_session)]
```

### 5.2 役割

「DB セッションを引数に差し込むための型」を 1 か所にまとめておくためのラベル。

router 関数の引数に書くと、リクエストごとに新しい `AsyncSession` が自動で渡される：

```python
async def create_health_check(session: SessionDep) -> HealthCheck:
    # ↑ session には毎リクエスト新しい AsyncSession が入る
    ...
```

### 5.3 `SessionDep` と `AsyncSession` の違い

| | `AsyncSession` | `SessionDep` |
|---|---|---|
| 種類 | 値そのものの型（SQLAlchemy のクラス） | 「型 + 取り出し方」をセットにしたエイリアス |
| 中身 | DB セッションオブジェクト | `Annotated[AsyncSession, Depends(get_async_session)]` |
| 引数に書くと | FastAPI は「型は分かったが、誰がこの値を作るの？」と困る | 「型は AsyncSession、値は get_async_session() で作る」と FastAPI に伝わる |

`session: AsyncSession` と書くだけでは不十分で、`Depends(...)` を添えて初めて FastAPI が値を作って渡してくれる。`SessionDep` はその両方をまとめた略記。

### 5.4 構成要素（提供元込み）

`Annotated[AsyncSession, Depends(get_async_session)]` の中身：

| 部品 | 提供元 | 役割 |
|---|---|---|
| `Annotated` | Python 標準（`typing`） | 型に追加情報を載せる入れ物。`Annotated[型, 追加情報]` の形 |
| `AsyncSession` | SQLAlchemy | 引数に渡される値の型 |
| `Depends` | FastAPI | 値の取り出し方を指示する印（中の関数を呼んで結果を引数に渡す） |
| `get_async_session` | 自作（`app/db/session.py`） | 実際に DB セッションを作る関数 |

### 5.5 配置の方針

現状は各 router ファイル内で定義しているが、複数 router で重複してきたら `app/deps/db.py` に切り出して共通化してもよい（[backend.md](../../.claude/rules/backend.md) の「横断的な部品は責務に近い場所に置く」方針）。

---

## 6. その他の自作ファイル

`apps/api/app/` 配下にある自作ファイル一覧と、それぞれの役割。

| ファイル | 役割 | 編集頻度 |
|---|---|---|
| [main.py](./app/main.py) | FastAPI アプリ本体 + router を束ねる | 新 router 追加時のみ |
| [core/config.py](./app/core/config.py) | 設定値（DB URL 等）を `.env` から読み込む共通モジュール | 設定項目追加時のみ |
| [db/base.py](./app/db/base.py) | 全 SQLAlchemy モデルの共通親クラス `Base` を定義 | ほぼ編集しない |
| [db/session.py](./app/db/session.py) | DB エンジン / セッション工場 / `get_async_session` | ほぼ編集しない |
| [models/health_check.py](./app/models/health_check.py) | `HealthCheck` テーブルの SQLAlchemy モデル | 新モデル追加時のみ |
| [schemas/health.py](./app/schemas/health.py) | `HealthCheckResponse` の Pydantic スキーマ | 新スキーマ追加時のみ |
| [routers/health.py](./app/routers/health.py) | `/health` エンドポイント（DB 往復付き） | 新エンドポイント追加時のみ |
| [routers/probes.py](./app/routers/probes.py) | `/healthz` エンドポイント（DB 不要の生存確認） | ほぼ編集しない |

### 6.1 `main.py` — アプリ本体

```python
from fastapi import FastAPI
from app.routers import health, probes

app = FastAPI(title="AI Coding Drill API")
app.include_router(probes.router)
app.include_router(health.router)
```

**役割**：FastAPI アプリのインスタンスを 1 個作り、各 router をぶら下げる。Uvicorn（起動コマンド）はこの `app` を見つけて起動する。

**新機能を追加した時にここに 1 行足す**のが基本：

```python
from app.routers import problems
app.include_router(problems.router)
```

| 部品 | 提供元 | 役割 |
|---|---|---|
| `FastAPI` | FastAPI（クラス） | アプリ本体。OpenAPI / Swagger UI / Redoc の自動生成も含む |
| `app.include_router` | FastAPI（メソッド） | 各 router を組み込む |
| `title="..."` | FastAPI | Swagger UI の見出しになる |

### 6.2 `core/config.py` — 設定値の共通モジュール

`.env` ファイル / 環境変数から設定値（DB URL 等）を読み込み、型付きで提供する。

```python
class Settings(BaseSettings):
    database_url: str = Field(default="postgresql+asyncpg://...")
    redis_url: str = Field(default="redis://localhost:6379/0")

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

**使い方**：

```python
settings = get_settings()
settings.database_url   # ← .env の DATABASE_URL（無ければデフォルト）
```

**ポイント**：
- `BaseSettings` を継承すると、フィールド名（小文字）と同名の環境変数（大文字）から自動で値が埋まる
- `@lru_cache` で 2 回目以降は再読込せず即返す
- 新機能で新しい設定（例：`OPENAI_API_KEY`）が必要になったらここにフィールドを追加する

| 部品 | 提供元 | 役割 |
|---|---|---|
| `BaseSettings` | pydantic-settings | 環境変数 / `.env` から自動でフィールドを埋める基底クラス |
| `Field` | Pydantic | デフォルト値や説明文を付ける |
| `lru_cache` | Python 標準（functools） | 結果をキャッシュ |

### 6.3 `db/base.py` — SQLAlchemy モデルの親クラス

```python
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    """全 SQLAlchemy モデルの共通親クラス。"""
```

**役割**：すべての SQLAlchemy モデルが継承する**親クラス**。

- Alembic（マイグレーションツール）が **`Base.metadata`** を見て「現状のテーブル定義」を把握する
- 新しいモデルを書くときは必ず `class MyModel(Base):` で継承する
- このファイル自体はほぼ編集しない（共通テーブル列を全テーブルに自動で付けたい時等にだけ拡張）

| 部品 | 提供元 | 役割 |
|---|---|---|
| `DeclarativeBase` | SQLAlchemy | モデルの親クラスの基盤 |
| `Base`（自作） | このプロジェクト | プロジェクト全体で使う共通親クラス |

### 6.4 `db/session.py` — DB エンジン / セッション

すでに §4 で詳しく解説済み。3 つの主要シンボル：

| シンボル | 提供範囲 | 役割 |
|---|---|---|
| `engine` | アプリ全体で 1 個 | 接続プールを内部に持つ |
| `AsyncSessionLocal` | アプリ全体で 1 個 | セッションを作る工場 |
| `get_async_session` | 各リクエストで呼ばれる | セッションを 1 個作って渡し、終わったら片付ける |

### 6.5 `models/<feature>.py` — SQLAlchemy モデル

DB のテーブル 1 つに対して Python クラスを 1 つ作る。`HealthCheck` の例：

```python
class HealthCheck(Base):
    __tablename__ = "health_check"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )
```

**役割**：

- DB の 1 テーブル ⇄ Python の 1 クラスの対応
- `Base` を継承して `__tablename__` を指定
- 各カラムを `Mapped[型]` + `mapped_column(...)` で定義
- `server_default` を付けると DB 側が空欄を埋めてくれる（UUID 自動生成 / 現在時刻等）

| 部品 | 提供元 | 役割 |
|---|---|---|
| `Mapped[型]` | SQLAlchemy | カラムの型注釈 |
| `mapped_column` | SQLAlchemy | カラムの定義（PK / nullable / デフォルト値等） |
| `UUID` / `TIMESTAMP` | SQLAlchemy（postgresql 方言） | Postgres 固有の型 |
| `text("...")` | SQLAlchemy | 生 SQL を埋め込む（`gen_random_uuid()` 等の DB 関数呼び出しに使う） |

新機能追加時はこのファイルを真似てモデルを書く。

### 6.6 `schemas/<feature>.py` — Pydantic スキーマ

API の境界で扱う JSON の形を定義する。`HealthCheckResponse` の例：

```python
class HealthCheckResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime
```

**役割**：

- HTTP リクエスト / レスポンスの形（外向け JSON）を定義する公開リスト
- SQLAlchemy モデルから「公開してよい列だけ」を抜き出して定義
- `from_attributes=True` で SQLAlchemy インスタンスからも自動変換可能になる

**命名規則**：機能ごとに `Create` / `Update` / `Response` / `Query` をスイートで作る（`/backend-new-module` スキルが雛形生成）：

```
ProblemCreate    # POST /problems のリクエスト body
ProblemUpdate    # PATCH /problems/{id} のリクエスト body
ProblemResponse  # 各エンドポイントのレスポンス JSON
ProblemQuery     # GET /problems のクエリパラメータ
```

| 部品 | 提供元 | 役割 |
|---|---|---|
| `BaseModel` | Pydantic | スキーマの親クラス |
| `Field` | Pydantic | デフォルト値 / 制約 / 説明文を付ける |
| `ConfigDict` | Pydantic | モデル設定を書く型 |
| `from_attributes=True` | Pydantic | SQLAlchemy インスタンスを受け取れるようにする |

### 6.7 `routers/probes.py` — 生存確認エンドポイント

```python
router = APIRouter(tags=["probes"])

@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
```

**役割**：

- **liveness probe**（プロセス生存確認）用の `/healthz` を提供
- DB / Redis 等の外部依存に**触らない**（依存先の一時障害でコンテナ再起動の嵐を防ぐため）
- Kubernetes / ALB が定期的に叩く想定

依存先まで含めた健全性確認は `routers/health.py` 側（`/health`）が担当する、という用途分け。

### 6.8 `routers/health.py` — DB 往復ありの疎通確認

このドキュメントの主対象（§1〜§5 で詳述）。

---

## 7. 全体図

```
[自作の 3 点セット]               [router 1 個]              [使うだけ]
SQLAlchemy モデル ────┐           ┌──── router 関数（複数）─┐
Pydantic スキーマ ────┼→ router 内で使う ─┤                ├→ ライブラリ提供
DB セッション関数（共通）           └──── ローカル変数        │   の部品で組み立てる
                                                            └→ get_async_session（共通）
```

新機能を作るたびに **「モデル + スキーマ + router」の 3 ファイル** を書くのが基本パターン。
