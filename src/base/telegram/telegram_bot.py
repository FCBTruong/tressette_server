import aiohttp
import logging
from src.config.settings import settings

# Hardcoded bot token and chat ID
BOT_TOKEN = settings.TELEGRAM_BOT_TOKEN
CHAT_ID = "995915268"
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"


async def send_message(message: str):
    try:
        payload = {
            'chat_id': CHAT_ID,
            'text': message,
            'parse_mode': 'Markdown'
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(API_URL, data=payload) as response:
                response_text = await response.text()
                if response.status == 200:
                    logging.info("Message sent to Telegram successfully")
                else:
                    logging.error(f"Failed to send message: {response.status} - {response_text}")
    except Exception as e:
        logging.error(f"Unexpected error while sending message: {e}")


