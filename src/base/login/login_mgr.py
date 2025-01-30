import random
from src.base.security.jwt import create_login_token, verify_token
from src.constants import *
from src.postgres.orm import PsqlOrm
from src.postgres.sql_models import FirebaseAuthSchema, GuestsSchema, UserInfoSchema
import firebase_admin
from firebase_admin import auth, credentials
# Initialize Firebase Admin SDK
cred = credentials.Certificate("secrets/firebase_auth.json")
firebase_admin.initialize_app(cred)

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
        elif login_type == LOGIN_FACEBOOK or login_type == LOGIN_GOOGLE:
            # verify the token
            try:
                payload = verify_token(token)
                return payload.get("uid")
            except Exception as e:
                print(e)
        return -1
    
    def create_new_basic_user(self) -> UserInfoSchema:
        user_model = UserInfoSchema()
        user_model.gold = 0 
        user_model.level = 1

        # random avatar 1 -> 8
        avatar_id = random.randint(1, 8)
        user_model.avatar = str(avatar_id)
        return user_model

    async def login_firebase(self, token):
        try:
            print("Verifying token Firebase")
            decoded_token = auth.verify_id_token(token)
            firebase_uid = decoded_token.get("user_id")
            sign_in_provider = decoded_token.get("firebase").get("sign_in_provider")
        except Exception as e:
            print(e)
            return None
        
        print(f"Decoded token: {decoded_token}")
        async with PsqlOrm.get().session() as session:
            uid = -1
            firebase_auth = await session.get(FirebaseAuthSchema, firebase_uid)
            if firebase_auth:
                uid = firebase_auth.uid
            else:
                # Create a new user
                basic_user = self.create_new_basic_user()

                if sign_in_provider == "facebook.com":
                    basic_user.login_type = LOGIN_FACEBOOK
                elif sign_in_provider == "google.com":
                    basic_user.login_type = LOGIN_GOOGLE
                
                basic_user.name = decoded_token.get("name")
                basic_user.avatar = decoded_token.get("picture")

                session.add(basic_user)
                await session.commit()
                await session.refresh(basic_user)

                firebase_auth = FirebaseAuthSchema()
                firebase_auth.firebase_user_id = firebase_uid
                firebase_auth.uid = basic_user.uid
                firebase_auth.name = decoded_token.get("name")
                firebase_auth.sign_in_provider = sign_in_provider
                firebase_auth.email = decoded_token.get("email")
                firebase_auth.picture = decoded_token.get("picture")

                session.add(firebase_auth)
                await session.commit()
                uid = basic_user.uid
        
        # generate a new token
        new_token = create_login_token({
            "uid": uid
        })
        return new_token
