import asyncio
from fastapi import WebSocket, WebSocketDisconnect
from src.game.game_client import game_client
from src.base.network.packets import packet_pb2
from src.game.cmds import CMDs

MAX_RETRY_PINGS = 3
CMD_PING_PONG = 0
PING_INTERVAL = 10  # Interval between pings

class ConnectionManager:
    def __init__(self):
        self.active_connections: set[WebSocket] = set()
        self.ping_tasks: dict[WebSocket, asyncio.Task] = {}
        self.ping_responses: dict[WebSocket, int] = {}  # Track pongs received per connection

    async def handle_new_connection(self, websocket: WebSocket):
        """Handles a new WebSocket connection."""
        await self.connect(websocket)
        try:
            while websocket in self.active_connections:
                raw_data = await websocket.receive_bytes()
                await self.handle_received_packet(websocket, raw_data)
        except WebSocketDisconnect:
            await self.disconnect(websocket)
            print(f"WebSocket disconnected: {websocket}")
        except Exception as e:
            print(f"Error: {e}")
            await self.disconnect(websocket)

    async def ping_client(self, websocket: WebSocket):
        """Sends a ping message and waits for pong responses."""
        self.ping_responses[websocket] = 0  # Reset pong counter
        num_pings = 0

        while websocket in self.active_connections:
            try:
                await self._send_ping_packet(websocket)
                num_pings += 1
                await asyncio.sleep(PING_INTERVAL)

                if self.ping_responses[websocket] == 0:
                    if num_pings >= MAX_RETRY_PINGS:
                        print(f"Max retries for ping reached. Disconnecting WebSocket: {websocket}.")
                        await self.disconnect(websocket)
                        break
                else:
                    self.ping_responses[websocket] = 0  # Reset pong counter after receiving pong
            except WebSocketDisconnect:
                print(f"WebSocket closed during ping: {websocket}")
                break
            except Exception as e:
                print(f"Error during ping: {e}. Retrying...")
                await asyncio.sleep(1)

    async def _send_ping_packet(self, websocket: WebSocket):
        """Sends a ping packet."""
        ping = packet_pb2.PingPong()  # Empty message
        payload_ping = ping.SerializeToString()
        await self.send_packet(websocket, CMD_PING_PONG, payload_ping)

    async def connect(self, websocket: WebSocket):
        """Handles accepting and adding a new connection."""
        await websocket.accept()
        self.active_connections.add(websocket)
        ping_task = asyncio.create_task(self.ping_client(websocket))
        self.ping_tasks[websocket] = ping_task  # Track the ping task

    async def disconnect(self, websocket: WebSocket):
        """Disconnects and cleans up resources for a WebSocket."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        if websocket in self.ping_tasks:
            self.ping_tasks[websocket].cancel()  # Cancel the ping task
            del self.ping_tasks[websocket]
        if websocket in self.ping_responses:
            del self.ping_responses[websocket]  # Remove pong tracking

        print(f"WebSocket disconnected: {websocket}")

    async def send_personal_message(self, message: str, websocket: WebSocket):
        """Sends a personal message to a WebSocket."""
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        """Broadcasts a message to all active connections."""
        for connection in self.active_connections:
            await connection.send_text(message)

    async def send_packet(self, websocket: WebSocket, cmd_id: int, payload: bytes):
        """Sends a serialized packet to the WebSocket."""
        print(f"Sending packet: cmd_id={cmd_id}")
        
        packet = packet_pb2.Packet(cmd_id=cmd_id, payload=payload)
        serialized_packet = packet.SerializeToString()

        # Send the serialized packet
        await websocket.send_bytes(serialized_packet)
        print(f"Packet successfully sent: cmd_id={cmd_id}")

    async def handle_received_packet(self, websocket: WebSocket, raw_data: bytes):
        """Handles incoming packets and responds accordingly."""
        try:
            packet = packet_pb2.Packet()
            packet.ParseFromString(raw_data)
            cmd_id = packet.cmd_id
            payload = packet.payload
            print(f"Packet received: cmd_id={cmd_id}")

            if cmd_id == CMD_PING_PONG:
                self.ping_responses[websocket] += 1  # Increment pong counter
            else:
                await game_client.on_receive_packet(cmd_id, payload)

                chat_message = packet_pb2.Login()
                chat_message.abc = 100.1
                chat_message.username = "test"
                chat_message.uid = 222
                chat_message.active = True

                p = chat_message.SerializeToString()
                await self.send_packet(websocket, CMDs.TEST_MESSAGE, p)  # Echo the message back to the client
                pass
        except Exception as e:
            print(f"Failed to parse packet: {e}")

# Instantiate the ConnectionManager for usage
connection_manager = ConnectionManager()
