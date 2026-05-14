# このファイルの役割：
#   pytest が「conftest.py」というファイル名を**予約名**として扱う特別なファイル。
#   tests/ 配下に置くと、その配下のすべてのテストから参照できる「共有フィクスチャ置き場」になる。
#   テスト関数の引数に書くだけで pytest が自動で値を注入してくれる（import 不要）。
#
#   ファイル名自体は pytest の決まり、中身は自前で書く（プロジェクト固有のフィクスチャを並べる）。

# AsyncIterator: 「非同期で 1 個ずつ値を渡せる関数」の戻り値型（Python 標準 / collections.abc）。
#                yield を使う非同期ジェネレータ関数の型注釈に使う。
from collections.abc import AsyncIterator

# pytest: テストフレームワーク本体。@pytest.fixture デコレータを提供。
import pytest

# ASGITransport: httpx 用の輸送層。「外部 HTTP を介さず、ASGI アプリ（FastAPI 等）に
#                直接リクエストを流す」役割。テスト時にサーバ起動なしでアプリを叩ける。
# AsyncClient:   httpx の非同期 HTTP クライアント。本番コードと同じ書き味でテストできる。
from httpx import ASGITransport, AsyncClient

# delete: DELETE 文を組み立てる SQLAlchemy の関数（SELECT の select() の DELETE 版）。
from sqlalchemy import delete

# AsyncSessionLocal: アプリ全体で使う「セッションを作る工場」（中身は app/db/session.py）。
#                    テスト中にも DB に直接アクセスしたい時はここからセッションを作る。
from app.db.session import AsyncSessionLocal

# app: FastAPI アプリ本体（中身は app/main.py）。テストではこれを ASGITransport に渡して叩く。
from app.main import app

# HealthCheck: health_check テーブルに対応する SQLAlchemy モデル
#              （中身は app/models/health_check.py）。
from app.models import HealthCheck


# デコレータとは：
#   関数やクラスの直前に `@xxx` と書いて、その関数 / クラスに**追加機能を付与する**書き方。
#   関数本体には手を入れず、外側から機能を足せるのが利点。
#
#   例（このプロジェクトで頻出）：
#     @router.post("/...")   → 関数を「HTTP エンドポイント」として登録（FastAPI）
#     @pytest.fixture        → 関数を「フィクスチャ」に変身（pytest）
#     @lru_cache             → 関数の結果をキャッシュ（Python 標準）
#     @field_validator       → 関数を Pydantic のバリデータとして登録
#
#   裏で起きていること（@xxx は糖衣構文で、以下と同じ）：
#     @some_decorator                ↔︎    def my_func(): ...
#     def my_func(): ...                   my_func = some_decorator(my_func)
#   ＝「関数を受け取って、装飾済みの関数を返す関数」がデコレータ。
#
#   他言語の同類：TypeScript の @decorator / Java の @Override 等のアノテーション /
#                C# の [Attribute] と同じ役割。
#
# @pytest.fixture（pytest が提供）:
#   関数をテスト用の「フィクスチャ」に変えるデコレータ。
#
#   フィクスチャとは：
#     「テストに必要な前準備・値の提供・後片付けを 1 つの関数にまとめて、複数のテストで使い回せる
#       ようにした仕組み」。
#     テスト関数の引数に同名で書くだけで pytest が自動で実行・注入してくれる。
#
#   フィクスチャの 3 つの役割：
#     1. 前準備（初期化処理）: DB クリア / ファイル作成 / 外部 API モック設定など、
#                              テスト前にやる副作用
#     2. 値の提供:            テスト関数の引数に Python オブジェクトを渡す
#                              （AsyncClient / Session / モック等）
#     3. 後片付け:            テスト終了後にリソース解放（yield の後ろに書く）
#     ※ 1 つのフィクスチャは 1〜3 の役割を任意に組み合わせられる
#        （例：client は「2 値の提供」のみ、reset_health_check_table は「1 前準備」のみ）
#
#   挙動：
#     - 引数に同名のフィクスチャを書いたテスト関数が pytest 起動時に発見される
#     - pytest が自動でこの関数を呼んで、戻り値 / yield 値をテスト関数に渡す
#     - yield を使うと、yield より前が「前準備」、yield より後が「後片付け」になる
#       （pytest が自動で yield の後ろまで進めてくれる）
#
#   スコープ：デフォルトは "function"（テスト関数 1 個ごとに毎回呼ばれる）。
#            @pytest.fixture(scope="session") にすると全テスト共有で 1 回だけになる。
@pytest.fixture
# reset_health_check_table（自作フィクスチャ）:
#   各テストの前に health_check テーブルを空にする「お掃除フィクスチャ」。
#   引数に reset_health_check_table を書いたテスト関数は、実行前に必ずこのフィクスチャが走る。
# -> AsyncIterator[None]:
#   yield を含む非同期関数なので戻り値型は AsyncIterator。None なのは yield に値を渡さないため。
async def reset_health_check_table() -> AsyncIterator[None]:
    """各テスト前に health_check テーブルを空にする。

    integration テストは実 DB を使うため、テスト間の独立性を保つために
    fixture で前処理する。新しいテーブルが追加されたら本 fixture を拡張するか、
    機能ごとに別 fixture を切り分ける。
    """
    # async with AsyncSessionLocal() as session:
    #   テスト用に新しい DB セッションを 1 個作る。ブロックを抜ける時に自動で片付く。
    async with AsyncSessionLocal() as session:
        # delete(HealthCheck): DELETE FROM health_check の SQL を組み立てる（まだ実行しない）。
        # session.execute:     組み立てた DELETE 文を DB に発行して実際に削除する。
        await session.execute(delete(HealthCheck))
        # session.commit: 削除を確定する。commit しないとテストから見えない状態のまま破棄される。
        await session.commit()
    # yield:
    #   ここで一時停止して、テスト関数に制御を渡す（前準備完了の合図）。
    #   値を渡さない（None）ので、テスト関数の引数には実質「合図だけ」が入る。
    #   yield の後ろに書けば後片付けにできるが、ここでは前処理だけなので何も書いていない。
    yield


@pytest.fixture
# client（自作フィクスチャ）:
#   テスト用の「アプリ直結 HTTP クライアント」を提供するフィクスチャ。
#   テスト関数の引数に client: AsyncClient と書けば、すぐに client.get("/...") が叩ける。
# -> AsyncIterator[AsyncClient]:
#   yield で AsyncClient を渡すので、戻り値型は AsyncIterator[AsyncClient]。
async def client() -> AsyncIterator[AsyncClient]:
    """ASGI in-process クライアント（外部 HTTP 不要）。"""
    # ASGITransport(app=app):
    #   「FastAPI アプリ（app）に直接リクエストを流す輸送層」を作る。
    #   実サーバ（uvicorn 起動 + TCP 通信）を介さないので、テストが軽くて速い。
    transport = ASGITransport(app=app)
    # async with AsyncClient(...) as ac:
    #   この transport を使う非同期 HTTP クライアントを 1 個作る。
    #   base_url="http://testserver": 相対パス（"/healthz" 等）の解決用ダミーホスト。
    #                                 ASGI 直結なので実際の通信先にはならない。
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        # yield ac: テスト関数に AsyncClient を渡して一時停止。
        #           テスト関数が終わると async with の終了処理でクライアントが片付く。
        yield ac
