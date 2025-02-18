import asyncio
import logging
import random
import time
import traceback
from fastapi import WebSocket, WebSocketDisconnect
from fastapi.websockets import WebSocketState
from src.base.security.jwt import create_session_token, verify_token
from src.constants import *
from src.game.users_info_mgr import users_info_mgr
from src.game.game_vars import game_vars
from src.base.network.packets import packet_pb2
from src.game.cmds import CMDs

logging.basicConfig(
    level=logging.INFO,  # Set logging level
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",  # Log format
)
logger = logging.getLogger("connection_manager")  # Name your logger
MAX_RETRY_PINGS = 10 # After 10 * 10 seconds = 1 minute, 30 secs, disconnect the WebSocket

CMD_PING_PONG = 0
CMD_LOGIN = 1
CMD_CREATE_GUEST_ACCOUNT = 2
CMD_LOGIN_FIREBASE = 3
PING_INTERVAL = 10  # Interval between pings


class ConnectionManager:
    def __init__(self):
        self.active_connections: set[WebSocket] = set()
        self.ping_tasks: dict[WebSocket, asyncio.Task] = {}
        self.ping_responses: dict[WebSocket, int] = {}  # Track pongs received per connection
        self.user_websockets: dict[int, WebSocket] = {}  # Track user IDs to WebSockets
        self.guest_create_times: dict[WebSocket, int] = {} # timestamp of guest account creation, to prevent spam

    async def handle_new_connection(self, websocket: WebSocket):
        """Handles a new WebSocket connection."""
        await self.connect(websocket)
        try:
            while websocket in self.active_connections:
                raw_data = await websocket.receive_bytes()
                asyncio.create_task(self.handle_received_packet(websocket, raw_data))
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
        user_id = None
        for uid, ws in self.user_websockets.items():
            if ws == websocket:
                user_id = uid
                del self.user_websockets[uid]
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
        logger.info(f"Sending packet: cmd_id={cmd_id}")
        
        packet = packet_pb2.Packet(cmd_id=cmd_id, payload=payload)
        serialized_packet = packet.SerializeToString()

        # Send the serialized packet
        await websocket.send_bytes(serialized_packet)
        print(f"Packet successfully sent: cmd_id={cmd_id}")

    def _authenticate_user(self):
        return True

    async def handle_received_packet(self, websocket: WebSocket, raw_data: bytes):
        """Handles incoming packets and responds accordingly."""
        try:
            packet = packet_pb2.Packet()
            packet.ParseFromString(raw_data)
            cmd_id = packet.cmd_id
            payload = packet.payload
            token = packet.token
            logger.info(f"Packet received: cmd_id={cmd_id}")

            if cmd_id == CMD_PING_PONG:
                if websocket not in self.ping_responses:
                    print(f"Received pong from untracked WebSocket: {websocket}")
                    return
                self.ping_responses[websocket] += 1  # Increment pong counter
            elif cmd_id == CMD_CREATE_GUEST_ACCOUNT:
                if websocket in self.guest_create_times:
                    last_create_time = self.guest_create_times[websocket]
                    if last_create_time + 300 > int(time.time()): # 5 minutes
                        print(f"Guest account creation too fast. Disconnecting WebSocket: {websocket}")
                        return
                self.guest_create_times[websocket] = int(time.time())
                guest_id = await game_vars.get_guest_mgr().create_guest_account()
                guest_account = packet_pb2.GuestAccount()
                guest_account.guest_id = guest_id
                p = guest_account.SerializeToString()
                await self.send_packet(websocket, CMD_CREATE_GUEST_ACCOUNT, p)
            elif cmd_id == CMD_LOGIN_FIREBASE:
                await self._handle_login_firebase(websocket, payload)   
            elif cmd_id == CMD_LOGIN:
                login_client_pkg = packet_pb2.Login()
                login_client_pkg.ParseFromString(payload)
                token = login_client_pkg.token
                login_type = login_client_pkg.type
                print(f"Login packet received: token={token}, login_type={login_type}")
                login_response = packet_pb2.LoginResponse()

                # authenticate user
                uid = await game_vars.get_login_mgr().authenticate_user(login_type, token)

                if uid == -1:
                    logger.info("Unauthorized")
                    login_response.error = LOGIN_ERROR_UNAUTHORIZED
                    p = login_response.SerializeToString()
                    await self.send_packet(websocket, CMD_LOGIN, p)
                    return
                logger.info(f"Login packet received: uid={uid}")

                user_cred = {
                    "uid": uid,
                    "active": True
                }

                user = await users_info_mgr.get_user_info(uid)
                if not user or not user.is_active:
                    logger.info("User inactive") # removed, or banned, disabled
                    return
                # Check if user is already logged in, if so, disconnect the old connection
                old_websocket = self.user_websockets.get(uid)
                if old_websocket:
                    print(f"User with ID {uid} is already logged in. Disconnecting old connection.")
                
                    if old_websocket.application_state == WebSocketState.CONNECTED:
                        await old_websocket.close()

                logger.info('create access token')
                new_token = create_session_token(user_cred)
                login_response.token = new_token
                login_response.uid = uid
                login_response.error = LOGIN_ERROR_SUCCESS

                p = login_response.SerializeToString()

                self.user_websockets[uid] = websocket
                await self.send_packet(websocket, CMD_LOGIN, p)
                await game_vars.get_game_client().user_login_success(uid=uid)
            else:
                if not token:
                    logger.info("Unauthorized")
                    return

                user = verify_token(token)
                if not user:
                    logger.info("Unauthorized")
                    return
                
                # Prevent user play game from multiple devices
                if self.user_websockets.get(user.get("uid")) != websocket:
                    print("Not allow user play game from multiple devices")
                    return
                print(f"User: {user}")
                uid = user.get("uid")
                
                await game_vars.get_game_client().on_receive_packet(uid=uid, cmd_id=cmd_id, payload=payload)
        except Exception as e:
            logger.info(f"Failed to parse packet: {e}")
            traceback.print_exc()
        finally:
            return

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

    async def user_logout(self, uid: int):
        # remove from user_websockets
        if uid in self.user_websockets:
            del self.user_websockets[uid]

    def check_user_active_online(self, uid: int):
        is_active = False
        if uid in self.user_websockets:
            ws = self.user_websockets[uid]
            if ws in self.active_connections:
                is_active = True
        return is_active
    
    def get_random_user_online(self, size: int) -> list[int]:
        users = list(self.user_websockets.keys())
        if len(users) <= size:
            return users
        return random.sample(users, size)  # Randomly select `size` users
            
    async def _handle_login_firebase(self, websocket, payload):
        login_firebase_pkg = packet_pb2.LoginFirebase()
        login_firebase_pkg.ParseFromString(payload)
        token = login_firebase_pkg.login_token

        sub_type = login_firebase_pkg.sub_type
        if sub_type != 0:
            if sub_type == 1:  # Google
                # Firebase Auth not working for iOS, so need to login through server
                google_login_inf = await game_vars.get_login_mgr().login_by_google_token(token)
                if not google_login_inf['success']:
                    print("Unauthorized Google")
                    return
                token = google_login_inf['firebase_token']
            elif sub_type == 2:  # Facebook
                pass
            elif sub_type == 3: # Apple
                apple_login_inf = await game_vars.get_login_mgr().login_by_apple_token(token)
                if not apple_login_inf['success']:
                    print("Unauthorized Apple")
                    return
                token = apple_login_inf['firebase_token']


        game_token = await game_vars.get_login_mgr().login_firebase(token)
        if not game_token:
            print("Unauthorized")
            return
        login_response = packet_pb2.LoginFirebase()
        login_response.login_token = str(game_token)
        p = login_response.SerializeToString()
        await self.send_packet(websocket, CMD_LOGIN_FIREBASE, p)   

# Instantiate the ConnectionManager for usage
connection_manager = ConnectionManager()
