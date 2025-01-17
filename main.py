
import logging
from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse
from src.base.network.connection_manager import connection_manager
import src.game.game_client as game_client


logging.basicConfig(
    level=logging.INFO,  # Set logging level
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",  # Log format
)
logger = logging.getLogger("main")  # Name your logger

async def lifespan(app: FastAPI):
    print("Application startup complete.")
    yield

app = FastAPI(lifespan=lifespan)

html = """
<!DOCTYPE html>
<html>
    <head>
        <title>Chat</title>
    </head>
    <body>
        <h1>WebSocket Chat</h1>
        <h2>Your ID: <span id='ws-id'></span></h2>
        <form action="" onsubmit="sendMessage(event)">
            <input type="text" id="messageText" autocomplete="off"/>
            <button>Send</button>
        </form>
        <ul id='messages'>
        </ul>
        <script>
            var client_id = Math.floor(Math.random() * 1000);  // Generate a random client ID
            document.getElementById('ws-id').textContent = client_id;
            var ws = new WebSocket("ws://localhost:8000/ws/" + client_id);
            ws.onmessage = function(event) {
                var messages = document.getElementById('messages')
                var message = document.createElement('li')
                var content = document.createTextNode(event.data)
                message.appendChild(content)
                messages.appendChild(message)
            };
            function sendMessage(event) {
                var input = document.getElementById("messageText")
                ws.send(input.value)
                input.value = ''
                event.preventDefault()
            }
        </script>
    </body>
</html>
"""


@app.get("/")
async def get():
    return HTMLResponse(html)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    print(f"New WebSocket connection from Client")
    await connection_manager.handle_new_connection(websocket)

@app.get("/commands/{password}/{cmd}")
async def get_data_cmds(password, cmd):
    try:
        if password != "tzPuys0cPIHKfgA":
            return "Invalid password"
        if cmd == 'ccu':
            return len(connection_manager.active_connections)
        
        return "hello"
    except Exception as e:
        return str(e)
