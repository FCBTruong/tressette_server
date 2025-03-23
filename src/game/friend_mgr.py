
from sqlalchemy import func, select
from src.base.network.connection_manager import connection_manager
from src.base.network.packets import packet_pb2
from src.game.game_vars import game_vars
from src.game.users_info_mgr import users_info_mgr
from src.game.cmds import CMDs
from src.postgres.orm import PsqlOrm
from src.postgres.sql_models import Friendship, UserInfoSchema
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
    

    async def remove_friend(self, uid: int, payload):
        pkg = packet_pb2.RemoveFriend()
        pkg.ParseFromString(payload)
        friend_id = pkg.uid
        async with PsqlOrm.get().session() as session:
            result = await session.execute(
                select(Friendship).where(
                    (Friendship.user1_id == uid) & (Friendship.user2_id == friend_id) |
                    (Friendship.user1_id == friend_id) & (Friendship.user2_id == uid),
                    Friendship.status == FRIENDSHIP_STATUS_ACCEPTED
                )
            )
            row = result.scalars().first()
            if row:
                await session.delete(row)
                await session.commit()
        pass

    async def get_friend_requests(self, uid: int) -> list:
        return []
    
    async def accept_friend_request(self, uid: int, payload):
        print(f"User {uid} accept friend request")
        pkg = packet_pb2.RequestFriendAccept()
        pkg.ParseFromString(payload)
        friend_id = pkg.uid
        action = pkg.action
        async with PsqlOrm.get().session() as session:
            result = await session.execute(
                select(Friendship).where(
                    (Friendship.user1_id == friend_id) & (Friendship.user2_id == uid)
                )
            )

            row = result.scalars().first()
            if row:
                if action == ACTION_FRIEND_REQUEST_ACCEPT:
                    row.status = FRIENDSHIP_STATUS_ACCEPTED
                    await session.commit()
                elif action == ACTION_FRIEND_REQUEST_REJECT:
                    await session.delete(row)
                    await session.commit()

        user_info = await users_info_mgr.get_user_info(uid=uid)
        # notify to the friend that the request is accepted
        if action == ACTION_FRIEND_REQUEST_ACCEPT:
            accepted_pkg = packet_pb2.FriendRequestAccepted()
            accepted_pkg.uid = uid
            accepted_pkg.name = user_info.name
            accepted_pkg.avatar = user_info.avatar
            accepted_pkg.level = user_info.level
            accepted_pkg.gold = user_info.gold
            await game_vars.get_game_client().send_packet(friend_id, CMDs.NEW_FRIEND_ACCEPTED, accepted_pkg)

    async def on_receive_packet(self, uid: int, cmd_id: int, payload):
        match cmd_id:
            case CMDs.SEARCH_FRIEND:
                await self._handle_search_friend(uid, payload)
                pass
            case CMDs.ADD_FRIEND:
                await self._handle_add_friend(uid, payload)
            
            case CMDs.ACCEPT_FRIEND_REQUEST:
                await self.accept_friend_request(uid, payload)
                pass

            case CMDs.REMOVE_FRIEND:
                await self.remove_friend(uid, payload)
                pass
            case CMDs.FRIEND_LIST:
                await self.send_list_friends(uid)
                pass

    async def send_list_friends(self, uid: int, send_recommend_if_empty=False):
        friend_ids = await self.get_friends(uid)

        if len(friend_ids) == 0 and send_recommend_if_empty:
            # NO friends, so send recommend friends instead
            print(f"User {uid} has no friends, send recommend friends")
            await self.send_recommend_friends(uid)
            return
        
        pkg = packet_pb2.FriendList()

        names = []
        avatars = []
        levels = []
        golds = []
        onlines = []
        uids = []
        playings = []
        for friend_id in friend_ids:
            user_info = await users_info_mgr.get_user_info(friend_id)
            if user_info and user_info.is_active:
                is_online = connection_manager.check_user_active_online(friend_id)
                is_playing = False
                if is_online:
                    is_playing = await game_vars.get_match_mgr().is_user_in_match(friend_id)
                onlines.append(is_online)
                uids.append(friend_id)
                names.append(user_info.name)
                avatars.append(user_info.avatar)
                levels.append(user_info.level)
                golds.append(user_info.gold)
                playings.append(is_playing)

        pkg.uids.extend(uids)
        pkg.names.extend(names)
        pkg.avatars.extend(avatars)
        pkg.levels.extend(levels)
        pkg.golds.extend(golds)
        pkg.onlines.extend(onlines)
        pkg.is_playings.extend(playings)

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
        if not user_info or user_info.is_active == False:
            print(f"User {uid} search friend {search_uid} not found")
            err = 1
        else:
            pkg_response.uid = user_info.uid
            pkg_response.name = user_info.name
            pkg_response.avatar = user_info.avatar
            pkg_response.level = user_info.level
            pkg_response.gold = user_info.gold
            pkg_response.exp = user_info.exp
            pkg_response.win_count = user_info.win_count
            pkg_response.game_count = user_info.game_count

        pkg_response.error = err
        # send response
        await game_vars.get_game_client().send_packet(uid, CMDs.SEARCH_FRIEND, pkg_response)

    # Requests need accept and sent requests to other users
    async def send_friend_requests(self, uid: int):
        print(f"Send friend requests to user {uid}")
        async with PsqlOrm.get().session() as session:
            result = await session.execute(
                select(Friendship).where(
                    (Friendship.user1_id == uid) | (Friendship.user2_id == uid),
                    Friendship.status == FRIENDSHIP_STATUS_PENDING
                ) 
            )
        # First ID is sender, second ID is who will accept
        rows = result.scalars().all()
        friend_requests = []
        sent_requests = []
        for row in rows:
            if row.user1_id == uid:
                sent_requests.append(row.user2_id)
            else:
                friend_requests.append(row.user1_id)

        pkg = packet_pb2.FriendRequests()

        request_uids = []
        names = []
        avatars = []
        levels = []
        golds = []
        for rid in friend_requests:
            user_info = await users_info_mgr.get_user_info(rid)
            if user_info:
                request_uids.append(user_info.uid)
                names.append(user_info.name)
                avatars.append(user_info.avatar)
                levels.append(user_info.level)
                golds.append(user_info.gold)

        pkg.uids.extend(request_uids)
        pkg.names.extend(names)
        pkg.avatars.extend(avatars)
        pkg.levels.extend(levels)
        pkg.golds.extend(golds)

        pkg.sent_uids.extend(sent_requests)

        await game_vars.get_game_client().send_packet(uid, CMDs.FRIEND_REQUESTS, pkg)

    async def _handle_add_friend(self, uid: int, payload):
        count_friends = await self._count_friends(uid)

        if count_friends >= MAX_FRIENDS_NUMBER:
            print(f"User {uid} reach max friends number")
            return
        pkg = packet_pb2.AddFriend()
        pkg.ParseFromString(payload)

        friend_uid = pkg.uid
        print(f"User {uid} add friend {friend_uid}")

        # check if user exist
        receiver = await users_info_mgr.get_user_info(friend_uid)
        if not receiver:
            print(f"User {uid} add friend {friend_uid} not found")
            return

        # check if already sent request
        async with PsqlOrm.get().session() as session:
            result = await session.execute(
                select(Friendship).where(
                    (Friendship.user1_id == uid) & (Friendship.user2_id == friend_uid) |
                    (Friendship.user1_id == friend_uid) & (Friendship.user2_id == uid)
                )
            )

            row = result.scalars().first()
            if row:
                if row.user1_id == uid:
                    print(f"User {uid} add friend {friend_uid} already sent request")
                    return
                else:
                    # BOTH user sent request to each other -> auto accept
                    # update status
                    row.status = FRIENDSHIP_STATUS_ACCEPTED
                    await session.commit()
                    # send friend requests to friend
                    await self.send_friend_requests(friend_uid)
                    return
            
        # Save to database
        async with PsqlOrm.get().session() as session:
            # User 1 send request to user 2
            friendship = Friendship(user1_id=uid, user2_id=friend_uid, status=FRIENDSHIP_STATUS_PENDING)
            session.add(friendship)
            await session.commit()

        # send to des user a notification
        sender = await users_info_mgr.get_user_info(uid)
        new_fr_pkg = packet_pb2.NewFriendRequest()
        new_fr_pkg.uid = uid
        new_fr_pkg.name = sender.name
        new_fr_pkg.avatar = sender.avatar
        new_fr_pkg.level = sender.level
        new_fr_pkg.gold = sender.gold

        await game_vars.get_game_client().send_packet(friend_uid, CMDs.NEW_FRIEND_REQUEST, new_fr_pkg)
        

    async def _count_friends(self, user_id):
        async with PsqlOrm.get().session() as session:
            result = await session.execute(
                select(func.count())
                .select_from(Friendship)
                .where(
                    ((Friendship.user1_id == user_id) | (Friendship.user2_id == user_id)) &
                    (Friendship.status == FRIENDSHIP_STATUS_ACCEPTED)  # Assuming 'accepted' is the status
                )
            )
            return result.scalar_one()
        
    async def send_recommend_friends(self, uid: int):
        # get online UIDs first
        online_uids = connection_manager.get_random_user_online(10)

        # remove the user itself
        if uid in online_uids:
            online_uids.remove(uid)

        recommend_uids = online_uids
        # If not found user online, find from database
        if len(online_uids) == 0:
            async with PsqlOrm.get().session() as session:
                result = await session.execute(
                    select(UserInfoSchema.uid)
                    .where(UserInfoSchema.is_active == True)
                    .order_by(func.random())  # Order by a random value
                    .limit(FRIEND_RECOMMENDED_SIZE)  # Limit to 10 results
                )
            recommend_uids = result.scalars().all()  # Get all 10 random uids

        if uid in recommend_uids:
            recommend_uids.remove(uid)

        if len(recommend_uids) == 0:
            print(f"User {uid} has no friends and no recommend friends")
            return
        
        # get the user info and send to the user
        uids = []
        names = []
        avatars = []
        levels = []
        golds = []
        for rec_uid in recommend_uids:
            user_info = await users_info_mgr.get_user_info(rec_uid)
            if user_info:
                uids.append(user_info.uid)
                names.append(user_info.name)
                avatars.append(user_info.avatar)
                levels.append(user_info.level)
                golds.append(user_info.gold)
        
        pkg = packet_pb2.RecommendFriends()
        pkg.uids.extend(uids)   
        pkg.names.extend(names)
        pkg.avatars.extend(avatars)
        pkg.levels.extend(levels)
        pkg.golds.extend(golds)

        await game_vars.get_game_client().send_packet(uid, CMDs.RECOMMEND_FRIENDS, pkg)

    async def is_friend(self, uid1, uid2):
        async with PsqlOrm.get().session() as session:
            result = await session.execute(
                select(Friendship).where(
                    (Friendship.user1_id == uid1) & (Friendship.user2_id == uid2) |
                    (Friendship.user1_id == uid2) & (Friendship.user2_id == uid1),
                    Friendship.status == FRIENDSHIP_STATUS_ACCEPTED
                )
            )
            row = result.scalars().first()
            return row is not None
        
FRIEND_RECOMMENDED_SIZE = 10