
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
    
game_vars = GameVars()
