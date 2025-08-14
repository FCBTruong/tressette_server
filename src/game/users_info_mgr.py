
from datetime import datetime
import json
import logging
# from src.cache import redis_cache
from src.base.logs.logs_mgr import write_log
from src.base.network.packets import packet_pb2
from src.config.settings import settings
from src.game.game_vars import game_vars
from src.game.models import UserInfo
from src.postgres.sql_models import UserInfoSchema
from src.postgres.orm import PsqlOrm
from src.game.cmds import CMDs
from src.constants import *
from src.game.tressette_config import get_price_change_name

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
        user_info = self.users.get(uid)
        
        if not user_info:
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
                    user_inf.avatar_frame = user_info.avatar_frame
                    user_inf.last_time_online = user_info.last_time_online
                    user_inf.claimed_levels = user_info.claimed_levels
                    user_inf.num_change_name = user_info.num_change_name
                    
                    self.users[uid] = user_inf
                    user_info = user_inf

        if not user_info:
            logger.error(f"User {uid} not found in database")
            return None
        
        # check avatar frame expire
        if user_info.avatar_frame and user_info.avatar_frame != AVATAR_FRAME_DEFAULT:
            current_time = int(datetime.now().timestamp())
            invent_info = await game_vars.get_inventory_mgr().get_inventory(uid)
            item = next((i for i in invent_info if i.item_id == user_info.avatar_frame), None)
            if item and item.expire_time != PERMANENT_ITEM_EXPIRE_TIME and item.expire_time < current_time:
                # item expired, reset to default
                user_info.avatar_frame = AVATAR_FRAME_DEFAULT
                await user_info.commit_to_database('avatar_frame')
        return user_info

    async def on_receive_packet(self, uid, cmd_id, payload):
        match cmd_id:
            case CMDs.CHANGE_AVATAR:
                await self._handle_change_avatar(uid, payload)
            case CMDs.CHANGE_USER_NAME:
                await self._handle_change_user_name(uid, payload)
            case CMDs.CHEAT_GOLD_USER:
                await self._handle_cheat_gold_user(uid, payload)
            case CMDs.CHEAT_EXP_USER:
                await self._handle_cheat_exp_user(uid, payload)
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

    async def _handle_cheat_exp_user(self, uid: int, payload):
        if not settings.ENABLE_CHEAT:
            return

        pkg = packet_pb2.CheatExpUser()
        pkg.ParseFromString(payload)
        exp = pkg.exp
        user = await self.get_user_info(uid)
        user.add_exp(exp)
        await user.commit_exp()
        await user.send_update_exp()
        print(f"User {uid} cheat exp {exp}")

    async def check_user_vip(self, uid: int) -> bool:
        user = await self.get_user_info(uid)
        if not user:
            return False
        current_time = int(datetime.now().timestamp())
        if user.time_show_ads > current_time:
            return True
        return False
    
    async def _handle_change_user_name(self, uid: int, payload: bytes):
        user = await self.get_user_info(uid)
        price = get_price_change_name(user.num_change_name)

        # parse payload first
        req = packet_pb2.ChangeUserName()
        req.ParseFromString(payload)
        new_name = req.name.strip()

        # validate new name
        if not (1 <= len(new_name) <= 25):
            logger.error(f"User {uid} tried to change to invalid name: '{new_name}'")
            return

        # check inventory for rename cards
        inv = await game_vars.get_inventory_mgr().get_inventory(uid)
        item = next((i for i in inv if i.item_id == RENAME_CARD_ITEM_ID), None)
        if item is None or getattr(item, "value", 0) < price:
            logger.error(f"User {uid} lacks rename cards (need {price}, have {0 if item is None else item.value})")
            return

        # deduct price (stackable) then apply change
        await game_vars.get_inventory_mgr().update_inventory(
            uid=uid, item_id=RENAME_CARD_ITEM_ID, duration_sec=0, value=-price
        )

        user.name = new_name
        user.num_change_name += 1
        await user.commit_to_database("name", "num_change_name")
        await game_vars.get_inventory_mgr().send_user_inventory(uid)
        write_log(uid, "change_user_name", new_name, [price])



users_info_mgr = UsersInfoMgr()