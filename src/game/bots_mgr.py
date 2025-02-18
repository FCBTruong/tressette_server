

from src.game.models import UserInfo


class BotsMgr:
    
    async def get_a_bot(self) -> UserInfo:
        user = UserInfo(2000000, "bot", 1000000, 1, "default_avatar", "", True, 0)
        return user
        