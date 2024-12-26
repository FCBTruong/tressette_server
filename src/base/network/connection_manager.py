

from fastapi import WebSocket
from src.game.packet_processor import packet_processor
from src.base.network.packets.packet_pb2 import Packet


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    async def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
    
    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

    async def send_packet(self, cmd_id, payload):
        print(f"Sending packet: cmd_id={cmd_id}")
        # Placeholder implementation
        packet = Packet(cmd_id=cmd_id, payload=payload)
        # Serialize and send packet logic here
        print(f"Packet sent: cmd_id={cmd_id}, payload={payload}")

    async def receive_packet(self, raw_data):
        packet = Packet()
        packet.ParseFromString(raw_data)
        cmd_id = packet.cmd_id
        payload = packet.payload
        print(f"Packet received: cmd_id={cmd_id}")
        packet_processor.on_receive_packet(cmd_id, payload)

connection_manager = ConnectionManager()