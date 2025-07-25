

import random
import uuid

from src.base.logs.logs_mgr import write_log
from src.game.game_vars import game_vars
from src.postgres.orm import PsqlOrm
from src.postgres.sql_models import GuestsSchema, UserInfoSchema
from src.constants import *

class GuestMgr:
    async def create_guest_account(self) -> str:
        # Generate a random UUID (UUID4)
        guest_id = str(uuid.uuid4())
        uid = None

        async with PsqlOrm.get().session() as session:
            # Create a new user model
            user_model = UserInfoSchema()
            user_model.gold = 0
            user_model.level = 1

            # random avatar 1 -> 8
            avatar_id = random.choice(AVATAR_IDS)
            user_model.avatar = str(avatar_id)
            user_model.login_type = LOGIN_GUEST

            # Add the user model to the session
            session.add(user_model)
            
            # Commit the session to the database
            await session.commit()
            await session.refresh(user_model)

            # Now set the name with the generated UID
            user_model.name = f"Guest_{user_model.uid}"

            # Commit again to save the updated name
            await session.commit()

            # Create a new record in the 'guests' table
            guest_model = GuestsSchema()
            guest_model.guest_id = guest_id
            guest_model.uid = user_model.uid
            uid = user_model.uid

            # Add the guest record to the session
            session.add(guest_model)
            # Commit the session to save the guest record
            await session.commit()
        write_log(uid, "new_user", "guest", [])
        return guest_id