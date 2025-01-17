import logging
import sys
import redis
from src.config.settings import settings

logging.basicConfig(
    level=logging.INFO,  # Set logging level
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",  # Log format
)
logger = logging.getLogger("redis_cache")  # Name your logger

class RedisCache:
    engine = None
    @classmethod
    def get(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        RedisCache.lazy_initialize_pg_connection()

    @staticmethod
    def lazy_initialize_pg_connection():
        if RedisCache.engine is None:
            RedisCache.engine = redis.StrictRedis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=0,
                decode_responses=True
            )
                
    @staticmethod
    async def with_session() -> AsyncGenerator[AsyncSession, None]:
        async with RedisCache.async_session() as db:
            yield db 

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