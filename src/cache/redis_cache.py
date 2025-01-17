import logging
import sys
import redis
from src.config.settings import settings

logging.basicConfig(
    level=logging.INFO,  # Set logging level
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",  # Log format
)
logger = logging.getLogger("redis_cache")  # Name your logger

# Initialize Redis connection
redis_client = redis.StrictRedis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, db=0, decode_responses=True)


# try:
#     redis_client = redis.StrictRedis(
#         host='tressette-redis-valkey-dev-kgdynn.serverless.apse1.cache.amazonaws.com',
#         port=6379,
#         db=0,
#         decode_responses=True
#     )
#     redis_client.ping()  # Test the connection
#     logger.info("Connected to Valkey!")
# except redis.ConnectionError as e:
#     logger.error(f"Failed to connect to Valkey: {e}")
#     sys.exit(1)  # Exit with an error code
# except Exception as e:
#     logger.error(f"Unexpected error: {e}")
#     sys.exit(1)  # Exit with an error code

def get_from_cache(key: str):
    try:
        """Retrieve data from Redis cache"""
        return redis_client.get(key)
    except Exception as e:
        logger.info('crashhh', e)

def set_to_cache(key: str, value: str, ttl: int = settings.REDIS_TTL):
    """Set data to Redis cache with optional TTL (time-to-live)"""
    redis_client.setex(key, ttl, value)

def clear_cache():
    """Clear all data from Redis cache"""
    redis_client.flushall()