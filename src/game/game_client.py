from src.game.cmds import CMDs
from src.base.network.packets.packet_pb2 import ChatMessage  # Import ChatMessage from the protobuf module

class GameClient:
    def __init__(self):
        pass

    async def on_receive_packet(self, cmd_id, payload):
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

            case _:
                print(f"Unknown command ID: {cmd_id}")

    async def send_packet(self, user_id, cmd_id, payload):
        pass

# Instantiate the PacketProcessor
game_client = GameClient()
