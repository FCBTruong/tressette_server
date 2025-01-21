from datetime import datetime
import logging
from src.base.network.packets import packet_pb2
from src.base.payment import payment_mgr
from src.game.game_vars import game_vars
from src.game.users_info_mgr import users_info_mgr
from src.game.cmds import CMDs
from src.base.network.packets.packet_pb2 import ChatMessage  # Import ChatMessage from the protobuf module

logging.basicConfig(
    level=logging.INFO,  # Set logging level
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",  # Log format
)
logger = logging.getLogger("game_client")  # Name your logger

class GameClient:
    def __init__(self):
        pass

    async def on_receive_packet(self, uid, cmd_id, payload):
        if cmd_id >= 4000 and cmd_id < 5000:
            # PAYMENT
            await payment_mgr.on_receive_packet(uid, cmd_id, payload)
            return 
        await game_vars.get_game_mgr().on_receive_packet(uid, cmd_id, payload)
        match cmd_id:
            case CMDs.LOGOUT:
                print("Received LOGOUT packet")
            case _:
                pass

    async def user_login_success(self, uid):
        from src.base.network.connection_manager import connection_manager
        logger.info(f"User with ID {uid} has successfully logged in")
        general_pkg = packet_pb2.GeneralInfo()
        general_pkg.timestamp = int(datetime.now().timestamp())
        await self.send_packet(uid, CMDs.GENERAL_INFO, general_pkg)

        user_pkg = packet_pb2.UserInfo()
        
        user_info = await users_info_mgr.get_user_info(uid)

        user_pkg.uid = user_info.uid
        user_pkg.name = user_info.name
        user_pkg.gold = user_info.gold
        user_pkg.scores.extend([1, 2, 3, 4, 5])
        user_pkg.names.extend(["a", "", "c", "d", "e"])
        user_pkg.abc = 999
        logger.info(f"User info: {user_info.gold}")

        await self.send_packet(uid, CMDs.USER_INFO, user_pkg)

        # check if user is in a match
        await game_vars.get_game_mgr().on_user_login(uid)


    
    async def send_packet(self, uid, cmd_id, pkt):
        from src.base.network.connection_manager import connection_manager
        await connection_manager.send_packet_to_user(uid=uid, cmd_id=cmd_id, payload=pkt.SerializeToString())

