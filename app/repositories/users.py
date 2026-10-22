from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import UserModel


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create(self, telegram_id: int) -> UserModel:
        result = await self._session.execute(
            select(UserModel).where(UserModel.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        if user is not None:
            return user
        user = UserModel(telegram_id=telegram_id)
        self._session.add(user)
        await self._session.flush()
        return user
