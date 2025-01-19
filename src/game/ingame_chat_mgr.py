
import traceback
from src.base.network.packets import packet_pb2
from src.game.game_vars import game_vars


class InGameChatMgr:

    async def on_chat_message(self, uid, payload):
        try:
            pkg = packet_pb2.InGameChatMessage()
            pkg.ParseFromString(payload)
            message = pkg.chat_message
            print(f"User {uid} sent message: {message}")    
            # get the room and broadcast the message
            match = await game_vars.get_match_mgr().get_match_of_user(uid)
            if not match:
                return

            await match.broadcast_chat_message(uid, message)
        except Exception as e:
            traceback.print_exc()
            print(f"Error on_chat_message: {e}")

