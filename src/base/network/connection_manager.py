import asyncio
import traceback
from fastapi import WebSocket, WebSocketDisconnect
from fastapi.websockets import WebSocketState
from src.base.security.jwt import create_access_token, verify_token
from src.game.game_vars import game_vars
from src.base.network.packets import packet_pb2
from src.game.cmds import CMDs

MAX_RETRY_PINGS = 3

CMD_PING_PONG = 0
CMD_LOGIN = 1
PING_INTERVAL = 10  # Interval between pings

class ConnectionManager:
    def __init__(self):
        self.active_connections: set[WebSocket] = set()
        self.ping_tasks: dict[WebSocket, asyncio.Task] = {}
        self.ping_responses: dict[WebSocket, int] = {}  # Track pongs received per connection
        self.user_websockets: dict[int, WebSocket] = {}  # Track user IDs to WebSockets

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

        # find user id
        for user_id, ws in self.user_websockets.items():
            if ws == websocket:
                del self.user_websockets[user_id]
                break
        if user_id:
            await game_vars.get_game_mgr().on_user_disconnect(user_id)

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
            token = packet.token
            print(f"Packet received: cmd_id={cmd_id}")

            if cmd_id == CMD_PING_PONG:
                self.ping_responses[websocket] += 1  # Increment pong counter
            elif cmd_id == CMD_LOGIN:
                login_client_pkg = packet_pb2.Login()
                login_client_pkg.ParseFromString(payload)
                uid = login_client_pkg.uid
                print(f"Login packet received: uid={uid}")

                user_info = {
                    "uid": uid,
                    "active": True
                }

                # Check if user is already logged in, if so, disconnect the old connection
                old_websocket = self.user_websockets.get(uid)
                if old_websocket:
                    print(f"User with ID {uid} is already logged in. Disconnecting old connection.")
                
                    if old_websocket.application_state == WebSocketState.CONNECTED:
                        await   old_websocket.close()

                new_token = create_access_token(user_info)
                print(f"New token: {new_token}")
                login_response = packet_pb2.LoginResponse()
                login_response.token = new_token
                login_response.uid = uid

                p = login_response.SerializeToString()

                self.user_websockets[uid] = websocket
                await self.send_packet(websocket, CMD_LOGIN, p)
                await game_vars.get_game_client().user_login_success(uid=uid)
            else:
                if not token:
                    print("Unauthorized")
                    return

                user = verify_token(token)
                if not user:
                    print("Unauthorized")
                    return
                print(f"User: {user}")
                uid = user.get("uid")
                
                await game_vars.get_game_client().on_receive_packet(uid=uid, cmd_id=cmd_id, payload=payload)
                pass
        except Exception as e:
            print(f"Failed to parse packet: {e}")
            traceback.print_exc()

    async def send_packet_to_user(self, uid: int, cmd_id: int, payload: bytes):
        websocket_ref = self.user_websockets.get(uid)
        if websocket_ref:
            # check active, other wise remove from user_websockets
            if websocket_ref not in self.active_connections:
                print(f"User with ID {uid} has no active WebSocket connection")
                del self.user_websockets[uid]
                return
            await self.send_packet(websocket_ref, cmd_id, payload)
        else:
            print(f"User with ID {uid} not has no active WebSocket connection")
        pass

# Instantiate the ConnectionManager for usage
connection_manager = ConnectionManager()
