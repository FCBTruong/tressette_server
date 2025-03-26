

import asyncio
from datetime import datetime, timedelta, timezone
import json
import random

from sqlalchemy import select
from src.base.network.packets import packet_pb2
from src.game.users_info_mgr import users_info_mgr
from src.game.cmds import CMDs
from src.postgres.sql_models import RankingPlayersSchema, RankingSeasonSchema, RankingRewardsSchema
from src.postgres.orm import PsqlOrm
import bisect
from src.game.game_vars import game_vars
from src.config.settings import settings

class RankingSeasonInfo:
    time_start: datetime
    time_end: datetime
    season_id: int

class RankingPlayerInfo:
    uid: int
    score: int

with open('config/ranking.json', 'r') as file:
    ranking_config = json.load(file)
rewards = ranking_config["rewards"]
class RankingMgr:
    season_info: RankingSeasonInfo = None
    players: list[RankingPlayerInfo] = [] # sorted, rank 1, 2, 3, ...
    player_map: dict[int, RankingPlayerInfo] = {} # uid -> player


    
    async def end_season(self):
        # calculate rewards, winner
        for i in range(min(len(self.players), len(rewards))):
            player = self.players[i]
            reward = RankingRewardsSchema()
            reward.season_id = self.season_info.season_id
            reward.uid = player.uid
            reward.rank = i + 1
            reward.gold_reward = rewards[i]
            async with PsqlOrm.get().session() as session:
                session.add(reward)
                await session.commit()
        

        # update season info in db
        async with PsqlOrm.get().session() as session:
            result = await session.execute(
                select(RankingSeasonSchema).where(RankingSeasonSchema.season_id == self.season_info.season_id)
            )
            season = result.scalars().first()
            season.is_active = False
            await session.commit()

        self.season_info = None

    async def on_receive_packet(self, uid: int, cmd_id: int, payload):
        match cmd_id:
            case CMDs.RANKING_INFO:
                await self.send_ranking_info(uid)

        return
    
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

            # load players
            result = await session.execute(
                select(RankingPlayersSchema).where(RankingPlayersSchema.season_id == self.season_info.season_id)
            )
            players = result.scalars().all()
            for player in players:
                player_info = RankingPlayerInfo()
                player_info.uid = player.uid
                player_info.score = player.score
                self.players.append(player_info)
                self.player_map[player.uid] = player_info

            # if settings.DEV_MODE:
            #     self.season_info.time_end = datetime.now() + timedelta(seconds=20) # add 200 seconds for testing


        if not self.season_info:
            await self.new_season()

        # schedule to check season end
        while True:
            await self.check_season_end()
            await asyncio.sleep(10) # check every minute
    
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

        # Update in db
        async with PsqlOrm.get().session() as session:
            result = await session.execute(
                select(RankingPlayersSchema)
                .where(
                    (RankingPlayersSchema.uid == uid) &
                    (RankingPlayersSchema.season_id == self.season_info.season_id)
                )
            )
            player_db = result.scalars().first()
            
            if player_db:
                player_db.score = score
                await session.commit()

        # Extract scores but negate them (to handle descending order as ascending)
        scores = [-p.score for p in self.players]

        # Find the correct insertion position
        insert_pos = bisect.bisect_left(scores, -player_to_update.score)

        # Insert player at the correct position
        self.players.insert(insert_pos, player_to_update)

    async def add_player(self, uid: int):
        if not self.season_info:
            return

        player = RankingPlayerInfo()

        player.uid = uid
        player.score = 0

        # save to db
        async with PsqlOrm.get().session() as session:
            new_player = RankingPlayersSchema()
            new_player.season_id = self.season_info.season_id
            new_player.uid = uid
            new_player.score = 0
            session.add(new_player)
            await session.commit()

        self.players.append(player)
        self.player_map[uid] = player


    async def on_user_login(self, uid: int):
        if not self.season_info:
            return
        if not self.player_map.get(uid):
            await self.add_player(uid)

        await self.send_ranking_info(uid)

    async def send_ranking_info(self, uid: int):
        if not self.season_info:
            return
        if not self.player_map.get(uid):
            await self.add_player(uid)

        # send ranking info to user
        rank_pkg = packet_pb2.RankingInfo()
        rank_pkg.season_id = self.season_info.season_id
        rank_pkg.time_start = int(self.season_info.time_start.timestamp())
        rank_pkg.time_end = int(self.season_info.time_end.timestamp())

        rank_pkg.rewards.extend(rewards)

        for i, player in enumerate(self.players):
            if player.uid == uid:
                rank_pkg.my_rank = i + 1
        rank_pkg.my_score = self.player_map[uid].score

        uids = []
        names = []
        scores = []
        avatars = []
   
        for i in range(min(len(self.players), 10)):
            player = self.players[i]
            u_info = await users_info_mgr.get_user_info(player.uid)
            names.append(u_info.name)
            scores.append(player.score)
            avatars.append(u_info.avatar)
            uids.append(player.uid)

        rank_pkg.uids.extend(uids)
        rank_pkg.names.extend(names)
        rank_pkg.scores.extend(scores)
        rank_pkg.avatars.extend(avatars)

        await game_vars.get_game_client().send_packet(uid, CMDs.RANKING_INFO, rank_pkg)


        # check user has reward


    async def on_user_win_game(self, uid: int):
        if not self.season_info:
            return
        player = self.player_map.get(uid)
        if not player:
            # add player to ranking
            await self.add_player(uid)   
            return
        await self.update_user_score(uid, player.score + 1)
