from src.game.cmds import CMDs
from src.base.network.packets.packet_pb2 import ChatMessage  # Import ChatMessage from the protobuf module

class GameClient:
    def __init__(self):
        pass

    async def on_receive_packet(self, uid, cmd_id, payload):
        match cmd_id:
            case CMDs.TEST_MESSAGE:
                print("Received TEST_MESSAGE packet")
                
                # Deserialize payload into a ChatMessage object
                chat_message = ChatMessage()
                try:
                    chat_message.ParseFromString(payload)
                    print(f"Message from {chat_message}")
                except Exception as e:
                    print(f"Failed to parse ChatMessage: {e}")
            
            case CMDs.LOGOUT:
                print("Received LOGOUT packet")
            
            case CMDs.QUICK_PLAY:
                print("Received QUICK_PLAY packet")
                await self.send_packet(uid, CMDs.GAME_INFO, b"Game info!")
            case _:
                print(f"Unknown command ID: {cmd_id}")

    async def user_login_success(self, uid):
        from src.base.network.connection_manager import connection_manager
        print(f"User with ID {uid} has successfully logged in")
        await self.send_packet(uid, CMDs.GENERAL_INFO, b"Welcome to the server!")
    
    async def send_packet(self, uid, cmd_id, payload):
        from src.base.network.connection_manager import connection_manager
        await connection_manager.send_packet_to_user(uid=uid, cmd_id=cmd_id, payload=payload)
        pass

# Instantiate the PacketProcessor
game_client = GameClient()
