
class GameVars:
    def __init__(self):
        self.game_client = None
        self.game_mgr = None
        self.match_mgr = None
        self.ingame_chat_mgr = None
        self.guest_mgr = None
        self.login_mgr = None
        self.user_info_mgr = None
        self.friend_mgr = None
        self.bots_mgr = None
        self.logs_mgr = None
        self.game_live_performance = None
        self.customer_service_mgr = None
        self.debt_mgr = None
        self.sette_mezzo_mgr = None
        self.mission_mgr = None
        self.ranking_mgr = None

    def get_game_client(self):
        if self.game_client is None:
            from src.game.game_client import GameClient
            self.game_client = GameClient()
        return self.game_client
    
    def get_game_mgr(self):
        if self.game_mgr is None:
            from src.game.game_mgr import GameMgr
            self.game_mgr = GameMgr()
        return self.game_mgr
    
    def get_match_mgr(self):
        if self.match_mgr is None:
            from src.game.match_mgr import MatchManager
            self.match_mgr = MatchManager()
            self.match_mgr.start()

        return self.match_mgr
    
    def get_ingame_chat_mgr(self):
        if self.ingame_chat_mgr is None:
            from src.game.ingame_chat_mgr import InGameChatMgr
            self.ingame_chat_mgr = InGameChatMgr()
        return self.ingame_chat_mgr
    
    def get_guest_mgr(self):
        if self.guest_mgr is None:
            from src.base.login.guest_mgr import GuestMgr
            self.guest_mgr = GuestMgr()
        return self.guest_mgr
    
    def get_login_mgr(self):
        if self.login_mgr is None:
            from src.base.login.login_mgr import LoginMgr
            self.login_mgr = LoginMgr()
        return self.login_mgr
    
    def get_friend_mgr(self):
        if self.friend_mgr is None:
            from src.game.friend_mgr import FriendMgr
            self.friend_mgr = FriendMgr()
        return self.friend_mgr
    
    def get_bots_mgr(self):
        if self.bots_mgr is None:
            from src.game.bots_mgr import BotsMgr
            self.bots_mgr = BotsMgr()
        return self.bots_mgr
    
    def get_game_live_performance(self):
        if self.game_live_performance is None:
            from src.game.game_live_performance import GameLivePerformance
            self.game_live_performance = GameLivePerformance()
        return self.game_live_performance
    
    def get_customer_service_mgr(self):
        if self.customer_service_mgr is None:
            from src.game.modules.customer_service import CustomerServiceMgr
            self.customer_service_mgr = CustomerServiceMgr()
        return self.customer_service_mgr
    
    def get_debt_mgr(self):
        if self.debt_mgr is None:
            from src.game.debt_mgr import DebtMgr
            self.debt_mgr = DebtMgr()
        return self.debt_mgr
    
    def get_sette_mezzo_mgr(self):
        if self.sette_mezzo_mgr is None:
            from src.game.modules.sette_mezzo.sette_mezzo_mgr import SetteMezzoMgr
            self.sette_mezzo_mgr = SetteMezzoMgr()
        return self.sette_mezzo_mgr
    
    def get_mission_mgr(self):
        if self.mission_mgr is None:
            from src.game.modules.mission.mission_mgr import MissionMgr
            self.mission_mgr = MissionMgr()
        return self.mission_mgr
    
    def get_ranking_mgr(self):
        if self.ranking_mgr is None:
            from src.game.modules.ranking.ranking_mgr import RankingMgr
            self.ranking_mgr = RankingMgr()
        return self.ranking_mgr
    
    # this function is called when the server starts
    async def init_game_vars(self):
        await self.get_ranking_mgr().init_season()
        
    
game_vars = GameVars()
