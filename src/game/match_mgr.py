# Configure the logger

import asyncio
from enum import Enum
import logging
import random

from src.base.logs.logs_mgr import write_log
from src.base.network.packets import packet_pb2
from src.game.game_vars import game_vars
from src.game.cmds import CMDs
from src.game.match import LeaveMatchErrors, Match, MatchState, PLAYER_SOLO_MODE, PLAYER_DUO_MODE, TressetteMatch
from src.game.users_info_mgr import users_info_mgr
from src.game.tressette_config import config as tress_config
from src.game.modules.sette_mezzo.sette_mezzo_match import SetteMezzoMatch


logging.basicConfig(
    level=logging.INFO,  # Set logging level
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",  # Log format
)
logger = logging.getLogger("game_match")  # Name your logger

class JoinMatchErrors(Enum):
    SUCCESS = 0
    MATCH_STARTED = 1
    FULL_ROOM = 2
    NOT_ENOUGH_GOLD = 3
    ALREADY_IN_MATCH = 4
    MATCH_NOT_FOUND = 5

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
                    asyncio.create_task(self._run_match(match))  # Fire and forget
                
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            logger.info("MatchManager loop has been stopped.")
        except Exception as e:
            logger.error(f"Unexpected error in MatchManager loop: {e}")

    async def _run_match(self, match: Match):
        """Run a single match loop and handle errors."""
        try:
            await match.loop()
        except Exception as e:
            logger.error(f"Error in match loop for match {match.match_id}: {e}")

    async def _create_match(self, bet, player_mode = PLAYER_SOLO_MODE, is_private = False, point_mode = 11) -> Match:
        match_id = self.start_match_id
        logger.info(f"Creating match {match_id}")
        match = TressetteMatch(match_id, bet, player_mode=player_mode, point_mode=point_mode)
        match.set_public(not is_private)
        self.matches[match_id] = match
        self.start_match_id += 1
        return match

    async def create_sette_mezzo_match(self) -> Match:
        match_id = self.start_match_id
        logger.info(f"Creating match {match_id}")
        match = SetteMezzoMatch(match_id)
        self.matches[match_id] = match
        self.start_match_id += 1
        return match

    async def received_create_table(self, uid, payload):
        create_table_pkg = packet_pb2.CreateTable()
        create_table_pkg.ParseFromString(payload)
        bet = create_table_pkg.bet
        player_mode = create_table_pkg.player_mode
        point_mode = create_table_pkg.point_mode
        is_private = create_table_pkg.is_private
        if point_mode not in [11, 21]:
            print(f"Invalid point mode {point_mode}")
            return
        
        if player_mode != PLAYER_DUO_MODE and player_mode != PLAYER_SOLO_MODE:
            print(f"Invalid player mode {player_mode}")
            return
        if player_mode == PLAYER_DUO_MODE:
            # point need to be 21
            point_mode = 21

        # check if user has enough gold to create table this bet
        user_info = await users_info_mgr.get_user_info(uid)
        if user_info.gold < self.get_gold_minimum_play():
            print(f"User {uid} not enough gold")
            return
        if await self.is_user_in_match(uid):
            return
        
        if create_table_pkg.bet_mode:
            if user_info.gold < bet * tress_config.get('bet_multiplier_min'):
                return
        else: # in review
            bet = 0
            # get fee this user
            fee = tress_config.get('fee_mode_no_bet')
            if user_info.gold < fee:
                return
            user_info.add_gold(-fee)
            await user_info.commit_gold()
            await user_info.send_update_money()

        
        match = await self._create_match(bet, player_mode, is_private, point_mode)
        await self.user_join_match(match, uid)

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
    
    async def find_a_suitable_match_quickplay(self, gold) -> Match:
        expect_match = None
        best_match = None
        best_diff = float('inf')
        should_choose_duo = random.choice([True, False]) # 50 %
        
        for match_id, match in self.matches.items():
            if not match.is_public:
                continue
            if match.bet == 0:
                # Bet = 0 is for review
                continue

            if match.player_mode == PLAYER_DUO_MODE and not should_choose_duo:
                continue
            if match.state == MatchState.WAITING and not match.check_room_full():
                # For current, only solo mode for quick play
                min_gold = match.get_min_gold_play()
                
                # Ensure user has enough gold to play
                if gold >= min_gold:
                    # Prioritize match with gold closest to 2 * min_gold_play
                    diff = abs((3 * min_gold) - gold)
                    
                    if best_match is None or diff < best_diff:
                        best_match = match
                        best_diff = diff
                        
        expect_match = best_match
        return expect_match

    
    async def user_join_match(self, match: Match, uid: int):
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
    async def handle_user_leave_match(self, uid: int, reason = 0) -> LeaveMatchErrors:
        match_id = self.user_matchids.get(uid)

        if not match_id:
            return LeaveMatchErrors.NOT_IN_MATCH
        
        match = await self.get_match_of_user(uid)
        if not match.can_quit_game():
            return LeaveMatchErrors.MATCH_STARTED
        
        await match.user_leave(uid, reason)
        self.user_matchids.pop(uid)

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
            # skip private match
            if match.is_public is False:
                continue
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

        # pkg = packet_pb2.TableList()
        # pkg.table_ids.extend([1, 2, 3, 4, 5,6,7])
        # pkg.bets.extend([100000, 2000000, 300000, 400000, 5000000, 400000, 5000000])
        # pkg.player_modes.extend([2,2,2,2,2,2,2])
        # pkg.num_players.extend([1,2,1,2,1,2,2])
        await game_vars.get_game_client().send_packet(uid, CMDs.TABLE_LIST, pkg)

    async def _prioritize_matches(self, matches: dict[int, Match], uid: int) -> list[Match]:
        MAX_MATCHES = 20  # Limit of prioritized matches
        user = await users_info_mgr.get_user_info(uid)
        user_gold = user.gold

        # Separate matches by state
        waiting_matches = [match for match in matches.values() if match.state == MatchState.WAITING]
        other_matches = [match for match in matches.values() if match.state != MatchState.WAITING]

        # Sort matches by bet proximity to user's gold
        waiting_matches.sort(key=lambda match: abs(match.bet * tress_config.get('bet_multiplier_min') - user_gold))
        other_matches.sort(key=lambda match: abs(match.bet * tress_config.get('bet_multiplier_min') - user_gold))

        # Combine matches, prioritizing waiting matches
        prioritized_matches = waiting_matches + other_matches

        # Return the top matches, limited to `MAX_MATCHES`
        return prioritized_matches[:MAX_MATCHES]

    async def join_match(self, uid, match_id):
        match = await self.get_match(match_id)

        # check other conditions to join match
        if not match:
            return
        await self.user_join_match(match, uid)

    async def _handle_case_bet_in_review(self, uid):
        match = await self._create_match(0)
        
        print(f"User {uid} join match {match.match_id}")
        await self.user_join_match(match, uid=uid)


    async def _handle_quick_play(self, uid: int):
        print(f"User {uid} quick play")
        # STEP 1: CHECK IF USER IS IN A MATCH
        match = await self.get_match_of_user(uid)
        if match:
            print(f"User {uid} is in a match, reconnecting")
            await match.user_reconnect(uid)
            return
    
        user = await users_info_mgr.get_user_info(uid)
        if user.gold < self.get_gold_minimum_play():
            print(f"User {uid} not enough gold")
            return

        # STEP JOIN A MATCH
        if user.game_count == 0:
            # for new user, should create new match instead
            match = await self._create_match(1000, PLAYER_SOLO_MODE, False, 11)
        else:
            match = await self.find_a_suitable_match_quickplay(user.gold)
            if not match:
                # Expect bet
                ccu = await game_vars.get_game_live_performance().get_ccu()
                if ccu < 20:
                    expect_bet = int(user.gold / (tress_config.get('bet_multiplier_min') * 3))
                    expect_bet = min(expect_bet, 200000) # prevent spam bot
                elif ccu < 100:
                    expect_bet = int(user.gold / (tress_config.get('bet_multiplier_min') * 4))
                else:
                    expect_bet = int(user.gold / (tress_config.get('bet_multiplier_min') * 2))
                bet = self.find_largest_bet_below(expect_bet)

                point_mode = random.choice([11, 21])
                match = await self._create_match(bet, PLAYER_SOLO_MODE, False, point_mode)
        
        print(f"User {uid} join match {match.match_id}")
        await self.user_join_match(match, uid=uid)

        write_log(uid, "quick_play", "", [])
    
    
    async def  _handle_user_join_by_match_id(self, uid, match_id):
        # check if user is in a match
        is_in_match = await self.is_user_in_match(uid)
        if is_in_match:
            await self._send_response_join_table(uid, JoinMatchErrors.ALREADY_IN_MATCH)
            return

        match = await self.get_match(match_id)
        if not match:
            await self._send_response_join_table(uid, JoinMatchErrors.MATCH_NOT_FOUND)
            return
        
        if match.state != MatchState.WAITING:
            await self._send_response_join_table(uid, JoinMatchErrors.MATCH_STARTED)
            return
        
        if match.check_room_full():
            await self._send_response_join_table(uid, JoinMatchErrors.FULL_ROOM)
            return
        user_info = await users_info_mgr.get_user_info(uid)
        if user_info.gold < match.get_min_gold_play():
            await self._send_response_join_table(uid, JoinMatchErrors.NOT_ENOUGH_GOLD)
            return
        
        await self.user_join_match(match, uid)

    async def _send_response_join_table(self, uid, status):
        join_pkg = packet_pb2.JoinTableResponse()
        join_pkg.error = status.value
        await game_vars.get_game_client().send_packet(uid, CMDs.JOIN_TABLE_BY_ID, join_pkg)

    async def receive_user_join_match(self, uid, payload):
        join_pkg = packet_pb2.JoinTableById()
        join_pkg.ParseFromString(payload)
        match_id = join_pkg.match_id
        await self._handle_user_join_by_match_id(uid, match_id)

    async def receive_quick_play(self, uid, payload):
        quick_play_pkg = packet_pb2.QuickPlay()
        quick_play_pkg.ParseFromString(payload)
        await self._handle_quick_play(uid)

    def find_largest_bet_below(self, expect_bet):
        tresette_bets = tress_config.get("bets")
        suitable_bet = tresette_bets[0]
        
        for bet in tresette_bets:
            if bet <= expect_bet:
                if suitable_bet is None or bet > suitable_bet:
                    suitable_bet = bet
        
        return suitable_bet
    
    async def receive_game_action_napoli(self, uid, payload):
        match = await self.get_match_of_user(uid)
        if match:
            await match.receive_game_action_napoli(uid, payload)

    def get_gold_minimum_play(self):
        return tress_config.get('bets')[0] * tress_config.get('bet_multiplier_min')
    
    async def receive_user_return_to_table(self, uid):
        match = await self.get_match_of_user(uid)
        if match:
            match.user_return_to_table(uid)

    async def user_ready(self, uid):
        match = await self.get_match_of_user(uid)
        if match:
            match.user_ready(uid)