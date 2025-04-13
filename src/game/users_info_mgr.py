
from datetime import datetime
import json
import logging
# from src.cache import redis_cache
from src.base.network.packets import packet_pb2
from src.config.settings import settings
from src.game.models import UserInfo
from src.postgres.sql_models import UserInfoSchema
from src.postgres.orm import PsqlOrm
from src.game.cmds import CMDs
from src.constants import *

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
        if settings.DEV_MODE:
            if uid >= 2000000:
                user_info_data = {
                            "uid": uid,
                            "name": "tester",
                            "gold": 9999999,
                            "level": 1,
                            "avatar": '1',
                            "avatar_third_party": '',
                            "is_active": True,
                            "last_time_received_support": 0,
                            "received_startup": True,
                        }
                        
                user_inf = UserInfo(**user_info_data)
                user_inf.win_count = 0
                user_inf.game_count = 0
                user_inf.exp = 0
                user_inf.time_show_ads = 0
                user_inf.login_type = 0
            
                return user_inf
        
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
                    "avatar_third_party": user_info.avatar_third_party,
                    "is_active": user_info.is_active,
                    "last_time_received_support": user_info.last_time_received_support,
                    "received_startup": user_info.received_startup,
                }
                
                user_inf = UserInfo(**user_info_data)
                user_inf.win_count = user_info.win_count
                user_inf.game_count = user_info.game_count
                user_inf.exp = user_info.exp
                user_inf.login_type = user_info.login_type
                user_inf.num_payments = user_info.num_payments
                user_inf.time_show_ads = user_info.time_show_ads
                user_inf.time_ads_reward = user_info.time_ads_reward
                user_inf.num_claimed_ads = user_info.num_claimed_ads
                
                self.users[uid] = user_inf
                return user_inf
        return None

    async def on_receive_packet(self, uid, cmd_id, payload):
        match cmd_id:
            case CMDs.CHANGE_AVATAR:
                await self._handle_change_avatar(uid, payload)
            case CMDs.CHANGE_USER_NAME:
                await self._handle_change_user_name(uid, payload)
            case CMDs.CHEAT_GOLD_USER:
                await self._handle_cheat_gold_user(uid, payload)
            case _:
                pass

    async def _handle_change_avatar(self, uid: int, payload):
        pkg = packet_pb2.ChangeAvatar()
        pkg.ParseFromString(payload)
        avatar_id = pkg.avatar_id
        user = await self.get_user_info(uid)

        # verify avatar id
        if avatar_id == -1:
            if not user.avatar_third_party:
                logger.error(f"User {uid} try to change to invalid avatar {avatar_id}")
                return
            user.update_avatar(user.avatar_third_party)
        else:
            if avatar_id not in AVATAR_IDS:
                logger.error(f"User {uid} try to change to invalid avatar {avatar_id}")
                return
            user.update_avatar(str(avatar_id))

        # update changes to database
        await user.commit_avatar()

    async def _handle_cheat_gold_user(self, uid: int, payload):
        if not settings.ENABLE_CHEAT:
            return

        pkg = packet_pb2.CheatGoldUser()
        pkg.ParseFromString(payload)
        gold = pkg.gold
        user = await self.get_user_info(uid)
        user.add_gold(gold)
        await user.commit_gold()
        await user.send_update_money()
        print(f"User {uid} cheat gold {gold}")

    async def check_user_vip(self, uid: int) -> bool:
        user = await self.get_user_info(uid)
        if not user:
            return False
        current_time = int(datetime.now().timestamp())
        if user.time_show_ads > current_time:
            return True
        return False
    
    async def _handle_change_user_name(self, uid: int, payload):
        user = await self.get_user_info(uid)

        # only user with name "tressette player" can change name
        if user.name != "tressette player":
            logger.error(f"User {uid} try to change name {user.name}")
            return
        pkg = packet_pb2.ChangeUserName()
        pkg.ParseFromString(payload)
        new_name = pkg.name
        
        # valid new name
        if len(new_name) > 20 or len(new_name) < 1:
            logger.error(f"User {uid} try to change to invalid name {new_name}")
            return
        # update and save to database
        user.name = new_name
        await user.commit_to_database('name')
        

users_info_mgr = UsersInfoMgr()