

import asyncio
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
                await self._handle_quick_play(uid)
            case CMDs.LEAVE_GAME:
                await self._handle_leave_game(uid)
            case CMDs.PLAY_CARD:
                await game_vars.get_match_mgr().user_play_card(uid, payload)
            case CMDs.NEW_INGAME_CHAT_MESSAGE:
                await game_vars.get_ingame_chat_mgr().on_chat_message(uid, payload)
            case CMDs.TABLE_LIST:
                await game_vars.get_match_mgr().on_table_list(uid)
        pass
    
    async def _handle_quick_play(self, uid: int):
        user = await users_info_mgr.get_user_info(uid)
        if user.gold < 15000:
            print(f"User {uid} not enough gold")
            return

        print(f"User {uid} quick play")
        # STEP 1: CHECK IF USER IS IN A MATCH
        match = await game_vars.get_match_mgr().get_match_of_user(uid)
        if match:
            print(f"User {uid} is in a match, reconnecting")
            await match.user_reconnect(uid)
            return

        # STEP JOIN A MATCH
        match = await game_vars.get_match_mgr().get_free_match(uid)
        if not match:
            match = await game_vars.get_match_mgr().create_match(uid)
        
        print(f"User {uid} join match {match.match_id}")
        await game_vars.get_match_mgr().user_join_match(match, uid=uid)

    async def _handle_leave_game(self, uid: int):  
        status = await game_vars.get_match_mgr().handle_user_leave_match(uid)
        leave_pkg = packet_pb2.LeaveGame()
        print(f"User {uid} leave game with status {status}")
        leave_pkg.status = status.value
        await game_vars.get_game_client().send_packet(uid, CMDs.LEAVE_GAME, leave_pkg)
        
        
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