from sqlalchemy import select, update
from datetime import datetime, timedelta
from src.base.network.packets import packet_pb2
from src.constants import *
from src.game.users_info_mgr import users_info_mgr
from src.game.game_vars import game_vars
from src.game.cmds import CMDs
from src.postgres.orm import PsqlOrm
from src.postgres.sql_models import InventorySchema


class InventoryMgr:
    cache_inventory: dict[int, list[InventorySchema]] = {}

    def __init__(self):
        pass

    async def on_receive_packet(self, uid: int, cmd_id: int, payload):
        match cmd_id:
            case CMDs.USE_ITEM:
                await self.handle_use_item(uid, payload)
        return
    

    async def update_inventory(self, uid: int, item_id: int, duration_days: int):
        now_ts = int(datetime.now().timestamp())
        duration_sec = duration_days * 86400

        inventory_list = await self.get_inventory(uid)
        item = next((i for i in inventory_list if i.item_id == item_id), None)

        async with PsqlOrm.get().session() as session:
            if item is None:
                item = InventorySchema(
                    user_id=uid,
                    item_id=item_id,
                    expire_time=now_ts + duration_sec
                )
                session.add(item)
                inventory_list.append(item)
            else:
                if item.expire_time == -1: # permanent item
                    return
                if item.expire_time < now_ts:
                    item.expire_time = now_ts
                item.expire_time += duration_sec
                await session.execute(
                    update(InventorySchema).where(
                        InventorySchema.user_id == uid,
                        InventorySchema.item_id == item_id
                    ).values(expire_time=item.expire_time)
                )

            await session.commit()

        self.cache_inventory[uid] = inventory_list

    async def get_inventory(self, uid: int) -> list[InventorySchema]:
        if uid in self.cache_inventory:
            return self.cache_inventory[uid]

        async with PsqlOrm.get().session() as session:
            result = await session.execute(
                select(InventorySchema).where(InventorySchema.user_id == uid)
            )
            inventory = result.scalars().all()
            self.cache_inventory[uid] = inventory
            return inventory
    
    async def send_user_inventory(self, uid: int):
        inventory_list = await self.get_inventory(uid)
        pkg = packet_pb2.UserInventory()
        
        for item in inventory_list:
            inv_item = pkg.items.add()
            inv_item.item_id = item.item_id
            inv_item.expire_time = item.expire_time
        
        await game_vars.get_game_client().send_packet(uid, CMDs.USER_INVENTORY, pkg)

    async def handle_use_item(self, uid: int, payload):
        inventory_list = await self.get_inventory(uid)
        if not inventory_list:
            return
        
        use_item_pkg = packet_pb2.UseItem()
        use_item_pkg.ParseFromString(payload)
        item_id = use_item_pkg.item_id
        item = next((i for i in inventory_list if i.item_id == item_id), None)
        if not item:
            print(f"User {uid} tried to use an item that does not exist: {item_id}")
            return
        if item.expire_time != PERMANENT_ITEM_EXPIRE_TIME and item.expire_time < int(datetime.now().timestamp()):
            print(f"User {uid} tried to use an expired item: {item_id}")
            return
        
        # Handle the item usage logic here
        # For example, if it's a frame item, apply it to the user's avatar
        if not item_id in AVATAR_FRAME_IDS:
            print(f"User {uid} tried to use an invalid item: {item_id}")
            return
        
        user_info = await users_info_mgr.get_user_info(uid)
        user_info.avatar_frame = item_id
        await user_info.commit_to_database('avatar_frame')

        


        

        
       