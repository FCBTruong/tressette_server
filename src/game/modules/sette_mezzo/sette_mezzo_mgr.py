
from src.base.network.packets import packet_pb2
from src.game.game_vars import game_vars
from src.game.cmds import CMDs
from src.game.match import SETTE_MEZZO_MODE


class SetteMezzoMgr:
    
    async def on_receive_packet(self, uid: int, cmd_id: int, payload):
        match cmd_id:
            case CMDs.SETTE_MEZZO_QUICK_PLAY:
                await self._quick_play(uid, payload)
                pass
            case CMDs.SETTE_MEZZO_ACTION_HIT:
                mat = await game_vars.get_match_mgr().get_match_of_user(uid)
                if mat:
                    await mat.user_hit(uid, payload)
            case CMDs.SETTE_MEZZO_ACTION_STAND:
                mat = await game_vars.get_match_mgr().get_match_of_user(uid)
                if mat:
                    await mat.user_stand(uid, payload)

    async def _quick_play(self, uid: int, payload):
        quick_play_pkg = packet_pb2.SetteMezzoQuickPlay()
        quick_play_pkg.ParseFromString(payload)

        match_mgr = game_vars.get_match_mgr()
        match = await match_mgr.get_match_of_user(uid)
        if match:
            print(f"User {uid} is in a match, reconnecting")
            await match.user_reconnect(uid)
            return
        
        # find a match
        if not match:
            for match_id, m in game_vars.get_match_mgr().matches.items():
                if m.game_mode != SETTE_MEZZO_MODE:
                    continue
                if m.check_room_full():
                    continue
                match = m
                break
        if not match:
            match = await game_vars.get_match_mgr().create_sette_mezzo_match()
        await game_vars.get_match_mgr().user_join_match(match, uid)
        

        