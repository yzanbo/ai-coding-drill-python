# datetime: 日時を扱う Python 標準クラス。
from datetime import datetime

# UUID: 一意な ID（重複しない英数字の塊）を表す Python 標準の型。
from uuid import UUID

# BaseModel:  Pydantic の親クラス。これを継承すると「JSON ⇄ Python オブジェクト」の変換と
#             バリデーションが自動で効くクラスになる。
# ConfigDict: Pydantic v2 でモデル設定を書くための型（TypedDict）。型補完が効く。
from pydantic import BaseModel, ConfigDict


# HealthCheckResponse: GET/POST /health のレスポンス JSON の形を定義する Pydantic スキーマ。
#                      クライアントに返すフィールドだけをここに列挙する（公開リスト）。
class HealthCheckResponse(BaseModel):
    # dict（辞書）: Python 標準のデータ型。{ "キー": 値, ... } の形でキー → 値のペアを持つ。
    #               例：{"id": "a3f8...", "created_at": "2026-..."}
    #               他言語の「ハッシュマップ」「連想配列」「オブジェクトリテラル」と同じ概念。
    #               JSON との相性が良く、API リクエスト/レスポンスの中身は通常 dict で表現される。
    #
    # model_config = ConfigDict(from_attributes=True):
    #   Pydantic に「dict だけでなく、オブジェクトの属性（.id / .created_at）からも
    #   値を読み取ってよい」と許可する設定。
    #   これが無いと SQLAlchemy モデル → Pydantic スキーマの自動変換ができない。
    #
    #   3 要素の役割：
    #     - model_config:        Pydantic v2 の予約名。これに値を入れるとモデル全体の設定になる。
    #     - ConfigDict:          Pydantic が提供する設定用の型（型補完用）。
    #     - from_attributes=True: 属性アクセスでも値を取り出してよいというフラグ。
    #
    #   なぜ必要か：
    #     FastAPI が response_model=HealthCheckResponse 指定時に、内部で
    #       HealthCheckResponse.model_validate(record)   # record は SQLAlchemy の HealthCheck
    #     を呼ぶ。record は dict ではなくオブジェクト（record.id / record.created_at）なので、
    #     このフラグが無いと「dict じゃない」と ValidationError になる。
    #
    #   Pydantic v1 → v2 の改名：
    #     v1 では `class Config: orm_mode = True` だった。v2 で「ORM 専用ではなく汎用に
    #     属性アクセスを許可する」意図を反映して `from_attributes` に改名された。
    model_config = ConfigDict(from_attributes=True)

    # id / created_at: HealthCheck（DB モデル）と同名のフィールドだけを取り出して公開する。
    #                  DB モデル側に内部フィールドが増えても、ここに書かなければ JSON には載らない。
    id: UUID
    created_at: datetime
