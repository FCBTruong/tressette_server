# Configure the logger

import asyncio
import logging

from src.base.network.packets import packet_pb2
from src.game.game_vars import game_vars
from src.game.cmds import CMDs
from src.game.match import LeaveMatchErrors, Match, MatchState
from src.game.users_info_mgr import users_info_mgr
from src.game.tressette_config import config as tress_config


logging.basicConfig(
    level=logging.INFO,  # Set logging level
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",  # Log format
)
logger = logging.getLogger("game_match")  # Name your logger


class MatchManager:
    def __init__(self):
        self.start_match_id = 1000
        self.matches: dict[int, Match] = {}
        self.user_matchids: dict[int, int] = {}
        self._task = None

    def start(self):
        """Starts the match manager loop."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())

    def stop(self):
        """Stops the match manager loop."""
        if self._task:
            self._task.cancel()

    async def _loop(self):
        """The main loop to manage matches."""
        try:
            while True:
                for match in list(self.matches.values()):  # Use list() to avoid mutation issues.
                    try:
                        await match.loop()
                    except Exception as e:
                        logger.error(f"Error in match loop: {e}")
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            logger.info("MatchManager loop has been stopped.")
        except Exception as e:
            logger.error(f"Unexpected error in MatchManager loop: {e}")

    async def create_match(self, uid) -> Match:
        match_id = self.start_match_id
        logger.info(f"Creating match {match_id}")
        match = Match(match_id)
        self.matches[match_id] = match
        self.start_match_id += 1
        return match

    async def create_table(self, uid, payload):
        create_table_pkg = packet_pb2.CreateTable()
        create_table_pkg.ParseFromString(payload)
        bet = create_table_pkg.bet
    
        # check if user has enough gold to create table this bet
        user_info = await users_info_mgr.get_user_info(uid)
        if user_info.gold < tress_config.get("min_gold_play"):
            print(f"User {uid} not enough gold")
            return
        if await self.is_user_in_match(uid):
            return
        
        if user_info.gold < bet * tress_config.get('bet_multiplier_min'):
            return
        
        match = await self.create_match(uid)
        match.bet = bet
        await self._user_join_match(match, uid)

    async def get_match(self, match_id):
        return self.matches.get(match_id)

    async def update_matches(self):
        for match_id, match in self.matches.items():
            match.update_state()

    async def get_match_of_user(self, user_id) -> Match:
        match_id = self.user_matchids.get(user_id)
        if match_id:
            return self.matches.get(match_id)
        return None

    def destroy_match(self, match_id):
        print(f"End match {match_id}")
        match = self.matches.get(match_id)
        if match:
            for player in match.players:
                if player.uid in self.user_matchids:
                    self.user_matchids.pop(player.uid)
            self.matches.pop(match_id)
            del match

    async def is_user_in_match(self, user_id):
        return user_id in self.user_matchids
    
    async def get_free_match(self) -> Match:
        for match_id, match in self.matches.items():
            if match.state == MatchState.WAITING and not match.check_room_full():
                return match
        return None
    
    async def _user_join_match(self, match: Match, uid: int):
        self.user_matchids[uid] = match.match_id
        await match.user_join(uid)

    async def handle_register_leave_match(self, uid: int, payload):
        leave_pkg = packet_pb2.RegisterLeaveGame()
        leave_pkg.ParseFromString(payload)
        status = leave_pkg.status
        # print(f"User {uid} leave game with status {status}")
        # leave_pkg.status = status.value
        # await game_vars.get_game_client().send_packet(uid, CMDs.REGISTER_LEAVE_GAME, leave_pkg)

        match = await self.get_match_of_user(uid)
        if not match:
            return
        
        if match.can_quit_game():
            await self.handle_user_leave_match(uid)
            return
        
        if status == 0:
            match.register_leave(uid)
        else:
            match.deregister_leave(uid)

        await game_vars.get_game_client().send_packet(uid, CMDs.REGISTER_LEAVE_GAME, leave_pkg)


    # USER officially leave match
    async def handle_user_leave_match(self, uid: int) -> LeaveMatchErrors:
        match_id = self.user_matchids.get(uid)

        if not match_id:
            return LeaveMatchErrors.NOT_IN_MATCH
        
        match = await self.get_match_of_user(uid)
        if not match.can_quit_game():
            return LeaveMatchErrors.MATCH_STARTED
        
        await match.user_leave(uid)
        self.user_matchids.pop(uid)
        print("User leave match", match.check_has_real_players())

        if not match.check_has_real_players():
            print('Destroy match', match_id)
            self.destroy_match(match_id)

        return LeaveMatchErrors.SUCCESS
            
    async def user_disconnect(self, uid: int):
        is_in_match = await self.is_user_in_match(uid)
        if is_in_match:
            print(f"User {uid} is in a match, auto leave")
            match = await self.get_match_of_user(uid)
            if match.state == MatchState.WAITING:
                await self.handle_user_leave_match(uid)

    async def user_play_card(self, uid: int, payload):
        match = await self.get_match_of_user(uid)
        if match:
            await match.user_play_card(uid, payload)

    async def receive_request_table_list(self, uid):
        matches = await self._prioritize_matches(self.matches, uid)  # Get the 20 matches closest to the user's gold
        # priority table is waiting
        match_ids = []
        bets = []
        player_modes = []
        num_players = []
        for match in matches:
            match_ids.append(match.match_id)
            bets.append(match.bet)
            player_modes.append(match.player_mode)
            num_players.append(match.get_num_players())

        
        print(f"Table list: {match_ids}")
        pkg = packet_pb2.TableList()
        pkg.table_ids.extend(match_ids)
        pkg.bets.extend(bets)
        pkg.player_modes.extend(player_modes)
        pkg.num_players.extend(num_players)
        await game_vars.get_game_client().send_packet(uid, CMDs.TABLE_LIST, pkg)

    async def _prioritize_matches(self, matches: dict[int, Match], uid: int) -> list[Match]:
        MAX_MATCHES = 20  # Limit of prioritized matches
        user = await users_info_mgr.get_user_info(uid)
        user_gold = user.gold

        # Separate matches by state
        waiting_matches = [match for match in matches.values() if match.state == MatchState.WAITING]
        other_matches = [match for match in matches.values() if match.state != MatchState.WAITING]

        # Sort matches by bet proximity to user's gold
        waiting_matches.sort(key=lambda match: abs(match.bet - user_gold))
        other_matches.sort(key=lambda match: abs(match.bet - user_gold))

        # Combine matches, prioritizing waiting matches
        prioritized_matches = waiting_matches + other_matches

        # Return the top matches, limited to `MAX_MATCHES`
        return prioritized_matches[:MAX_MATCHES]

    async def join_match(self, uid, match_id):
        match = await self.get_match(match_id)

        # check other conditions to join match
        if not match:
            return
        await self._user_join_match(match, uid)

    async def _handle_quick_play(self, uid: int):
        user = await users_info_mgr.get_user_info(uid)
        if user.gold < tress_config.get("min_gold_play"):
            print(f"User {uid} not enough gold")
            return

        print(f"User {uid} quick play")
        # STEP 1: CHECK IF USER IS IN A MATCH
        match = await self.get_match_of_user(uid)
        if match:
            print(f"User {uid} is in a match, reconnecting")
            await match.user_reconnect(uid)
            return

        # STEP JOIN A MATCH
        match = await self.get_free_match()
        if not match:
            match = await game_vars.get_match_mgr().create_match(uid)

        # Check condition
        if user.gold < match.get_min_gold_play():
            return
        
        print(f"User {uid} join match {match.match_id}")
        await self._user_join_match(match, uid=uid)

        game_vars.get_logs_mgr().write_log(uid, "quick_play", "", [])
        
    async def _check_user_can_join_match(self, uid, match: Match) -> bool:
        user = await users_info_mgr.get_user_info(uid)
        if user.gold < match.get_min_gold_play():
            return False
        return True
    
    async def _handle_user_join_by_match_id(self, uid, match_id):
        # check if user is in a match
        is_in_match = await self.is_user_in_match(uid)
        if is_in_match:
            return

        match = await self.get_match(match_id)
        if not match:
            return
        
        if match.state != MatchState.WAITING:
            return
        
        if match.check_room_full():
            return
        
        if not await self._check_user_can_join_match(uid, match):
            return
        
        await self._user_join_match(match, uid)

    async def receive_user_join_match(self, uid, payload):
        join_pkg = packet_pb2.JoinTableById()
        join_pkg.ParseFromString(payload)
        match_id = join_pkg.match_id
        await self._handle_user_join_by_match_id(uid, match_id)

    async def receive_quick_play(self, uid, payload):
        await self._handle_quick_play(uid)