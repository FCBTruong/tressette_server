import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.schema import CreateTable
from typing import AsyncGenerator
from ..config.settings import settings

logger = logging.getLogger(__name__)


class PsqlOrm(object):
    PSQL_CONNECTION = {
        'dbname': settings.POSTGRES_DB,
        'user': settings.POSTGRES_USER,
        'password': settings.POSTGRES_PASSWORD,
        'host': settings.POSTGRES_SERVER,
        'port': settings.POSTGRES_PORT,
        'pool_size': settings.POSTGRES_POOL_SIZE,
        'max_overflow': settings.POSTGRES_MAX_OVERFLOW,
        'pool_timeout': settings.POSTGRES_POOL_TIMEOUT,
        'pool_recycle': settings.POSTGRES_POOL_RECYCLE,
    }
    print(PSQL_CONNECTION)
    engine = None
    async_session = None
    current_connection_type = None
    _instance = None

    @classmethod
    def get(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        PsqlOrm.lazy_initialize_pg_connection()

    @staticmethod
    def lazy_initialize_pg_connection():
        pg_conn_params = PsqlOrm.PSQL_CONNECTION
      
        if PsqlOrm.engine is None:
            # Creating the async engine
            PsqlOrm.engine = create_async_engine(
                f"postgresql+asyncpg://{pg_conn_params['user']}:{pg_conn_params['password']}@{pg_conn_params['host']}:{pg_conn_params['port']}/{pg_conn_params['dbname']}",
                pool_size=pg_conn_params['pool_size'],
                max_overflow=pg_conn_params['max_overflow'],
                pool_timeout=pg_conn_params['pool_timeout'],
                pool_recycle=pg_conn_params['pool_recycle'],

            )
            logger.info("Async engine created successfully")
        else:
            logger.info("Reuse async engine connection")

        PsqlOrm.async_session = async_sessionmaker(
            PsqlOrm.engine, expire_on_commit=False
        )

    def session(self) -> AsyncSession:
        return PsqlOrm.async_session()

    @staticmethod
    async def with_session() -> AsyncGenerator[AsyncSession, None]:
        async with PsqlOrm.async_session() as db:
            yield db
    
    def create_sql(self, models):
        for model in models:
            create_table_sql = str(CreateTable(model.__table__).compile(PsqlOrm.engine))
            print(create_table_sql)