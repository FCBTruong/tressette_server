

from src.base.network.packets import packet_pb2
from src.game.cmds import CMDs
from src.game.game_vars import game_vars
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
    is_active: bool
    last_time_received_support: int
    exp: int
    game_count: int
    win_count: int
    received_startup: bool
    login_type: int
    num_payments: int
    time_show_ads: int
    time_ads_reward: int
    num_claimed_ads: int
    def __init__(self, uid: int, name: str, gold: int, level: int, avatar: str, avatar_third_party: str, is_active: bool,
                 last_time_received_support: int, received_startup: bool = True):
        self.uid = uid
        self.name = name
        self.gold = gold
        self.level = level
        self.avatar = avatar
        self.avatar_third_party = avatar_third_party
        self.is_active = is_active
        self.last_time_received_support = last_time_received_support
        self.received_startup = received_startup

        # Set default values
        if self.avatar_third_party is None:
            self.avatar_third_party = ""

        if self.level is None:
            self.level = 1

        if self.name is None:
            self.name = "tressette player"

        if self.avatar is None:
            self.avatar = "0"

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

    def add_exp(self, exp: int):
        self.exp += exp

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


    async def send_update_money(self):
        pkg_money = packet_pb2.UpdateMoney()
        pkg_money.gold = self.gold
        await game_vars.get_game_client().send_packet(self.uid, CMDs.UPDATE_MONEY, pkg_money)
    
    async def send_update_ads(self):
        pkg_ads = packet_pb2.UpdateAds()
        pkg_ads.time_show_ads = self.time_show_ads
        await game_vars.get_game_client().send_packet(self.uid, CMDs.UPDATE_ADS, pkg_ads)

    async def commit_to_database(self, *fields):
        """
        Updates the specified fields for the UserInfoSchema table using the current instance's values.

        Parameters:
        - fields: A list of field names to update. Only the specified fields will be updated.
        """
        # Collect field values from self
        update_data = {field: getattr(self, field) for field in fields if hasattr(self, field)}

        if not update_data:
            return  # No fields to update

        async with PsqlOrm.get().session() as session:
            await session.execute(
                sa_update(UserInfoSchema)
                .where(UserInfoSchema.uid == self.uid)
                .values(**update_data)
            )
            await session.commit()