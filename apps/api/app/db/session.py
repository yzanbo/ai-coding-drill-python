# AsyncIterator: 「非同期で 1 個ずつ値を渡せる関数」の戻り値型。
#                yield を使う非同期ジェネレータ関数の型注釈に使う。
from collections.abc import AsyncIterator

# SQLAlchemy の非同期 DB アクセス用部品（すべて SQLAlchemy が提供）：
# AsyncEngine:          DB との接続プールを管理する本体（アプリ全体で 1 個だけ作る）。
# AsyncSession:         DB と非同期でやり取りするセッションのクラス（リクエストごとに 1 個作る）。
# async_sessionmaker:   「セッションを作る工場」を作る関数。設定をまとめて固定し、毎回同じ
#                       設定の AsyncSession を作れるようにする。
# create_async_engine:  接続文字列から AsyncEngine を作る関数。
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# get_settings: .env や環境変数から読み込んだ設定をまとめて返す関数（中身は core/config.py）。
from app.core.config import get_settings


# _create_engine（自作・先頭 _ は「このファイル内だけで使う」印）:
#   AsyncEngine を 1 個だけ組み立てる関数。下のモジュールトップで 1 回呼ばれる。
#
# -> AsyncEngine: 返り値の型注釈（type hint）。
#   「この関数は AsyncEngine 型の値を返します」と人間 / IDE / 型チェッカ（pyright）に伝える宣言。
#   書き方は `def 関数名(引数: 型) -> 返り値の型:` の形。
#   Python は実行時には型を強制しない（動的型付けのまま）が、IDE 補完・型チェック・読みやすさ
#   のために書く。他言語で言えば TypeScript の `function f(): Type { }` や
#   Java の `Type f() { }` と同じ役割。
def _create_engine() -> AsyncEngine:
    # get_settings（自作 / core/config.py）:
    #   .env や環境変数から読み込んだ設定をまとめて Settings インスタンスとして返す関数。
    #   @lru_cache 付きなので 2 回目以降は同じインスタンスを即返す（再読込しない）。
    settings = get_settings()
    # create_async_engine（SQLAlchemy）:
    #   接続文字列とオプションから AsyncEngine（接続プールを内部に持つ DB アクセスの本体）
    #   を作る関数。ここで返す engine をモジュールトップで 1 回だけ作り、以後アプリ全体で使い回す。
    return create_async_engine(
        # database_url: 例 "postgresql+asyncpg://postgres:postgres@localhost:5432/ai_coding_drill"
        settings.database_url,
        # pool_pre_ping=True: 接続プールから取り出すたびに「生きてるか？」を軽く確認する設定。
        #                    DB が再起動した後の「死んだ接続を掴んで失敗」を防ぐ。
        pool_pre_ping=True,
    )


# engine: アプリ全体で 1 個だけ存在する DB エンジン（接続プールを内部に持つ）。
#         モジュール読み込み時に 1 回だけ作って、以後ずっと使い回す。
engine: AsyncEngine = _create_engine()

# AsyncSessionLocal: 「AsyncSession を作る工場」（プロジェクト固有の慣習名）。
#   bind=engine:          この工場で作るセッションは engine の接続プールを使う。
#   expire_on_commit=False: commit 後もオブジェクトの属性（record.id 等）にアクセスできる。
#                          True だと commit 後に属性が「期限切れ」扱いになり再取得が必要になるため、
#                          FastAPI のレスポンス整形（HealthCheckResponse 化）で困る。
#   class_=AsyncSession:   作るセッションのクラスを明示（async 用）。
AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


# get_async_session（自作・FastAPI + SQLAlchemy の定番パターン）:
#   FastAPI の Depends から呼ばれて、リクエスト 1 回分の DB セッションを作って渡し、
#   終わったら片付ける。
async def get_async_session() -> AsyncIterator[AsyncSession]:
    """FastAPI 依存性注入用：リクエスト単位で AsyncSession を生成・破棄する。

    使い方（Annotated 形式、B008 ruff 規約に準拠）：
        SessionDep = Annotated[AsyncSession, Depends(get_async_session)]

        @router.get("/...")
        async def handler(session: SessionDep):
            ...
    """
    # async with AsyncSessionLocal() as session:
    #   ① AsyncSessionLocal() で「工場」から AsyncSession を 1 個作る。
    #      内部で接続プールから接続を 1 本拝借し、それをくるんで session を組み立てる。
    #      この時点では DB に何も問い合わせていない（使う準備ができただけ）。
    #   ② async with: ブロックを抜ける時に自動で終了処理を実行
    #      （rollback 未確定変更 + 接続をプールへ返却）。
    async with AsyncSessionLocal() as session:
        # yield session:
        #   作った session を呼び出し元（FastAPI）に渡して、この関数を一時停止する。
        #   FastAPI は受け取った session を router 関数の引数に注入する。
        #   router 関数が終わったら、ここに制御が戻ってきて async with の終了処理が走る。
        #
        #   なぜ return ではなく yield なのか：
        #     return session と書くと、その瞬間に async with ブロックを抜けて session が
        #     即 close される。router 関数が使う前に無効になってしまう。yield なら
        #     「router 関数が使い終わるまで session を保持し、終わったら片付ける」を
        #     1 関数で実現できる。
        yield session
