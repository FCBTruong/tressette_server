import asyncio
from enum import Enum
from datetime import datetime, timedelta
import logging

from src.base.network.packets import packet_pb2
from src.game.cmds import CMDs
from src.game.game_vars import game_vars

class MatchState(Enum):
    WAITING = "waiting"
    IN_PROGRESS = "in_progress"
    FINISHED = "finished"

# Configure the logger
logging.basicConfig(
    level=logging.INFO,  # Set logging level
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",  # Log format
)
logger = logging.getLogger("game_match")  # Name your logger

class Match:
    def __init__(self, match_id):
        self.match_id = match_id
        self.user_ids = []
        self.state = MatchState.WAITING
        self.start_time = None
        self.end_time = None
        self.game_mode = None
        self.player_mode = None

    def start_match(self):
        self.state = MatchState.IN_PROGRESS
        self.start_time = datetime.now()

    def end_match(self):
        self.state = MatchState.FINISHED
        self.end_time = datetime.now()

    async def user_join(self, user_id):
        # send to others that user has joined
        for uid in self.user_ids:
            pass
        self.user_ids.append(user_id)
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

    def check_can_join(self, user_id):
        if self.state == MatchState.WAITING:
            return True
        return False
    
    def check_room_full(self):
        return len(self.user_ids) >= 4
    
    async def _send_game_info(self, uid):
        logger.info(f"Sending game info to user {uid}")
        game_info = packet_pb2.GameInfo()
        game_info.match_id = self.match_id
        await game_vars.get_game_client().send_packet(uid, CMDs.GAME_INFO, game_info)

class MatchManager:
    def __init__(self):
        self.start_match_id = 1000
        self.matches: dict[int, Match] = {}
        self.users_by_match: dict[int, int] = {}

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

    async def get_match_of_user(self, user_id):
        pass

    async def on_end_match(self, match_id):
        match = self.matches.get(match_id)
        if match:
            user_ids = match.user_ids
            for user_id in user_ids:
                self.users_by_match.pop(user_id)

    async def is_user_in_match(self, user_id):
        return user_id in self.users_by_match
    
    async def get_free_match(self) -> Match:
        for match_id, match in self.matches.items():
            if match.state == MatchState.WAITING and not match.check_room_full():
                return Match
        return None
    
    async def user_join_match(self, match: Match, uid: int):
        self.users_by_match[uid] = match
        await  match.user_join(uid)
