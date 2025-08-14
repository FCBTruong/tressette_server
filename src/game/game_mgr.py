

import asyncio
from datetime import date, datetime, timezone
from src.base.logs.logs_mgr import write_log
from src.base.network.packets import packet_pb2
from src.constants import PERMANENT_ITEM_EXPIRE_TIME
from src.game.users_info_mgr import users_info_mgr
from src.game.cmds import CMDs
from src.game.game_vars import game_vars
from src.game.tressette_config import config as tress_config
class GameMgr:
    def on_join_match(self, uid: int, match_id: int):
        pass

    async def on_receive_packet(self, uid: int, cmd_id: int, payload):
        if cmd_id >= 10000 and cmd_id < 11000: # sette mezzo game
            await game_vars.get_sette_mezzo_mgr().on_receive_packet(uid, cmd_id, payload)
            return
        
        match cmd_id:
            case CMDs.QUICK_PLAY:
                await game_vars.get_match_mgr().receive_quick_play(uid, payload)
            case CMDs.REGISTER_LEAVE_GAME:
                await game_vars.get_match_mgr().handle_register_leave_match(uid, payload)
            case CMDs.PLAY_CARD:
                await game_vars.get_match_mgr().user_play_card(uid, payload)
            case CMDs.NEW_INGAME_CHAT_MESSAGE:
                await game_vars.get_ingame_chat_mgr().on_chat_message(uid, payload)
            case CMDs.CHAT_EMOTICON:
                await game_vars.get_ingame_chat_mgr().on_chat_emoticon(uid, payload)
            case CMDs.TABLE_LIST:
                await game_vars.get_match_mgr().receive_request_table_list(uid)
            case CMDs.CREATE_TABLE:
                await game_vars.get_match_mgr().received_create_table(uid, payload)
            case CMDs.JOIN_TABLE_BY_ID:
                print("JOIN_TABLE_BY_ID")
                await game_vars.get_match_mgr().receive_user_join_match(uid, payload)
            case CMDs.CLAIM_SUPPORT:
                await self._claim_support(uid)
            case CMDs.INVITE_FRIEND_PLAY:
                await self._receive_invite_friend_play(uid, payload)
            case CMDs.CHEAT_ADD_BOT:
                mat = await game_vars.get_match_mgr().get_match_of_user(uid)
                if mat:
                    await mat.cheat_add_bot()
            case CMDs.GAME_ACTION_NAPOLI:
                await game_vars.get_match_mgr().receive_game_action_napoli(uid, payload)
            case CMDs.USER_RETURN_TO_TABLE:
                await game_vars.get_match_mgr().receive_user_return_to_table(uid)
            case CMDs.USER_MATCH_READY:
                await game_vars.get_match_mgr().user_ready(uid)
            case CMDs.VIEW_GAME:
                await game_vars.get_match_mgr().view_game(uid, payload)
            case CMDs.CLAIM_REWARD_LEVEL:
                await self._claim_reward_level(uid, payload)
     
    async def on_user_login(self, uid: int):
        # wait for 1 second, to let user handle login process
        await asyncio.sleep(1)
        is_is_match = await game_vars.get_match_mgr().is_user_in_match(uid)
        if is_is_match:
            print(f"User {uid} is in a match, reconnecting")
            match = await game_vars.get_match_mgr().get_match_of_user(uid)
            await match.user_reconnect(uid)
            return
    async def on_user_disconnect(self, uid: int):
        await game_vars.get_match_mgr().user_disconnect(uid)
        # Write last time user online
        user_info = await users_info_mgr.get_user_info(uid)
        if user_info:
            user_info.last_time_online = int(datetime.now(timezone.utc).timestamp())
            await user_info.commit_to_database('last_time_online')

    def check_can_receive_support(self, timestamp: int) -> bool:
        # Convert the given timestamp to a date
        last_support_date = datetime.fromtimestamp(timestamp).date()

        # Get the current date
        current_date = datetime.now().date()

        # Check if the last support date is today
        if last_support_date == current_date:
            return False

        return True
    
    async def _claim_support(self, uid: int):
        return
        GOLD_SUPPORT = 0
        user_info = await users_info_mgr.get_user_info(uid)

        if not user_info:
            return
        
        if user_info.gold >= game_vars.get_match_mgr().get_gold_minimum_play():
            return

        if not self.check_can_receive_support(user_info.last_time_received_support):
            return
        
        user_info.add_gold(GOLD_SUPPORT)

        user_info.last_time_received_support = int(datetime.now().timestamp())
        await user_info.commit_to_database('gold', 'last_time_received_support')
        await user_info.send_update_money()

        # send claim support success
        pkg = packet_pb2.ClaimSupport()
        pkg.support_amount = GOLD_SUPPORT
        await game_vars.get_game_client().send_packet(uid, CMDs.CLAIM_SUPPORT, pkg)

    async def _receive_invite_friend_play(self, uid: int, payload):
        pkg = packet_pb2.InviteFriendPlay()
        pkg.ParseFromString(payload)
        friend_uid = pkg.uid
        # get current room of user
        match = await game_vars.get_match_mgr().get_match_of_user(uid)
        if not match:
            print("Error invite friend play, user not in match")
            return
        
        if not game_vars.get_friend_mgr().is_friend(uid, friend_uid):
            print("Error invite friend play, not friend")
            return
        
        # send invite friend play
        res_pkg = packet_pb2.InviteFriendPlay()
        res_pkg.uid = uid
        res_pkg.room_id = match.match_id

        await game_vars.get_game_client().send_packet(friend_uid, CMDs.INVITE_FRIEND_PLAY, res_pkg)

    async def _claim_reward_level(self, uid: int, payload):
        pkg = packet_pb2.ClaimRewardLevel()
        pkg.ParseFromString(payload)
        level = pkg.level

        user_info = await users_info_mgr.get_user_info(uid)
        if not user_info:
            return
        
        if level in user_info.claimed_levels:
            print(f"User {uid} already claimed reward for level {level}")
            return
        
        # Check if the level is valid
        items = []
        for reward in tress_config.get("level_rewards"):  
            if reward["level"] == level:
                gold = reward["gold"]
                user_info.add_gold(gold)

                for item in reward.get("items", []):
                    item_id = item["item_id"]
                    duration = item["duration"] # days
                    items.append((item_id, duration))
                    duration_sec = PERMANENT_ITEM_EXPIRE_TIME if duration == -1 else duration * 86400  # convert days to seconds
                    await game_vars.get_inventory_mgr().update_inventory(uid, item_id, duration_sec=duration_sec)  # convert days to seconds
                    
                break
        user_info.claimed_levels.append(level)
        await user_info.commit_to_database('claimed_levels', 'gold')
        
        pkg_response = packet_pb2.ClaimRewardLevelResponse()
        pkg_response.level = level
        pkg_response.gold = gold

        for item_id, duration in items:
            reward_item = pkg_response.items.add()
            reward_item.item_id = item_id
            reward_item.duration = duration  # keep in days
        # Send update to client
        await game_vars.get_game_client().send_packet(uid, CMDs.CLAIM_REWARD_LEVEL, pkg_response)

        if items:
            # Send inventory update
            await game_vars.get_inventory_mgr().send_user_inventory(uid)

        write_log(uid, "claim_reward_level", level, [gold, items])
