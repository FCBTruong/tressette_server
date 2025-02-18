

import asyncio
from datetime import date, datetime
from src.base.network.packets import packet_pb2
from src.game.users_info_mgr import users_info_mgr
from src.game.cmds import CMDs
from src.game.game_vars import game_vars

MIN_GOLD_PLAY = 15000
class GameMgr:
    def on_join_match(self, uid: int, match_id: int):
        pass

    async def on_receive_packet(self, uid: int, cmd_id: int, payload):
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
                await game_vars.get_match_mgr().create_table(uid, payload)
            case CMDs.JOIN_TABLE_BY_ID:
                print("JOIN_TABLE_BY_ID")
                await game_vars.get_match_mgr().receive_user_join_match(uid, payload)
            case CMDs.CLAIM_SUPPORT:
                await self._claim_support(uid)
     
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

    def check_can_receive_support(self, timestamp: int) -> bool:
        # Convert the given timestamp to a date
        last_support_date = datetime.fromtimestamp(timestamp).date()

        # Get the current date
        current_date = date.today()

        # Check if the last support date is today
        if last_support_date == current_date:
            return False

        return True
    
    async def _claim_support(self, uid: int):
        GOLD_SUPPORT = 50000
        user_info = await users_info_mgr.get_user_info(uid)

        if not user_info:
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