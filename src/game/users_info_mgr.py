
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
    async def create_new_user(self) -> UserInfo:
        user_model = UserInfoSchema()
        user_model.name = "tressette player"
        user_model.gold = 0
        user_model.level = 1

        async with PsqlOrm.get().session() as session:
            session.add(user_model)
            await session.commit()
            return user_model

    async def get_user_info(self, uid: int) -> UserInfo:
        # redis_cache.clear_cache()
        # First get from Redis cache
        # If not found, get from Postgres and cache it
        cache_key = 'user' + str(uid)
        cached_user_info = None #redis_cache.get_from_cache(cache_key)
        if cached_user_info:
            logger.info("Cache hit")
            user_info_data = json.loads(cached_user_info)
            return UserInfo(**user_info_data)
        async with PsqlOrm.get().session() as session:
            user_info = await session.get(UserInfoSchema, uid)
            if user_info:
                user_info_data = {
                    "uid": user_info.uid,
                    "name": user_info.name,
                    "gold": user_info.gold,
                    "level": user_info.level
                }
                #redis_cache.set_to_cache(cache_key, json.dumps(user_info_data))
                return UserInfo(**user_info_data)
            return user_info


users_info_mgr = UsersInfoMgr()