

import random
from src.constants import AVATAR_IDS, LOGIN_GOOGLE, LOGIN_GUEST
from src.game.models import UserInfo
from src.game.tressette_config import config as tress_config


class BotsMgr:
    start_uid = 10000000
    bots = {}  # uid -> UserInfo
    def fake_data_for_bot(self, uid, bet) -> UserInfo:
        min_bet_multiplier = tress_config.get("bet_multiplier_min")
        if bet > 0:
            gold = random.randrange((2 * min_bet_multiplier) * bet, (3 * min_bet_multiplier) * bet)
        else:
            gold = random.randrange(500, 1000)
        avatar_id = random.choice(AVATAR_IDS)
        name = generate_italian_name()
        user = UserInfo(uid, name, gold, 1, str(avatar_id), "", True, 0)
        user.is_active = True

        user.game_count = random.randint(0, 100)
        user.win_count = random.randint(0, user.game_count)
        user.exp = random.randint(0, 1000)
        user.login_type = random.choice([LOGIN_GUEST, LOGIN_GOOGLE])

        self.bots[uid] = user
        return user
        
    def get_free_bot_uid(self):
        bot_uid = self.start_uid
        self.start_uid += 1
        return bot_uid
    
    def destroy_bot(self, bot_uid):
        if bot_uid in self.bots:
            del self.bots[bot_uid]
        return True
    
    def get_bot(self, uid):
        if uid in self.bots:
            return self.bots[uid]
        return None
    
    import random

first_names = [
    "Giuseppe", "Marco", "Antonio", "Francesco", "Giovanni", "Luca", "Alessandro", 
    "Matteo", "Davide", "Stefano", "Andrea", "Fabio", "Vincenzo", "Emanuele", "Salvatore"
]

surnames = [
    "Rossi", "Bianchi", "Romano", "Esposito", "Ricci", "Marino", "Greco", "Bruno",
    "Gallo", "Conti", "De Luca", "Moretti", "Rizzo", "De Santis", "Ferrara"
]

def generate_italian_name():
    first = random.choice(first_names)
    last = random.choice(surnames)
    return f"{first} {last}"