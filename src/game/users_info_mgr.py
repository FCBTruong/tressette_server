
import json
import logging
# from src.cache import redis_cache
from src.game.models import UserInfo
from src.postgres.sql_models import UserInfoSchema
from src.postgres.orm import PsqlOrm

logging.basicConfig(
    level=logging.INFO,  # Set logging level
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",  # Log format
)
logger = logging.getLogger("user_info_mgr")  # Name your logger

class UsersInfoMgr:
    users : dict[int, UserInfo] = {} # Store user info in memory for quick access uid -> UserInfo
    async def create_new_user(self) -> UserInfo:
        user_model = UserInfoSchema()
        user_model.name = "tressette player"
        user_model.gold = 0
        user_model.level = 1

        async with PsqlOrm.get().session() as session:
            session.add(user_model)
            await session.commit()
            return user_model
        
    async def remove_cache_user(self, uid: int):
        self.users.pop(uid, None)

    async def get_user_info(self, uid: int) -> UserInfo:
        # cache_key = 'user' + str(uid)
        cached_user_info = self.users.get(uid)
        if cached_user_info:
            return cached_user_info
        async with PsqlOrm.get().session() as session:
            user_info = await session.get(UserInfoSchema, uid)
            if user_info:
                user_info_data = {
                    "uid": user_info.uid,
                    "name": user_info.name,
                    "gold": user_info.gold,
                    "level": user_info.level,
                    "avatar": user_info.avatar,
                }
                user_inf = UserInfo(**user_info_data)
                self.users[uid] = user_inf
                return user_inf
            return user_info


users_info_mgr = UsersInfoMgr()