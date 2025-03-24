

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from src.postgres.sql_models import RankingSeasonSchema
from src.postgres.orm import PsqlOrm

class RankingSeasonInfo:
    time_start: datetime
    time_end: datetime
    season_id: int

class RankingMgr:
    season_info: RankingSeasonInfo = None
    async def end_season(self):
        pass

    async def init_season(self):
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
                return
            
        if not self.season_info:
            await self.new_season()

        # schedule to check season end
        while True:
            await self.check_season_end()
            await asyncio.sleep(60) # check every minute
    
    async def new_season(self):
        # create new season
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
        if datetime.now().date() > self.season_info.time_end:
            await self.end_season()
            await self.new_season()

    pass



