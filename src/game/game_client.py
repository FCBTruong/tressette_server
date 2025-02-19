from datetime import datetime
import logging
from src.base.network.connection_manager import connection_manager
from src.base.network.packets import packet_pb2
from src.base.payment import payment_mgr
from src.game.game_vars import game_vars
from src.game.users_info_mgr import users_info_mgr
from src.game.cmds import CMDs
from src.base.network.packets.packet_pb2 import ChatMessage  # Import ChatMessage from the protobuf module
from src.game.tressette_config import config as tress_config
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
        match cmd_id:
            case CMDs.LOGOUT:
                logout_pkg = packet_pb2.Logout()
                # send logout packet
                await self.send_packet(uid, CMDs.LOGOUT, logout_pkg)
                print("Accepted logout")
                await connection_manager.user_logout(uid)
                game_vars.get_logs_mgr().write_log(uid, "logout", "", [])
            case _:
                await game_vars.get_game_mgr().on_receive_packet(uid, cmd_id, payload)
                await users_info_mgr.on_receive_packet(uid, cmd_id, payload)
                await game_vars.get_friend_mgr().on_receive_packet(uid, cmd_id, payload)

    async def user_login_success(self, uid, device_model, platform):
        logger.info(f"User with ID {uid} has successfully logged in")
        general_pkg = packet_pb2.GeneralInfo()
        general_pkg.min_gold_play = tress_config.get("min_gold_play")
        general_pkg.time_thinking_in_turn = tress_config.get("time_thinking_in_turn")
        general_pkg.timestamp = int(datetime.now().timestamp())
        general_pkg.bet_multiplier_min = tress_config.get("bet_multiplier_min")

        tressette_bets = tress_config.get("bets")
        general_pkg.tressette_bets.extend(tressette_bets)
        await self.send_packet(uid, CMDs.GENERAL_INFO, general_pkg)

        user_pkg = packet_pb2.UserInfo()
        
        user_info = await users_info_mgr.get_user_info(uid)

        user_pkg.uid = user_info.uid
        user_pkg.name = user_info.name
        user_pkg.exp = user_info.exp
        user_pkg.game_count = user_info.game_count
        user_pkg.win_count = user_info.win_count
        user_pkg.gold = user_info.gold
        user_pkg.avatar = user_info.avatar
        user_pkg.level = user_info.level
        user_pkg.avatar_third_party = user_info.avatar_third_party
        user_pkg.support_num = 1 if game_vars.get_game_mgr().check_can_receive_support(user_info.last_time_received_support) else 0
        logger.info(f"User info: {user_info.gold}")

        await self.send_packet(uid, CMDs.USER_INFO, user_pkg)

        # SEND SHOP CONFIG
        await payment_mgr.send_shop_config(uid)

        # Send friend list
        await game_vars.get_friend_mgr().send_list_friends(uid, send_recommend_if_empty=True)
        await game_vars.get_friend_mgr().send_friend_requests(uid) # friend requests

        # check if user is in a match
        await game_vars.get_game_mgr().on_user_login(uid)

        # Write log login
        game_vars.get_logs_mgr().write_log(uid, "login", "", [device_model, platform])

    async def send_packet(self, uid, cmd_id, pkt):
        from src.base.network.connection_manager import connection_manager
        await connection_manager.send_packet_to_user(uid=uid, cmd_id=cmd_id, payload=pkt.SerializeToString())

