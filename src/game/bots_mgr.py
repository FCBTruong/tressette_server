

import random
from src.constants import AVATAR_IDS
from src.game.models import UserInfo
from src.game.tressette_config import config as tress_config


class BotsMgr:
    async def fake_data_for_bot(self, uid, bet) -> UserInfo:
        min_bet_multiplier = tress_config.get("bet_multiplier_min")
        if bet > 0:
            gold = random.randrange((2 * min_bet_multiplier) * bet, (3 * min_bet_multiplier) * bet)
        else:
            gold = random.randrange(500, 1000)
        avatar_id = random.choice(AVATAR_IDS)
        user = UserInfo(uid, "bot", gold, 1, str(avatar_id), "", True, 0)
        return user
        