import asyncio
from enum import Enum
from datetime import datetime, timedelta
import logging

from src.base.network.packets import packet_pb2
from src.game.cmds import CMDs
from src.game.game_vars import game_vars
from datetime import datetime, timedelta

class MatchState(Enum):
    WAITING = "waiting"
    IN_PROGRESS = "in_progress"
    FINISHED = "finished"

PLAYER_SOLO_MODE = 2
PLAYER_DUO_MODE = 4
TRESSETTE_MODE = 0
BRISCOLA_MODE = 1

class LeaveMatchErrors(Enum):
    SUCCESS = 0
    NOT_IN_MATCH = 1
    MATCH_STARTED = 2
# Configure the logger
logging.basicConfig(
    level=logging.INFO,  # Set logging level
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",  # Log format
)
logger = logging.getLogger("game_match")  # Name your logger

class MatchPlayer:
    def __init__(self, uid):
        self.uid = uid
        self.user_name = ""
        self.gold = 0

class Match:
    def __init__(self, match_id, game_mode=TRESSETTE_MODE, player_mode=PLAYER_SOLO_MODE):
        self.match_id = match_id
        self.state = MatchState.WAITING
        self.start_time = datetime.now()
        self.end_time = None
        self.game_mode = game_mode
        self.player_mode = player_mode

        self.players: list[MatchPlayer] = []
        if player_mode == PLAYER_SOLO_MODE:
            for i in range(2):
                self.players.append(MatchPlayer(-1))
        elif player_mode == PLAYER_DUO_MODE:
            for i in range(4):
                self.players.append(MatchPlayer(-1))

    def start_match(self):
        self.state = MatchState.IN_PROGRESS
        self.start_time = datetime.now()

    def end_match(self):
        self.state = MatchState.FINISHED
        self.end_time = datetime.now()

    async def user_join(self, user_id):
        # check user in match
        for player in self.players:
            if player.uid == user_id:
                print('User already in match, can not jion')
                return
        
        # send to others that user has joined
        for player in self.players:
            if player.uid == -1:
                continue
            print(f"Send to user {player.uid} that user {user_id} has joined")
            pkg = packet_pb2.NewUserJoinMatch()
            pkg.uid = user_id

            await game_vars.get_game_client().send_packet(player.uid, CMDs.NEW_USER_JOIN_MATCH, pkg)
            pass

        # find empty slot
        for i, player in enumerate(self.players):
            if player.uid == -1:
                self.players[i].uid = user_id
                break

        await self._send_game_info(user_id)

    def update_state(self):
        if self.state == MatchState.IN_PROGRESS:
            # Example: end match after 5 minutes
            if datetime.now() > self.start_time + timedelta(minutes=5):
                self.end_match()
        elif self.state == MatchState.WAITING:
            # Example: start match when all players are ready
            if all(player['ready'] for player in self.players):
                self.start_match()

    def check_can_join(self, uid: int):
        if self.state == MatchState.WAITING:
            return True
        return False
    
    def check_room_full(self):
        for player in self.players:
            if player.uid == -1:
                return False
        return True
    
    async def _send_game_info(self, uid):
        logger.info(f"Sending game info to user {uid}")
        game_info = packet_pb2.GameInfo()
        game_info.match_id = self.match_id
        game_info.game_mode = self.game_mode
        game_info.player_mode = self.player_mode

        for player in self.players:
            game_info.uids.append(player.uid)
            # game_info.user_names.append(player.user_name)
            game_info.user_golds.append(player.gold)
 
        await game_vars.get_game_client().send_packet(uid, CMDs.GAME_INFO, game_info)

    async def user_leave(self, uid): 
        for i, player in enumerate(self.players):
            if player.uid == uid:
                self.players[i].uid = -1
                break

        # noti to others
        for player in self.players:
            if player.uid == -1:
                continue

            print(f"Send to user {player.uid} that user {uid} has left")

            pkg = packet_pb2.UserLeaveMatch()
            pkg.uid = uid
            await game_vars.get_game_client().send_packet(player.uid, CMDs.NEW_USER_JOIN_MATCH, pkg)
            pass

    async def user_reconnect(self, uid):
       await self._send_game_info(uid)

class MatchManager:
    def __init__(self):
        self.start_match_id = 1000
        self.matches: dict[int, Match] = {}
        self.user_matchids: dict[int, int] = {}

    async def create_match(self) -> Match:
        match_id = self.start_match_id
        logger.info(f"Creating match {match_id}")
        match = Match(match_id)
        self.matches[match_id] = match
        self.start_match_id += 1
        return match

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

    async def on_end_match(self, match_id):
        match = self.matches.get(match_id)
        if match:
            user_ids = match.user_ids
            for user_id in user_ids:
                self.user_matchids.pop(user_id)
            self.matches.pop(match_id)

    async def is_user_in_match(self, user_id):
        return user_id in self.user_matchids
    
    async def get_free_match(self) -> Match:
        print(f"Number match current: {len(self.matches.items())}")
        for match_id, match in self.matches.items():
            if match.state == MatchState.WAITING and not match.check_room_full():
                return match
        return None
    
    async def user_join_match(self, match: Match, uid: int):
        self.user_matchids[uid] = match.match_id
        await match.user_join(uid)

    async def user_leave_match(self, uid: int) -> LeaveMatchErrors:
        match_id = self.user_matchids.get(uid)

        if not match_id:
            return LeaveMatchErrors.NOT_IN_MATCH
        
        match = await self.get_match_of_user(uid)
        if match.state != MatchState.WAITING:
            return LeaveMatchErrors.MATCH_STARTED
        
        await match.user_leave(uid)
        self.user_matchids.pop(uid)
        return LeaveMatchErrors.SUCCESS
            
    async def user_disconnect(self, uid: int):
        is_in_match = self.is_user_in_match(uid)
        if is_in_match:
            match = await self.get_match_of_user(uid)
            if match.state == MatchState.WAITING:
                await self.user_leave_match(uid)