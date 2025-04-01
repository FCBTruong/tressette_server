
import traceback
from src.base.network.packets import packet_pb2
from src.game.game_vars import game_vars
from src.constants import CHAT_EMO_IDS


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
                print(f"User {uid} not in a match")
                return

            await match.broadcast_chat_message(uid, message)
        except Exception as e:
            traceback.print_exc()
            print(f"Error on_chat_message: {e}")


    async def on_chat_emoticon(self, uid, payload):
        try:
            pkg = packet_pb2.InGameChatEmoticon()
            pkg.ParseFromString(payload)
            emoticon = pkg.emoticon
            # check emoticon
            if emoticon not in CHAT_EMO_IDS:
                return
                
            print(f"User {uid} sent emoticon: {emoticon}")
            # get the room and broadcast the emoticon
            match = await game_vars.get_match_mgr().get_match_of_user(uid)
            if not match:
                return

            await match.broadcast_chat_emoticon(uid, emoticon)
        except Exception as e:
            traceback.print_exc()
            print(f"Error on_chat_emoticon: {e}")
