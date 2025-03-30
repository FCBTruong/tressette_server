

from datetime import datetime
import json
from src.base.logs.logs_mgr import write_log
from src.base.network.packets import packet_pb2
from src.base.payment import apple_pay, google_pay
from src.game.users_info_mgr import users_info_mgr
from src.game.game_vars import game_vars
from src.game.cmds import CMDs
from src.postgres.sql_models import UserInfoSchema, AppleTransactions
from src.postgres.orm import PsqlOrm
from src.base.payment import paypal_pay

# load json config
# Load the JSON configuration file
with open('config/shop.json', 'r') as file:
    config = json.load(file)

async def on_receive_packet(uid, cmd_id, payload):
    match cmd_id:
        case CMDs.PAYMENT_GOOGLE_CONSUME:
            print("PAYMENT_GOOGLE_CONSUME")
            await _handle_google_consume(uid, payload)
        case CMDs.PAYMENT_APPLE_CONSUME:
            print("PAYMENT_APPLE_CONSUME")
            await _handle_apple_consume(uid, payload)
        case CMDs.PAYMENT_PAYPAL_REQUEST_ORDER:
            await _handle_paypal_request_order(uid, payload)
        case _:
            pass

async def _handle_apple_consume(uid, payload):
    pkg = packet_pb2.PaymentAppleConsume()
    pkg.ParseFromString(payload)
    print(f"User {uid} consume apple payment {pkg.receipt_data}")
    receipt_data = pkg.receipt_data
    pack_id = pkg.pack_id

    purchase_info = await apple_pay.verify_apple_receipt(uid, receipt_data)

    if not purchase_info: # not purchased yet
        print("Invalid purchase")
        return
    
    print("Buy success: ", purchase_info)

    in_app = purchase_info.get("receipt").get("in_app")
    for item in in_app:
        buy_pack_id = item.get("product_id")
        transaction_id = item.get("transaction_id")
        original_transaction_id = item.get("original_transaction_id")
        quantity = int(item.get("quantity", 1))
        purchase_date = item.get("purchase_date")
        original_purchase_date = item.get("original_purchase_date")
        is_trial_period = item.get("is_trial_period", "false").lower() == "true"
        in_app_ownership_type = item.get("in_app_ownership_type", "PURCHASED")

        # tell client that server received the transaction, so client can finish the transaction
        await _send_finished_apple_transaction(uid, buy_pack_id)
        
         # Check and marked transaction id to avoid duplicate consume
        async with PsqlOrm.get().session() as session:
            apple_transaction = await session.get(AppleTransactions, transaction_id)
            if apple_transaction:
                print("Transaction already consumed")
                continue
            
            # Create a new AppleTransactions object with all fields
            new_transaction = AppleTransactions(
                transaction_id=transaction_id,
                original_transaction_id=original_transaction_id,
                user_id=uid,
                product_id=buy_pack_id,
                quantity=quantity,
                purchase_date = purchase_date,
                original_purchase_date = original_purchase_date,
                is_trial_period=is_trial_period,
                in_app_ownership_type=in_app_ownership_type,
                purchase_date_ms=int(item.get("purchase_date_ms")),
                original_purchase_date_ms=int(item.get("original_purchase_date_ms"))
            )

            # Add and commit the new transaction
            session.add(new_transaction)
            await session.commit()

        await _purchase_success(uid, buy_pack_id, "apple")

# To tell user that the transaction is finished, ios call native finish transaction
async def _send_finished_apple_transaction(uid, product_id):
    pkg = packet_pb2.PaymentFinishedAppleTransaction()
    pkg.pack_id = product_id
    await game_vars.get_game_client().send_packet(uid, CMDs.PAYMENT_APPLE_FINISHED_TRANSACTION, pkg)

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

    await _purchase_success(uid, pack_id, "google")

async def _purchase_success(uid, pack_id, method):
    print(f"User {uid} purchase success pack {pack_id}")

    pack_info = get_pack_info(pack_id)
    pkg = packet_pb2.PaymentSuccess()
    pkg.gold = pack_info.get("gold")
    pkg.pack_id = pack_id

    user_info = await users_info_mgr.get_user_info(uid)

    before_gold = user_info.gold
    user_info.add_gold(pack_info.get("gold"))
    user_info.num_payments += 1

    if pack_info.get("no_ads_days"):
        timestamp_now = int(datetime.now().timestamp())
        delta_no_ads = pack_info.get("no_ads_days") * 86400
        if user_info.time_show_ads < timestamp_now:
            user_info.time_show_ads = timestamp_now + delta_no_ads
        else:
            user_info.time_show_ads += delta_no_ads

        await user_info.commit_to_database('gold', 'num_payments', 'time_show_ads')
        await user_info.send_update_ads()
    else:
        # save to database
        await user_info.commit_to_database('gold', 'num_payments')
    
    await user_info.send_update_money()

    # send to user
    await game_vars.get_game_client().send_packet(uid, CMDs.PAYMENT_SUCCESS, pkg)

    write_log(uid, "payment_success", method, [pack_id, before_gold, user_info.gold])

def get_pack_info(pack_id):
    packs = config.get("packs")
    for pack in packs:
        if pack.get("pack_id") == pack_id:
            return pack
    web_packs = config.get("web_packs")
    for pack in web_packs:
        if pack.get("pack_id") == pack_id:
            return pack
    if config.get("first_buy") and pack_id == config.get("first_buy").get("pack_id"):
        return config.get("first_buy")

    return None

def get_shop_config():
    return config

async def send_shop_config(uid, platform):
    pkg = packet_pb2.ShopConfig()
    shop_config = get_shop_config()
    pack_ids = []
    golds = []
    prices = []
    currencies = []
    no_ads_days = []
    
    if platform == "web":
        packs = shop_config.get("web_packs")
    else:
        packs = shop_config.get("packs")
        
    for p in packs:
        pack_ids.append(p.get("pack_id"))
        golds.append(p.get("gold"))
        prices.append(p.get("price"))
        currencies.append(p.get("currency"))
        no_ads_days.append(p.get("no_ads_days", 0))

    pkg.pack_ids.extend(pack_ids)
    pkg.golds.extend(golds)
    pkg.prices.extend(prices)
    pkg.currencies.extend(currencies)
    pkg.no_ads_days.extend(no_ads_days)
    await game_vars.get_game_client().send_packet(uid, CMDs.SHOP_CONFIG, pkg)
    print(f"Send shop config to user {uid}", CMDs.SHOP_CONFIG)

async def _handle_paypal_request_order(uid, payload):
    pkg = packet_pb2.PaymentPaypalRequestOrder()
    pkg.ParseFromString(payload)
    pack_id = pkg.pack_id
    
    pack_info = get_pack_info(pack_id)
    if not pack_info:
        print("Invalid pack")
        return
    
    amount = pack_info.get("price")
    currency = pack_info.get("currency")

    order_url = await paypal_pay.create_paypal_order(uid, amount, pack_id, currency)
    if not order_url:
        print("Failed to create PayPal order")
        return

    pkg = packet_pb2.PaymentPaypalOrder()
    pkg.order_url = order_url
    await game_vars.get_game_client().send_packet(uid, CMDs.PAYMENT_PAYPAL_REQUEST_ORDER, pkg)
    print(f"Send PayPal order to user {uid}")
