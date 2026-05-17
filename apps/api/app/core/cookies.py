# このファイルの役割：
#   セッション ID（sid）を Cookie に乗せる前に署名し、読み出し時に検証するヘルパ。
#
#   仕組み：
#     - 中身は CSPRNG で生成された不透明な sid（32 byte 相当）
#     - 署名は itsdangerous の URLSafeSerializer を使う
#       → Cookie 値は「sid.署名」の形になり、改ざんすると署名検証に失敗する
#     - 攻撃者が偽 sid を投げ込んでも署名段階で弾けるので、Redis に問い合わせる前に
#       早期 reject できる（DoS 緩和 + 余計な Redis 負荷回避）
#
#   なぜ署名するか（ADR 0047 / backend.md「認証：itsdangerous（セッション署名）」）：
#     - sid 自体は CSPRNG 32 byte で十分な不可推測性があるため、署名は本質的に必要ではない
#     - ただし「Cookie の値は不透明だがアプリ発行のものかを保証したい」という弱い同一性
#       検証として有用（Cookie の sid フィールドにゴミを入れる悪意のあるリクエストを
#       Redis 読み取り前に弾ける）
#
#   セッション本体は Redis に保存。Cookie に入るのは「sid + 署名」だけ。

from itsdangerous import BadSignature, URLSafeSerializer

from app.core.config import get_settings

# salt: 同じ秘密鍵を複数用途で使い分ける時のドメイン分離名。
#   例えば将来 CSRF Cookie にも署名を入れるなら別 salt を使う。
#   実装上は HMAC のメタ情報として混ぜ込まれる。
_SALT = "session-id"


def _serializer() -> URLSafeSerializer:
    """都度 Serializer を作る（秘密鍵を直接参照しないため一元化）。

    秘密鍵を本ファイル冒頭の import 時に固定すると、テストで .env を差し替えても
    旧鍵を保持してしまうため、呼び出しごとに Settings を取り直す方針にする。
    """
    settings = get_settings()
    return URLSafeSerializer(settings.session_signing_secret, salt=_SALT)


def sign_sid(sid: str) -> str:
    """sid に署名を付けて Cookie に乗せる値を返す。

    戻り値は ASCII の URL セーフ文字列。Cookie の Set-Cookie ヘッダーに
    そのまま入れられる。
    """
    return _serializer().dumps(sid)


def unsign_sid(signed_value: str) -> str | None:
    """Cookie の値から sid を取り出す。改ざん / 形式不正なら None。

    BadSignature を呼び出し側でハンドリングさせるより、None 返却で
    「未認証扱い」に揃えた方が deps/auth.py や CSRF middleware の分岐が
    シンプルになる。
    """
    if not signed_value or len(signed_value) > 1024:
        return None
    try:
        result = _serializer().loads(signed_value)
    except BadSignature:
        return None
    if not isinstance(result, str):
        return None
    return result
