
from src.base.network.packets import packet_pb2
from src.game.game_vars import game_vars
from src.game.users_info_mgr import users_info_mgr
from src.game.cmds import CMDs


class FriendMgr:
    async def get_friends(self, uid: int) -> list:
        return []
    
    async def add_friend(self, uid: int, friend_id: int):
        pass

    async def remove_friend(self, uid: int, friend_id: int):
        pass

    async def get_friend_requests(self, uid: int) -> list:
        return []
    
    async def accept_friend_request(self, uid: int, friend_id: int):
        pass

    async def on_receive_packet(self, uid: int, cmd_id: int, payload):
        match cmd_id:
            case CMDs.SEARCH_FRIEND:
                await self._handle_search_friend(uid, payload)
                pass

    async def _handle_search_friend(self, uid: int, payload):
        pkg = packet_pb2.SearchFriend()
        pkg.ParseFromString(payload)

        search_uid = pkg.uid
        print(f"User {uid} search friend {search_uid}")

        # get user info
        err = 0
        user_info = await users_info_mgr.get_user_info(search_uid)

        pkg_response = packet_pb2.SearchFriendResponse()
        if not user_info:
            print(f"User {uid} search friend {search_uid} not found")
            err = 1
        else:
            pkg_response.uid = user_info.uid
            pkg_response.name = user_info.name
            pkg_response.avatar = user_info.avatar
            pkg_response.level = user_info.level
            pkg_response.gold = user_info.gold

        pkg_response.error = err
        # send response
        await game_vars.get_game_client().send_packet(uid, CMDs.SEARCH_FRIEND, pkg_response)

