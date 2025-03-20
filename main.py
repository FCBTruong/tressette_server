
import logging
import traceback
from typing import Optional
from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.responses import HTMLResponse
from src.base.network.connection_manager import connection_manager
from src.base.payment.google_pay import verify_purchase
from src.base.telegram import telegram_bot
from src.config.settings import settings
from src.game.users_info_mgr import users_info_mgr
from src.game.game_vars import game_vars
import src.game.game_client as game_client
from src.base.payment.apple_pay import cheat_test_sandbox
from src.base.payment.paypal_pay import create_paypal_order, handle_paypal_success

logging.basicConfig(
    level=logging.INFO,  # Set logging level
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",  # Log format
)
logger = logging.getLogger("main")  # Name your logger

async def lifespan(app: FastAPI):
    print("Application startup complete.")
    if not settings.ENABLE_CHEAT:
        await telegram_bot.send_message(f"Server started")
    yield
if settings.ENABLE_SWAGGER:
    app = FastAPI(lifespan=lifespan)
else:
    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


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

@app.get('/health')
async def health():
    return 'ok'

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    print(f"New WebSocket connection from Client")
    await connection_manager.handle_new_connection(websocket)

@app.get("/commands/{password}/{cmd}")
async def get_data_cmds(password, cmd, data: Optional[str] = None):
    try:
        if password != "tzPuys0cPIHKfgA":
            return "Invalid password"
        if cmd == 'ccu':
            return await game_vars.get_game_live_performance().get_ccu()
        if cmd == 'cheat_refresh':
            if data is None:
                raise HTTPException(status_code=400, detail="Missing data for cheat command")
            await users_info_mgr.remove_cache_user(int(data))
            return 'cheat ok'
        elif cmd == 'cheat_refresh_all_cache':
            for uid in users_info_mgr.users:
                await users_info_mgr.remove_cache_user(uid)
            return 'cheat ok'
        elif cmd == "cheat_gold":
            if data is None:
                raise HTTPException(status_code=400, detail="Missing data for cheat command")
            uid, gold = data.split(',')
            user = await users_info_mgr.get_user_info(int(uid))
            if user is None:
                return f"User {uid} not found"
            user.add_gold(int(gold))
            await user.commit_gold()
            await user.send_update_money()
            return 'cheat ok'
        elif cmd == 'broadcast':
            if data is None:
                raise HTTPException(status_code=400, detail="Missing data for broadcast command")
            await connection_manager.admin_broadcast(data)
            return 'broadcast ok'
        elif cmd == 'enable_sandbox':
            if data is None:
                raise HTTPException(status_code=400, detail="Missing data for enable_sandbox command")
            cheat_test_sandbox(data)
            return 'enable_sandbox ok'
        elif cmd == "test_curl":
            # curl link and return response
            import requests
            response = requests.get(data)
            return response.text
        elif cmd == "send_logs":
            from src.base.logs.logs_mgr import send_logs
            send_logs()
        return "hello"
    except Exception as e:
        traceback.print_exc()
        return str(e)

@app.post("/payment/paypal-webhook")
async def on_paypal_webhook(request):
    pass
    # return await paypal_webhook(request)

@app.get('/paypal/success')
async def success(token: str, PayerID: str):
    await handle_paypal_success(token, PayerID)
    return HTMLResponse(html_payment_success)

@app.get('/paypal/cancel')
async def success(token: str, PayerID: str):
    print("Paypal cancel")


html_payment_success = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Payment Successful</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            text-align: center;
            padding: 50px;
            background-color: #f4f4f4;
        }
        .container {
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
            display: inline-block;
        }
        h1 {
            color: #4CAF50;
        }
        p {
            font-size: 18px;
            color: #333;
        }
        .btn {
            display: inline-block;
            margin-top: 20px;
            padding: 10px 20px;
            background: #008CBA;
            color: white;
            text-decoration: none;
            border-radius: 5px;
            font-size: 16px;
        }
        .btn:hover {
            background: #005f73;
        }
    </style>
</head>
<body>

    <div class="container">
        <h1>Payment Successful!</h1>
        <p>Thank you for your payment. You can now return to the game.</p>
        <a href="https://tressette.clareentertainment.com" class="btn">Back to Game</a>
    </div>

</body>
</html>
"""