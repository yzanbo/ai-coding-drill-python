# Annotated: 型に追加情報を載せるための書き方。Annotated[型, 追加情報] の形で使う。
from typing import Annotated

# APIRouter: URL をグループ単位でまとめる箱。
# Depends:   リクエストごとに必要なもの（DB セッション等）を関数の引数に自動で渡す仕組み。
from fastapi import APIRouter, Depends

# select: DB から取り出す SQL を組み立てる関数（実行はまだしない）。
from sqlalchemy import select

# AsyncSession: DB と非同期でやり取りするためのセッション（DB との 1 回分の会話の入れ物）。
from sqlalchemy.ext.asyncio import AsyncSession

# get_async_session: リクエストごとに DB セッションを作って渡し、終わったら閉じる関数。
#                    中身は db/session.py。
from app.db.session import get_async_session

# HealthCheck: health_check テーブルに対応する Python クラス。中身は models/health_check.py。
from app.models import HealthCheck

# HealthCheckResponse: 返す JSON の形を定義したクラス。中身は schemas/health.py。
from app.schemas.health import HealthCheckResponse

# DB まで実際にアクセスする疎通確認用のエンドポイント。
#
# POST /health: health_check テーブルに 1 行追加して、追加した行を返す。
# GET  /health: 直近 10 件を新しい順に返す。
#
# プロセスが生きているかだけを返す軽量版は /healthz（routers/probes.py）。
# DB が一時的に落ちてもコンテナが再起動の嵐にならないよう、用途を分けてある。
#
# 設計メモ：
# health は INSERT 1 行 / SELECT 1 行と単純なので、本来挟むはずのサービス層
# （ビジネスロジック専用のファイル）を作らずに router の中で直接 DB を触る。
# 実機能（auth / problems 等）からは services/<機能名>.py を作って分離する。

# APIRouter（FastAPI が提供）:
#            URL をグループ単位でまとめる箱。複数のエンドポイントを 1 つの router に登録し、
#            main.py で app.include_router(router) する流れ。prefix と tags をここで決める。
# APIRouter(prefix="/health", tags=["health"]):
#   - prefix: このファイル内のすべてのルートの URL 先頭。@router.post("") は POST /health になる。
#   - tags:   /docs（Swagger UI）の見出し（ドキュメント上のグループ名）。
router = APIRouter(prefix="/health", tags=["health"])

# SessionDep: 「リクエストごとに DB セッションを差し込む」型を 1 回だけ書くためのエイリアス。
#             関数引数に session: SessionDep と書けば、毎リクエスト新しいセッションが渡り、
#             終了時に自動で閉じられる。
#
# SessionDep と AsyncSession の違い：
#   - AsyncSession: **値そのものの型**（DB セッションオブジェクト、SQLAlchemy のクラス）。
#   - SessionDep:   **「型 + 取り出し方」をセットにしたエイリアス**。
#                   → AsyncSession（値の型）＋ Depends(get_async_session)（値の作り方の指示）
#                     をひとまとめにしたラベル。
#
#   もし引数を `session: AsyncSession` と書くと、FastAPI は「型は分かったが、誰がこの値を
#   作るの？」となり session に値が入らない。`session: SessionDep` と書くことで「型は
#   AsyncSession、値は get_async_session() を呼んで作る」を 1 つの名前で伝えられる。
#   複数の router 関数で短く書き回すための略記としてここで定義している。
#
# Annotated[AsyncSession, Depends(get_async_session)] の中身（提供元込み）：
#   - Annotated         （Python 標準 / typing）:
#       型に追加情報を載せるための入れ物。Annotated[型, 追加情報] の形で使う。
#   - AsyncSession      （SQLAlchemy）:
#       session 引数に渡される値の型（DB と非同期でやり取りするためのセッション）。
#       ※「引数」は、下の create_health_check(session: SessionDep) の `session` 引数のこと。
#   - Depends           （FastAPI）:
#       値の取り出し方を FastAPI に指示する印。引数に書かれた関数を呼んで結果を渡す。
#   - get_async_session （このプロジェクトが自前で書いた関数 / db/session.py）:
#       実際に DB セッションを作って返す関数。FastAPI + SQLAlchemy の定番パターンで
#       プロジェクトに 1 個だけ用意し、全 router で使い回す。
SessionDep = Annotated[AsyncSession, Depends(get_async_session)]


