

import random
from src.constants import AVATAR_IDS
from src.game.models import UserInfo


class BotsMgr:
    async def fake_data_for_bot(self, uid, bet) -> UserInfo:
        gold = random.randrange(5 * bet, 10 * bet)
        avatar_id = random.choice(AVATAR_IDS)
        user = UserInfo(uid, "bot", gold, 1, str(avatar_id), "", True, 0)
        return user
        