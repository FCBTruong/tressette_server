
from src.game.models.sql_models import UserInfo
from src.postgres.orm import PsqlOrm


class UsersInfoMgr:
    async def create_new_user(self) -> UserInfo:
        user_model = UserInfo()
        user_model.name = "tressette player"
        user_model.gold = 0
        user_model.level = 1

        async with PsqlOrm.get().session() as session:
            session.add(user_model)
            await session.commit()
            return user_model

    async def get_user_info(self, uid: int) -> UserInfo:
        async with PsqlOrm.get().session() as session:
            user_info = await session.get(UserInfo, uid)
            return user_info

users_info_mgr = UsersInfoMgr()