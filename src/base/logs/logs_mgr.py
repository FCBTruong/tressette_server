
import threading
import httpx  # Better for async requests
from datetime import datetime
import time

from src.config.settings import settings


log_buffer = []
buffer_limit = 10000  # Max logs before forcing send
log_server_url = settings.LOGS_URL

def write_log(uid, action, sub_action, extras):
    """Append log to buffer and send if limit is reached."""
    print('write log', action, extras)

    global log_buffer
    log_buffer.append({
        "log_time": datetime.now().isoformat(),
        "uid": uid,
        "action": action,
        "sub_action": sub_action,
        "extras": extras
    })

    if len(log_buffer) >= buffer_limit:
        send_logs()

def send_logs():
    """Send logs to the log server."""
    global log_buffer
    if log_buffer:
        try:
            response = httpx.post(log_server_url, json=log_buffer, timeout=10)
            if response.status_code != 200:
                print(f"Failed to send logs, status: {response.status_code}")
        except Exception as e:
            print(f"Error sending logs: {e}")

        log_buffer.clear()

TIME_SEND_LOGS = 60 * 10 # 10 minutes

if settings.DEV_MODE:
    TIME_SEND_LOGS = 1
    
# Background thread for sending logs every 10 minutes
def start_log_sender():
    while True:
        time.sleep(TIME_SEND_LOGS)
        send_logs()

# Start the background thread
threading.Thread(target=start_log_sender, daemon=True).start()
