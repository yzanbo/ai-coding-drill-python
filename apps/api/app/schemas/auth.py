# このファイルの役割：
#   認証関連 API のリクエスト / レスポンス JSON の形を Pydantic で定義する SSoT。
#   FastAPI が response_model に渡された形を OpenAPI に書き出し、Frontend は
#   それを Hey API 経由で TypeScript 型に展開する（→ ADR 0006）。
#
# 関わる要件：
#   - docs/requirements/4-features/authentication.md §1.4「共通 API」/ §2.4「GitHub 固有 API」

# UUID: Python 標準。一意 ID の型注釈に使う。
from uuid import UUID

# BaseModel:  Pydantic の親クラス。継承するだけで JSON ⇄ Python の相互変換と
#             バリデーションが効くクラスになる。
# ConfigDict: Pydantic v2 のモデル設定用 TypedDict。型補完が効くので class Config より使いやすい。
# alias_generators.to_camel: snake_case → camelCase の自動変換ヘルパ（Pydantic v2 同梱）。
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


# UserResponse: GET /auth/me の戻り JSON の形。
#   要件側の JSON 例（authentication.md §1.4）：
#     { "id": "<uuid>", "displayName": "...", "email": "..." }
#   フィールド名は **camelCase**（JS 慣習）で外に出すが、SQLAlchemy の User モデル側は
#   snake_case（display_name）。両方を繋ぐため alias_generator=to_camel を使う。
class UserResponse(BaseModel):
    """現在ログイン中のユーザー情報。GET /auth/me が返す形。

    snake_case のモデル属性を camelCase で JSON 出力するよう alias を効かせる
    （Frontend の Hey API 生成型もそのまま camelCase になる）。
    """

    model_config = ConfigDict(
        # from_attributes=True:
        #   Pydantic に「dict だけでなく、オブジェクト属性（.id / .display_name 等）からも
        #   値を読み取ってよい」と許可する設定。
        #   `UserResponse.model_validate(user_orm)` のように SQLAlchemy モデルから
        #   直接組み立てられるようになる。
        from_attributes=True,
        # alias_generator=to_camel:
        #   snake_case の属性名から camelCase の alias を自動生成する。
        #   例：display_name → displayName。
        # populate_by_name=True:
        #   入力時には snake_case / camelCase の両方を受け付ける（テストでの組み立てを楽に）。
        # serialize_by_alias=True:
        #   model_dump() / JSON 出力時に alias 名（camelCase）で書き出す。
        #   FastAPI の response_model 経路でもこれが効き、API レスポンスは camelCase になる。
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
    )

    id: UUID
    display_name: str
    # email は GitHub から取得できないユーザー（公開設定オフ）も許容するため Optional。
    email: str | None = None


# UserSyncInput: AuthService 内部で GitHub 取得結果をまとめて渡すための DTO。
#   API レスポンスではなく Service 引数用なので alias 設定は不要（snake_case のまま）。
#   Repository / Service / Router でやり取りする際の型ヒントを揃える目的。
class UserSyncInput(BaseModel):
    """GitHub から取得したユーザー情報をまとめた内部 DTO。

    AuthService.upsert_from_github の引数に渡す。
    - provider_id : GitHub の id（数値）を str 化したもの
    - display_name: name → login のフォールバック後の表示名（authentication.md §2.1）
    - email       : 公開 email or None
    """

    provider_id: str
    display_name: str
    email: str | None = None


# CreatedSession: AuthService.login_with_github の戻り値。
#   Router 側がこの情報を使って Set-Cookie ヘッダーを組み立てる。
#   - sid        : セッション Cookie に入れる値
#   - csrf_token : CSRF Cookie に入れる値（HttpOnly なし）
#   - user       : /auth/me 相当の戻り JSON で再利用可能な形
class CreatedSession(BaseModel):
    """ログイン成功時に Router に返す結果のひとまとまり。"""

    sid: str
    csrf_token: str
    user: UserResponse


# ログイン後のリダイレクトクエリ。
# 値そのものに Pydantic は使わないが、コールバックのレスポンスを表す型として
# 受け入れ条件で出てくる「/login?auth_error=<種別>」のキーを集約しておく。
class AuthErrorKind:
    """/login?auth_error=<kind> で Frontend に渡す種別の列挙（文字列定数）。

    Frontend 側（Hey API 生成では拾わない）でトースト表示の出し分けに使う。
    本クラスは Pydantic モデルではなく単なる名前空間。
    """

    OAUTH_CANCELED = "oauth_canceled"
    OAUTH_FAILED = "oauth_failed"
    STATE_INVALID = "state_invalid"
