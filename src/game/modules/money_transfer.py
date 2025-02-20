
from src.game.users_info_mgr import users_info_mgr
from src.game.modules import game_exp

from enum import Enum

class MoneyTransferErrors(Enum):
    SUCCESS = 0
    SENDER_NOT_LEVEL = 1
    RECEIVER_NOT_LEVEL = 2
    NOT_ENOUGH_GOLD = 3
    TRANSFER_FAILED = 4
    NOT_VALID_AMOUNT = 5

class MoneyTransfer:
    def __init__(self):
        pass

    async def receive_request_transfer(uid, payload):
        error = 0
        # check this user is qualified to transfer money, level >= 5
        user_sender = await users_info_mgr.get_user_info(uid)
        level_sender = game_exp.convert_exp_to_level(user_sender.exp)
        level_min_transfer_money = game_exp.tress_config.get("level_min_transfer_money")
        if level_sender < level_min_transfer_money:
            error = MoneyTransferErrors.SENDER_NOT_LEVEL
            return
        
        des_uid = payload.des_uid
        amount = payload.amount