# HealthCheck / HealthCheckResponse / response_model の役割分担：
#   - HealthCheck         （SQLAlchemy モデル）: DB の 1 行を表す Python オブジェクト
#   - HealthCheckResponse （Pydantic スキーマ）: クライアントに返す JSON の形
#   - response_model=...  （FastAPI の引数）:    返り値を指定した形に整えてから JSON 化する指示
#
#   流れ：関数が HealthCheck を return → response_model が HealthCheckResponse の形に整える
#        → JSON にしてクライアントに返す。
#   なぜ 2 種類用意するか：DB モデルには外に出したくない内部情報（パスワードハッシュ等）が
#   紛れることがある。公開してよいフィールドだけを Response 側に定義し、response_model で
#   強制すると、うっかり漏洩を防げる。今回の HealthCheck は 2 列だけなので見た目は同じだが、
#   実機能テーブル（例：User）になるとフィルタ効果がはっきり出る。
#
# SQLAlchemy = Python の代表的な ORM（DB のテーブルを Python のクラスとして扱う仕組み）。
#              SQL を直接書かずに session.add() / select() などの Python コードで DB 操作できる。
#
# @router.post（FastAPI が提供）:
#                 上で作った APIRouter インスタンス（router）が持つメソッド。
#                 POST <prefix>/<path> でこの関数が呼ばれるよう登録するデコレータ。
#                 ※ router 自体は変数名で自由に付けられるが、APIRouter のインスタンスは
#                   FastAPI が提供するクラスなので .post / .get / .put 等のメソッドはすべて
#                   FastAPI 由来。
# response_model（FastAPI が提供）: 返す JSON の形を指定。指定したフィールドだけを取り出して
#                 JSON にし、それ以外は自動で除外される（余計な情報の漏洩防止）。
#                 /docs にも同じ形が表示される。
# HealthCheckResponse（Pydantic スキーマ / 自前定義）:
#                 返す JSON の形そのもの（id と created_at の 2 つだけ）。中身は schemas/health.py。
@router.post("", response_model=HealthCheckResponse)
# async def:           非同期関数。DB の応答を待っている間、他のリクエストを処理できる。
# create_health_check: 関数名。/docs の見出しや、自動生成される TS クライアントの関数名にもなる。
# session:             この関数の中で使う DB セッションを受け取る引数（名前は何でもよい）。
#                      DB セッション ＝ アプリと DB の「1 回分の会話の入れ物」。
#                      1 リクエスト ＝ 1 セッションで、その間に add / commit / select 等を行う。
#                      毎回 DB へ「こんにちは」せず、同じ接続を使い回して途中で失敗したら全部
#                      キャンセル（rollback）できる単位。
# SessionDep:          上で定義した型エイリアス。これを引数の型に書くと、リクエストごとに
#                      新しい DB セッションが自動で渡される。
# -> HealthCheck:      返り値の型（SQLAlchemy モデル ＝ DB の 1 行を表す Python オブジェクト）。
#                      この値が FastAPI の引数 response_model（指定値: HealthCheckResponse、
#                      これは Pydantic スキーマ ＝ 外向け JSON の形）でフィルタされ、
#                      最終的に JSON 化されてクライアントに返る。
async def create_health_check(session: SessionDep) -> HealthCheck:
    """DB に 1 行追加して、追加した行を返す。"""
    # HealthCheck(): クラス名の末尾に () を付けるとコンストラクタ呼び出しになり、
    #                HealthCheck クラスの実体（インスタンス）を 1 個作る。
    #                他言語の `new HealthCheck()` に相当
    #                （Python には new キーワードが無く、クラス名() だけで実体化する）。
    #                id と created_at は DB 側が自動で埋めるので引数なしで作れる。
    #                ここではまだメモリ上の値だけで、DB には何も書かれていない。
    record = HealthCheck()
    # session.add(record):
    #   record（HealthCheck インスタンス）をセッションに追加する。
    #   ＝「この record をあとで INSERT する予定」とセッション内の予約リストに載せるだけ。
    #   この時点では SQL は発行されず、DB はまだ何も知らない（commit で初めて実行）。
    #   通販で言えば「カートに入れた」状態（注文確定はまだ）。
    session.add(record)
    # session.commit() と session.execute() の違い：
    #   - execute(stmt): SQL を 1 本 DB に発行して実行する（注文書を 1 枚渡すイメージ）。
    #                    SELECT なら結果が即返る。INSERT / UPDATE / DELETE は実行はされるが
    #                    まだ「未確定の変更」状態。
    #   - commit():      これまで貯めた変更（add したもの / 書き込み execute したもの）を
    #                    まとめて確定する（会計を済ませるイメージ）。確定して初めて他の
    #                    接続から見え、ロールバックできなくなる。
    #   分かれている理由：複数の SQL を「全部成功 or 全部キャンセル」のひとまとまり
    #                    （トランザクション）として扱うため。
    #
    # session.commit(): 貯めた変更（add した record 等）をまとめて DB に送って確定する。
    #   id / created_at は models/health_check.py で server_default を指定済み：
    #     - id:         gen_random_uuid()  ← DB が UUID を自動生成
    #     - created_at: NOW()              ← DB が現在時刻を埋める
    #   Python 側で空欄のまま渡すと DB が DEFAULT 式を実行して埋める仕組み。
    #   （DB に任せる理由：ID 衝突・時計ズレを避け、生成元を 1 か所に集約するため）
    #   ※ この時点では DB 上にだけ値があり、Python 側の record には未反映
    #     → 次の refresh で取り戻す。
    await session.commit()
    # session.refresh: DB 側で埋まった id / created_at を Python 側の record に取り込む。
    #                  これをしないと返す JSON の id / created_at が空になる。
    await session.refresh(record)
    return record


