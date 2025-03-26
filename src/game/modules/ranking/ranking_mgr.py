

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from src.base.network.packets import packet_pb2
from src.game.cmds import CMDs
from src.postgres.sql_models import RankingSeasonSchema, RankingRewardsSchema
from src.postgres.orm import PsqlOrm
import bisect
from src.game.game_vars import game_vars

class RankingSeasonInfo:
    time_start: datetime
    time_end: datetime
    season_id: int

class RankingPlayerInfo:
    uid: int
    score: int

class RankingMgr:
    season_info: RankingSeasonInfo = None
    players: list[RankingPlayerInfo] = [] # sorted, rank 1, 2, 3, ...
    player_map: dict[int, RankingPlayerInfo] = {} # uid -> player
    async def end_season(self):
        # calculate rewards, winner
        for i, player in min(enumerate(self.players), 3):
            reward = RankingRewardsSchema()
            reward.season_id = self.season_info.season_id
            reward.uid = player.uid
            reward.rank = i + 1
            reward.gold_reward = 1000
            async with PsqlOrm.get().session() as session:
                session.add(reward)
                await session.commit
        

        # update season info in db
        async with PsqlOrm.get().session() as session:
            result = await session.execute(
                select(RankingSeasonSchema).where(RankingSeasonSchema.season_id == self.season_info.season_id)
            )
            season = result.scalars().first()
            season.is_active = False
            await session.commit()

        self.season_info = None

    async def init_season(self):
        print("Initializing ranking season")
        # load season info from db
        async with PsqlOrm.get().session() as session:
            # Get active ranking season
            result = await session.execute(
                select(RankingSeasonSchema).where(RankingSeasonSchema.is_active == True)
            )
            active_season = result.scalars().first() 
            if active_season:
                self.season_info = RankingSeasonInfo()
                self.season_info.time_start = active_season.time_start
                self.season_info.time_end = active_season.time_end
                self.season_info.season_id = active_season.season_id

        print("Ranking season2222 initialized")
        if not self.season_info:
            await self.new_season()

        # schedule to check season end
        while True:
            await self.check_season_end()
            await asyncio.sleep(60) # check every minute
    
    async def new_season(self):
        # create new season
        self.players.clear()
        self.player_map.clear()
        async with PsqlOrm.get().session() as session:
            new_season = RankingSeasonSchema()
            new_season.time_start = datetime.now()
            new_season.time_end = datetime.now() + timedelta(days=7)
            session.add(new_season)
            await session.commit()
            self.season_info = RankingSeasonInfo()
            self.season_info.time_start = new_season.time_start
            self.season_info.time_end = new_season.time_end
            self.season_info.season_id = new_season.season_id

    async def check_season_end(self):
        if not self.season_info:
            return
        print("Checking season end")
        if datetime.now() > self.season_info.time_end:
            await self.end_season()
            await self.new_season()


    async def update_user_score(self, uid: int, score: int):
        if not self.season_info:
            return

        # Find and remove the player
        player_to_update = None
        for i, player in enumerate(self.players):
            if player.uid == uid:
                player_to_update = self.players.pop(i)  # Remove from list
                break

        if player_to_update is None:
            return  # Player not found

        # Update score
        player_to_update.score = score

        # Find new position (since the list is sorted in descending order)
        insert_pos = bisect.bisect_right([p.score for p in self.players], score, key=lambda x: -x)

        # Insert player at correct position
        self.players.insert(insert_pos, player_to_update)

    async def add_player(self, uid: int, score: int):
        if not self.season_info:
            return

        player = RankingPlayerInfo()

        player.uid = uid
        player.score = score

        # Find position to insert player
        insert_pos = bisect.bisect_right([p.score for p in self.players], score, key=lambda x: -x)

        # Insert player at correct position
        self.players.insert(insert_pos, player)
        self.player_map[uid] = player


    async def on_user_login(self, uid: int):
        if not self.season_info:
            return
        if not self.player_map.get(uid):
            await self.add_player(uid, 0)
        # send ranking info to user
        rank_pkg = packet_pb2.RankingInfo()
        rank_pkg.season_id = self.season_info.season_id
        rank_pkg.time_start = int(self.season_info.time_start.timestamp())
        rank_pkg.time_end = int(self.season_info.time_end.timestamp())

        await game_vars.get_game_client().send_packet(uid, CMDs.RANKING_INFO, rank_pkg)


        # check user has reward



