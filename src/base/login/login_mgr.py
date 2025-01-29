from src.constants import *
from src.postgres.orm import PsqlOrm
from src.postgres.sql_models import GuestsSchema


class LoginMgr:
    def __init__(self):
        pass

    async def authenticate_user(self, login_type, token) -> int:
        if login_type == LOGIN_GUEST:
            async with PsqlOrm.get().session() as session:
                # Query the 'guests' table for a record with the given guest ID
                guest = await session.get(GuestsSchema, token)
                print("token:::", token)
                if guest:
                    return guest.uid
                
        return -1


