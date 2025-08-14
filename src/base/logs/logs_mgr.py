import io, gzip, uuid, json, time, threading, atexit
from datetime import datetime, timezone
import boto3
from src.config.settings import settings
from botocore.exceptions import ClientError

AWS_REGION   = settings.AWS_REGION
S3_BUCKET    = settings.S3_BUCKET
APP          = settings.APP_NAME
SHARD_ID     = settings.SHARD_ID
FLUSH_SEC    = settings.TIME_SEND_LOGS
BUFFER_LIMIT = settings.BUFFER_LIMIT
ENV          = settings.ENVIRONMENT.value  # e.g. "prod" / "staging" / "dev"
RETRY        = 3

s3 = boto3.client("s3", region_name=AWS_REGION)

_log_buf = []
_lock = threading.Lock()
_stop = threading.Event()

def _utcnow():
    return datetime.now(timezone.utc)

def _s3_key_prefix(now):
    return f"logs/app={APP}/dt={now:%Y-%m-%d}/hour={now:%H}/shard={SHARD_ID}"

def _s3_key(now):
    return f"{_s3_key_prefix(now)}/logs-{uuid.uuid4().hex}.jsonl.gz"

def _put_object(key: str, body: bytes, *, content_type: str, content_encoding: str | None = None):
    kwargs = dict(
        Bucket=S3_BUCKET,
        Key=key,
        Body=body,
        ContentType=content_type,
        Metadata={"app": APP, "shard": SHARD_ID, "env": ENV},
    )
    if content_encoding:
        kwargs["ContentEncoding"] = content_encoding
    # If your bucket enforces SSE, uncomment:
    # kwargs["ServerSideEncryption"] = "AES256"  # or "aws:kms" + SSEKMSKeyId
    s3.put_object(**kwargs)

def _flush_to_s3(events):
    if not events:
        return
    now = _utcnow()
    key = _s3_key(now)

    bio = io.BytesIO()
    with gzip.GzipFile(fileobj=bio, mode="wb", compresslevel=6) as gz:
        for ev in events:
            gz.write((json.dumps(ev, separators=(",", ":")) + "\n").encode("utf-8"))
    bio.seek(0)

    _put_object(key, bio.getvalue(), content_type="application/json", content_encoding="gzip")
    print(f"Flushed {len(events)} events to S3 at {key}")

def _write_dead(batch):
    now = _utcnow()
    dead_key = f"dead/{now:%Y%m%dT%H%M%S}-{uuid.uuid4().hex}.txt"
    payload = ("\n".join(json.dumps(ev, separators=(",", ":")) for ev in batch)).encode("utf-8")
    _put_object(dead_key, payload, content_type="text/plain")
    print(f"Wrote dead letter {len(batch)} events to S3 at {dead_key}")

def _flush_once():
    if settings.ENABLE_CHEAT:
        print("Cheat mode enabled, skipping flush.")
        return
    with _lock:
        if not _log_buf:
            return
        batch = _log_buf[:]
        _log_buf.clear()

    for i in range(RETRY):
        try:
            _flush_to_s3(batch)
            return
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code")
            print(f"Error flushing logs to S3 ({i+1}/{RETRY}): {code} {e}")
        except Exception as e:
            print(f"Error flushing logs to S3 ({i+1}/{RETRY}): {repr(e)}")
        time.sleep(2 ** i)

    # All retries failed -> write dead
    try:
        _write_dead(batch)
    except Exception as e2:
        print(f"Failed to write dead letter: {repr(e2)}")

def _flush_loop():
    last = time.time()
    print("AAA flush loop started")
    while not _stop.is_set():
        time.sleep(0.5)
        if time.time() - last >= FLUSH_SEC:
            last = time.time()
            _flush_once()

def _graceful_shutdown():
    _stop.set()
    try:
        _bg.join(timeout=5)
    except Exception as e:
        print(f"Error during graceful shutdown: {e}")
    _flush_once()

def write_log(uid, action, sub_action, extras):
    entry = {
        "log_time": datetime.now().isoformat(),
        "uid": uid,
        "action": action,
        "sub_action": sub_action,
        "extras": [str(e) for e in extras] if extras else []
    }
    with _lock:
        _log_buf.append(entry)
        need_flush = (len(_log_buf) >= BUFFER_LIMIT)
    if need_flush:
        _flush_once()

def send_logs():
    _flush_once()

print(f"Logs manager started with buffer limit {BUFFER_LIMIT} and flush interval {FLUSH_SEC} seconds.")
_bg = threading.Thread(target=_flush_loop, daemon=True)
_bg.start()
atexit.register(_graceful_shutdown)

if settings.ENABLE_CHEAT:
    # write test
    write_log("test_user", "test_action", "test_sub_action", ["test_extra1", "test_extra2"])
    write_log("test_user2", "test_action2", "test_sub_action2", ["test_extra3"])
