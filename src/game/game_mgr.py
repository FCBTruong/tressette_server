

from src.game.cmds import CMDs
from src.game.game_vars import game_vars


class GameMgr:
    def on_join_match(self, uid: int, match_id: int):
        pass

    async def on_receive_packet(self, uid: int, cmd_id: int, payload):
        match cmd_id:
            case CMDs.QUICK_PLAY:
                await self._handle_quick_play(uid)
                pass
        pass
    
    async def _handle_quick_play(self, uid: int):
        match = await game_vars.get_match_mgr().get_free_match()
        if not match:
            match = await game_vars.get_match_mgr().create_match()
        
        if match.check_can_join(uid):
            await game_vars.get_match_mgr().user_join_match(match, uid)

