# UserRepository: users テーブルへの SQLAlchemy クエリだけを置く層。
#
# ADR 0044 の方針：
#   - SQLAlchemy の select / insert / update を呼ぶ実装はここに集約
#   - 戻り値は **ORM オブジェクト**（Pydantic への詰め替えは Service で行う）
#   - 認可チェック・トランザクション境界・ビジネスロジックは持たない

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.users import User


class UserRepository:
    """users テーブルのクエリ実装。"""

    # __init__: AsyncSession を Service から受け取って保持する。
    #   FastAPI の Depends から get_async_session で払い出された 1 リクエスト分の
    #   セッションを Service が DI で渡す。
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, id_: UUID) -> User | None:
        """主キーで 1 件取得。存在しなければ None。"""
        stmt = select(User).where(User.id == id_)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, *, display_name: str, email: str | None) -> User:
        """新規ユーザーを作って flush し、id / created_at が埋まった ORM を返す。

        commit はしない（Service 側がトランザクション境界を握る、ADR 0044）。
        """
        user = User(display_name=display_name, email=email)
        self.session.add(user)
        # flush:
        #   ここで「未確定のまま」DB に SQL を送る。INSERT が走り、サーバ既定値
        #   （id = gen_random_uuid() / created_at = NOW()）が決まって user に
        #   反映される。commit はしない＝同じトランザクション内で続けて
        #   auth_providers への INSERT を同期実行できるようにする。
        await self.session.flush()
        return user

    async def update_profile(
        self,
        *,
        user_id: UUID,
        display_name: str,
        email: str | None,
    ) -> User | None:
        """再ログイン時に display_name / email を最新値で上書きし、更新後の
        User ORM を返す。該当行が無ければ None。

        - authentication.md §2.1：「再ログイン時は GitHub の最新値で上書き」
        - updated_at は手で now に更新（onupdate を SQLAlchemy 側に書く方式もあるが
          現状のモデルは server_default のみのため、ここで明示的に渡す）
        - returning(User) で「UPDATE + SELECT」を 1 クエリにまとめる
          （別途 get_by_id を呼ぶ無駄なラウンドトリップを避ける）
        - commit はしない（Service 側）
        """
        stmt = (
            update(User)
            .where(User.id == user_id)
            .values(
                display_name=display_name,
                email=email,
                updated_at=datetime.now(UTC),
            )
            .returning(User)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
