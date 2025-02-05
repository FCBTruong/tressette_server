
from sqlalchemy import select
from src.base.network.packets import packet_pb2
from src.game.game_vars import game_vars
from src.game.users_info_mgr import users_info_mgr
from src.game.cmds import CMDs
from src.postgres.orm import PsqlOrm
from src.postgres.sql_models import Friendship
from src.constants import *


class FriendMgr:
    async def get_friends(self, uid: int) -> list:
        async with PsqlOrm.get().session() as session:
            result = await session.execute(
                select(Friendship).where(
                    (Friendship.user1_id == uid) | (Friendship.user2_id == uid),  # Use `|` for OR
                    Friendship.status == FRIENDSHIP_STATUS_ACCEPTED
                )
            )
            rows = result.scalars().all()  # Convert result to list
            # filter out the user itself
            friend_ids = [row.user1_id if row.user1_id != uid else row.user2_id for row in rows]
            return friend_ids
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

    async def send_list_friends(self, uid: int):
        friend_ids = await self.get_friends(uid)
        pkg = packet_pb2.FriendList()

        names = []
        avatars = []
        levels = []
        golds = []
        for friend_id in friend_ids:
            user_info = await users_info_mgr.get_user_info(friend_id)
            if user_info:
                names.append(user_info.name)
                avatars.append(user_info.avatar)
                levels.append(user_info.level)
                golds.append(user_info.gold)

        pkg.names.extend(names)
        pkg.avatars.extend(avatars)
        pkg.levels.extend(levels)
        pkg.golds.extend(golds)
        pkg.uids.extend(friend_ids)

        await game_vars.get_game_client().send_packet(uid, CMDs.FRIEND_LIST, pkg)
                

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

