from asyncio.log import logger
from datetime import datetime
import os
from typing import Optional
from dotenv import load_dotenv
from pydantic_settings import BaseSettings
from enum import Enum

# Load environment variables from .env file
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))

class EnvironmentOption(Enum):
    LOCAL = "local"
    STAGING = "staging"
    PRODUCTION = "production"

class EnvironmentSettings(BaseSettings):
    ENVIRONMENT: EnvironmentOption = os.getenv("ENVIRONMENT", default="local")

class DatabaseSettings(BaseSettings):
    pass

class PostgresSettings(DatabaseSettings):
    POSTGRES_USER: Optional[str] = os.getenv("POSTGRES_USER")
    POSTGRES_PASSWORD: Optional[str] = os.getenv("POSTGRES_PASSWORD")
    POSTGRES_SERVER: Optional[str] = os.getenv("POSTGRES_SERVER")
    POSTGRES_PORT: Optional[str] = os.getenv("POSTGRES_PORT")
    POSTGRES_DB: Optional[str] = os.getenv("POSTGRES_DB")

    # PsqlORM settings
    POSTGRES_POOL_SIZE: Optional[int] = os.getenv("POSTGRES_POOL_SIZE", 50)
    POSTGRES_MAX_OVERFLOW: Optional[int] = os.getenv("POSTGRES_MAX_OVERFLOW", 20)
    POSTGRES_POOL_TIMEOUT: Optional[int] = os.getenv("POSTGRES_POOL_TIMEOUT", 30)
    POSTGRES_POOL_RECYCLE: Optional[int] = os.getenv("POSTGRES_POOL_RECYCLE", 3600)

class RedisSettings(DatabaseSettings):
    REDIS_HOST: Optional[str] = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: Optional[str] = os.getenv("REDIS_PORT", "6379")
    REDIS_TTL: Optional[int] = os.getenv("REDIS_TTL", 3600)

class CommonSettings(BaseSettings):
    ENABLE_CHEAT: Optional[bool] = os.getenv("ENABLE_CHEAT") == "true"
    DEV_MODE: Optional[bool] = os.getenv("DEV_MODE") == "true"
    LOGS_URL: Optional[str] = os.getenv("LOGS_URL")
    
class Settings(
    EnvironmentSettings,
    PostgresSettings,
    RedisSettings,
    CommonSettings,
):
    pass

settings = Settings()

# Get the current local time with time zone info
current_time = datetime.now().astimezone()

# Print the current time zone name
print(f"Current Time Zone: {current_time.tzname()}")
print('configlog: ', settings)