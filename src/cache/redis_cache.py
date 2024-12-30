import redis
import os
from src.config.settings import settings

# Initialize Redis connection
redis_client = redis.StrictRedis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, db=0, decode_responses=True)

def get_from_cache(key: str):
    """Retrieve data from Redis cache"""
    return redis_client.get(key)

def set_to_cache(key: str, value: str, ttl: int = settings.REDIS_TTL):
    """Set data to Redis cache with optional TTL (time-to-live)"""
    redis_client.setex(key, ttl, value)

def clear_cache():
    """Clear all data from Redis cache"""
    redis_client.flushall()