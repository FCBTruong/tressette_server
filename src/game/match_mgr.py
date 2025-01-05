# Configure the logger

import asyncio
import logging

from src.game.match import LeaveMatchErrors, Match, MatchState


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
        print(f"End match {match_id}")
        match = self.matches.get(match_id)
        if match:
            for player in match.players:
                self.user_matchids.pop(player.uid)
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
        is_in_match = await self.is_user_in_match(uid)
        if is_in_match:
            print(f"User {uid} is in a match, auto leave")
            match = await self.get_match_of_user(uid)
            if match.state == MatchState.WAITING:
                await self.user_leave_match(uid)

    async def user_play_card(self, uid: int, payload):
        match = await self.get_match_of_user(uid)
        if match:
            await match.user_play_card(uid, payload)