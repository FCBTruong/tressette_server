import json
from sqlalchemy import select, update
from datetime import datetime, timedelta
from src.base.logs.logs_mgr import write_log
from src.base.network.packets import packet_pb2
from src.config.settings import settings
from src.constants import *
from src.game.users_info_mgr import users_info_mgr
from src.game.game_vars import game_vars
from src.game.cmds import CMDs
from src.postgres.orm import PsqlOrm
from src.postgres.sql_models import InventorySchema
from src.game.tressette_config import inventory_shop_config as shop_config


class InventoryMgr:
    cache_inventory: dict[int, list[InventorySchema]] = {}

    def __init__(self):
        pass

    async def on_receive_packet(self, uid: int, cmd_id: int, payload):
        match cmd_id:
            case CMDs.USE_ITEM:
                await self.receive_request_use_item(uid, payload)
            case CMDs.CHEAT_ITEM:
                await self.handle_cheat_item(uid, payload)
            case CMDs.BUY_ITEM:
                await self.handle_buy_item(uid, payload)
        return
    
    # duration = -1 means permanent
    async def update_inventory(self, uid: int, item_id: int, duration_sec: int, value: int = 0):
        now_ts = int(datetime.now().timestamp())
        item_type = item_id // 1000  # your scheme

        # allow permanent (-1); reject non-positive durations except -1
        if item_type != ITEM_TYPE_STACKABLE and duration_sec <= 0 and duration_sec != -1:
            return
        

        inventory_list = await self.get_inventory(uid)
        item = next((i for i in inventory_list if i.item_id == item_id), None)

        async with PsqlOrm.get().session() as session:
            if item is None:
                # create new
                expire_time = (
                    -1 if (duration_sec == -1 or item_type == ITEM_TYPE_STACKABLE)
                    else now_ts + duration_sec
                )
                item = InventorySchema(
                    user_id=uid,
                    item_id=item_id,
                    expire_time = expire_time,
                    value=value if item_type == ITEM_TYPE_STACKABLE else 0,
                )
                session.add(item)
                inventory_list.append(item)
            else:
                session.add(item)
                if item_type == ITEM_TYPE_STACKABLE:
                    item.value += value
                else:
                    if duration_sec == -1:
                        # make (or keep) permanent
                        item.expire_time = -1
                    else:
                        # extend time
                        if item.expire_time == -1:
                            # already permanent -> no change
                            pass
                        else:
                            if item.expire_time < now_ts:
                                item.expire_time = now_ts
                            item.expire_time += duration_sec
            await session.flush()
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
            inv_item.value = item.value
        
        await game_vars.get_game_client().send_packet(uid, CMDs.USER_INVENTORY, pkg)
    
    async def send_inventory_shop_config(self, uid: int):
        pkg = packet_pb2.InventoryShopConfig()
        
        for item_id, shop in shop_config.items():
            shop_item = pkg.items.add()
            shop_item.item_id = int(item_id)
            for pack in shop['shop']:
                pack_item = shop_item.packs.add()
                pack_item.id = pack['id']
                pack_item.price = pack['price']
                pack_item.duration = pack['duration']
        await game_vars.get_game_client().send_packet(uid, CMDs.INVENTORY_SHOP_CONFIG, pkg)
            
    async def receive_request_use_item(self, uid: int, payload):
        use_item_pkg = packet_pb2.UseItem()
        use_item_pkg.ParseFromString(payload)
        item_id = use_item_pkg.item_id
        await self.handle_use_item(uid, item_id)
    
    async def handle_use_item(self, uid: int, item_id: int):
        inventory_list = await self.get_inventory(uid)
        if not inventory_list:
            return
        
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

        if user_info.avatar_frame == item_id:
            print(f"User {uid} tried to use an item they already have equipped: {item_id}")
            return

        user_info.avatar_frame = item_id
        await user_info.commit_to_database('avatar_frame')

        # send back to user
        use_item_pkg = packet_pb2.UseItem()
        use_item_pkg.item_id = item_id
        await game_vars.get_game_client().send_packet(
            uid, CMDs.USE_ITEM, use_item_pkg
        )
        write_log(uid, "use_item", item_id, [])
    
    async def handle_cheat_item(self, uid: int, payload):
        if not settings.ENABLE_CHEAT:
            return
        
        cheat_item_pkg = packet_pb2.CheatItem()
        cheat_item_pkg.ParseFromString(payload)
        item_id = cheat_item_pkg.item_id
        duration = cheat_item_pkg.duration # seconds
        await self._cheat_item(uid, item_id, duration)
    
    async def _cheat_item(self, uid, item_id: int, duration_sec: int):
        type_id = item_id // 1000  # your scheme
        value = 0
        if type_id == ITEM_TYPE_STACKABLE:
            value = duration_sec  # for stackable items, use duration as value
        
        await self.update_inventory(uid, item_id, duration_sec, value)
        await self.send_user_inventory(uid)
        
    async def handle_buy_item(self, uid: int, payload):
        buy_item_pkg = packet_pb2.BuyItem()
        buy_item_pkg.ParseFromString(payload)
        item_id = buy_item_pkg.item_id
        pack_id = buy_item_pkg.pack_id

        if str(item_id) not in shop_config:
            print(f"User {uid} tried to buy an invalid item: {item_id}")
            return
        shop = shop_config[str(item_id)]['shop']
        # find pack
        pack = None
        for s in shop:
            if s['id'] == pack_id:
                pack = s
                break
        if pack is None:
            print(f"User {uid} tried to buy an item with invalid pack: {pack_id}")
            return
        price = pack['price']
        duration = pack['duration'] # days
        
        # Check if user has enough gold
        user_info = await users_info_mgr.get_user_info(uid)
        if user_info.gold < price:
            print(f"User {uid} tried to buy item {item_id} with insufficient gold")
            return
        # Deduct gold
        user_info.add_gold(-price)
        await user_info.commit_to_database('gold')
        await user_info.send_update_money()
        # Update inventory
        duration_sec = PERMANENT_ITEM_EXPIRE_TIME if duration == -1 else duration * 86400  # convert days to seconds
        await self.update_inventory(uid, item_id, duration_sec=duration_sec)  
        await self.send_user_inventory(uid)
        await game_vars.get_game_client().send_packet(
            uid, CMDs.BUY_ITEM, buy_item_pkg
        )
        write_log(uid, "buy_item", item_id, [price, pack_id, duration])

        

        
       