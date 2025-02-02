

from src.postgres.orm import PsqlOrm
from src.postgres.sql_models import UserInfoSchema
from sqlalchemy import update as sa_update


class UserInfo:
    uid: int
    name: str
    gold: int
    level: int
    avatar: str
    avatar_third_party: str
    def __init__(self, uid: int, name: str, gold: int, level: int, avatar: str, avatar_third_party: str):
        self.uid = uid
        self.name = name
        self.gold = gold
        self.level = level
        self.avatar = avatar
        self.avatar_third_party = avatar_third_party

        # Set default values
        if self.avatar_third_party is None:
            self.avatar_third_party = ""

    async def commit_to_database():
        pass

    def update_avatar(self, avatar: str):
        self.avatar = avatar

    def update_gold(self, gold: int):
        if gold < 0:
            # Do not allow negative gold
            print("Cannot set gold to negative value")
            return
        self.gold = gold

    def add_gold(self, gold: int):
        self.gold += gold
        if self.gold < 0:
            self.gold = 0

    async def commit_gold(self):
        async with PsqlOrm.get().session() as session:
            await session.execute(
                sa_update(UserInfoSchema)
                .where(UserInfoSchema.uid == self.uid)
                .values(gold=self.gold)
            )
            await session.commit()

    async def commit_avatar(self):
        async with PsqlOrm.get().session() as session:
            await session.execute(
                sa_update(UserInfoSchema)
                .where(UserInfoSchema.uid == self.uid)
                .values(avatar=self.avatar)
            )
            await session.commit()