# @router.get（FastAPI が提供）: APIRouter のメソッド。GET <prefix>/<path> として登録する。
# list[HealthCheckResponse]:    返り値がリストなので response_model も list[...] で包む。
@router.get("", response_model=list[HealthCheckResponse])
async def list_health_checks(session: SessionDep) -> list[HealthCheck]:
    """直近 10 件を新しい順に返す。"""
    # stmt: statement（SQL 文）の略。組み立てた SQL を入れる SQLAlchemy 慣習の変数名。
    #       select / update / insert / delete の戻り値を受ける変数として広く使われる
    #       （旧スタイルでは `query` と書く流派もあるが SQLAlchemy 2.0 系では stmt が主流）。
    # select(HealthCheck):          health_check テーブルから取り出す SQL の土台。
    # .order_by(...desc()):         created_at の降順（新しい順）に並べる。
    # .limit(10):                   先頭 10 件で打ち切る。
    # ※ この時点ではまだ SQL は実行されない（組み立てるだけ）。
    stmt = select(HealthCheck).order_by(HealthCheck.created_at.desc()).limit(10)
    # session.execute(stmt): 組み立てた SQL を実際に DB へ発行して結果を受け取る。
    #   役割：SQL 1 本を DB に渡して実行する（注文書を 1 枚渡すイメージ）。
    #   読み取り（SELECT）の場合：結果が即返ってきて result に入る。commit 不要。
    #   書き込み（INSERT/UPDATE/DELETE）の場合：実行はされるが「未確定の変更」状態。
    #                                          別途 commit() を呼ぶまで他の接続には見えない。
    #   commit との違い：execute は「SQL を 1 本実行」、commit は「貯めた変更を確定」。
    #                    複数の SQL を 1 つのトランザクションとして扱うため役割が分かれている。
    result = await session.execute(stmt)
    # result.scalars(): 結果の各行から 1 列目（HealthCheck オブジェクト）だけを取り出すイテレータ。
    #                   イテレータ ＝「1 個ずつ順番に取り出せる仕組み」を持ったオブジェクト。
    #                   この時点ではまだ中身を全部展開していない（回転寿司のレーンのイメージ。
    #                   皿が 1 枚ずつ流れてくるが、まだ取っていない状態）。100 万件あっても
    #                   メモリを節約しながら順に処理できるのが利点。
    # .all():           イテレータをまとめて取り出してリストにする（レーンの皿を全部取る）。
    # list(...):        FastAPI に渡しやすい普通の list に変換。
    return list(result.scalars().all())
