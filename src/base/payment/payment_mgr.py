

import json
from src.base.network.packets import packet_pb2
from src.base.payment import google_pay
from src.game.game_vars import game_vars
from src.game.cmds import CMDs
from src.postgres.sql_models import UserInfoSchema
from src.postgres.orm import PsqlOrm

# load json config
# Load the JSON configuration file
with open('config/shop.json', 'r') as file:
    config = json.load(file)

async def on_receive_packet(uid, cmd_id, payload):
    match cmd_id:
        case CMDs.PAYMENT_GOOGLE_CONSUME:
            print("PAYMENT_GOOGLE_CONSUME")
            await _handle_google_consume(uid, payload)
        case _:
            pass

async def _handle_google_consume(uid, payload):
    pkg = packet_pb2.PaymentGoogleConsume()
    pkg.ParseFromString(payload)
    print(f"User {uid} consume google payment {pkg.purchase_token}")
    purchase_token = pkg.purchase_token
    pack_id = pkg.sku

    purchase_info = await google_pay.verify_purchase(purchase_token=purchase_token, product_id=pack_id)

    if not purchase_info or purchase_info.get("purchaseState") != 0: # not purchased yet
        print("Invalid purchase")
        return
    print("Purchase: ", purchase_info)

    # check if acknowledged
    if purchase_info.get("consumptionState") == 1:
        print("Purchase already consumed")
        return
    
    consumed_state = await google_pay.consume_purchase(purchase_token=purchase_token, product_id=pack_id)
    if not consumed_state:
        print("Failed to consume purchase")
        return
    
    print("Consume success")

    await _purchase_success(uid, pack_id)

async def _purchase_success(uid, pack_id):
    print(f"User {uid} purchase success pack {pack_id}")

    pack_info = get_pack_info(pack_id)
    pkg = packet_pb2.PaymentSuccess()
    pkg.gold = pack_info.get("gold")

    async with PsqlOrm.get().session() as session:
        user_model = await session.get(UserInfoSchema, uid)
        if user_model:
            user_model.gold += pack_info.get("gold")
        await session.commit()
        # send packet update money
        pkg_money = packet_pb2.UpdateMoney()
        pkg_money.gold = user_model.gold
        await game_vars.get_game_client().send_packet(uid, CMDs.UPDATE_MONEY, pkg)

    # send to user
    await game_vars.get_game_client().send_packet(uid, CMDs.PAYMENT_SUCCESS, pkg)

def get_pack_info(pack_id):
    packs = config.get("packs")
    for pack in packs:
        if pack.get("pack_id") == pack_id:
            return pack
    return None