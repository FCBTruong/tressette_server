from src.base.network.connection_manager import connection_manager

class GameLivePerformance:
    async def get_ccu(self):
        return len(connection_manager.user_websockets)
