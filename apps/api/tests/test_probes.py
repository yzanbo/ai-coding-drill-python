"""liveness probe (/healthz) 専用テスト。

liveness probe とは「プロセスが生きているか」だけを確認する軽量エンドポイントで、
DB や外部サービスへの接続可否は判定対象に含めない（それらは readiness probe の責務）。
そのため /healthz は DB 未接続でも 200 を返す設計になっており、本テストも DB を一切触らない。

  補足：liveness と readiness の使い分けは Kubernetes 等のオーケストレータ前提の概念で、
  liveness が落ちる = プロセス再起動、readiness が落ちる = ロードバランサから一時切り離し、
  という別アクションに繋がる。DB 一時切断で liveness を落とすと無意味な再起動ループに
  陥るため、/healthz は依存先を見ない「最も浅い生存確認」に留める。依存先まで含めた
  健全性確認は別途 /readyz（readiness probe）として分離する想定。

マーカーについて：本ファイルには `@pytest.mark.<name>` を一切付けていない。
test_health.py には `@pytest.mark.integration` が付いているため、対比で「なぜ probes
だけマーカー無し？」と疑問に思われやすい。理由は以下：

  前提：`integration` は pytest 組み込みのマーカーではなく、本リポジトリの
  pyproject.toml で「Postgres が必要」と定義したプロジェクト固有マーカー。
  マーカー名で外部依存テストを分類するのは業界でよくあるパターンだが、普遍的な
  慣習ではなく（ディレクトリ分けや fixture 判定で区別する流派もある）、本リポ
  ジトリのローカルルールとして採用しているに過ぎない。

  現状定義済みのマーカーは `integration` 1 種類のみで、意味は「Postgres が必要」。
  /healthz は DB を触らないので `integration` を付ける理由が無く、結果として
  マーカー無しになっている。

  注意：「DB 不要 ＝ マーカー無し」を **設計原則として決めているわけではない**。
  あくまで現状のマーカー定義が 1 種類しかないための結果論で、将来 `unit` や
  `slow` 等が追加されれば、DB 不要な本テストにも別のマーカーが付く可能性は
  ある（その際は pyproject.toml の markers と合わせて見直すこと）。

  整備予定：backend.md ではテストを `tests/unit/` / `tests/integration/` /
  `tests/e2e/` のディレクトリ分けで運用する方針を掲げているが、R0 段階の
  現状はフラットな `tests/` + `integration` マーカー併用で過渡期にある。
  今後ディレクトリ分け運用に移行する際は、マーカー方針もそれに合わせて
  整理し直す予定（→ .claude/rules/backend.md「テスト」節）。

実行タイミング：pre-push フック（lefthook）は `uv run pytest` をマーカー絞り込み
無し（`-m <名前>` 未指定）で叩くため、マーカーの有無に関わらず全テストが対象になる。
本ファイルは DB 非依存なので、docker compose 未起動でも常に pass する。
"""

# AsyncClient: 非同期で HTTP リクエストを投げるためのクライアント。
#              テストでは FastAPI アプリに直接ぶら下げて、実サーバを起動せずに叩く。
from httpx import AsyncClient


# client: conftest.py で用意した AsyncClient のフィクスチャ。
#         関数引数に書くだけで pytest が自動で渡してくれる（DB セッションは作らない）。
async def test_healthz_liveness_probe(client: AsyncClient) -> None:
    """DB 接続不要の liveness probe が 200 を返す。"""
    # get("/healthz"): 生存確認用エンドポイントを GET で叩く。DB には触らない。
    response = await client.get("/healthz")
    # status_code: HTTP ステータスコード。200 = 正常応答。
    assert response.status_code == 200
    # json(): レスポンスボディを Python の辞書に変換して取り出す。
    # {"status": "ok"}: routers/probes.py が返す固定値。
    assert response.json() == {"status": "ok"}
