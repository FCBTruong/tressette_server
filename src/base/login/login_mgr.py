import random
from src.base.logs.logs_mgr import write_log
from src.base.security.jwt import create_login_token, verify_token
from src.config.settings import settings
from src.constants import *
from src.game.game_vars import game_vars
from src.game.users_info_mgr import users_info_mgr
from src.postgres.orm import PsqlOrm
from src.postgres.sql_models import FirebaseAuthSchema, GuestsSchema, UserInfoSchema
import firebase_admin
from firebase_admin import auth, credentials
# Initialize Firebase Admin SDK
cred = credentials.Certificate("secrets/firebase_auth.json")
firebase_admin.initialize_app(cred)
import aiohttp
from src.game.tressette_config import config as tress_config

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
        elif login_type == LOGIN_TOKEN:
            # verify the token
            try:
                payload = verify_token(token)
                return payload.get("uid")
            except Exception as e:
                print(e)
        elif login_type == LOGIN_UID_CHEAT:
            if not settings.ENABLE_CHEAT:
                return -1

            return int(token)
        return -1
    
    def create_new_basic_user(self) -> UserInfoSchema:
        user_model = UserInfoSchema()
        user_model.gold = 0
        user_model.level = 1

        avatar_id = random.choice(AVATAR_IDS)
        user_model.avatar = str(avatar_id)
        return user_model

    # Return permanent token (90days)
    async def login_firebase(self, token, guest_id=''):
        if settings.DEV_MODE:
            firebase_uid = token
            decoded_token = {
            }
            sign_in_provider = "google.com"
        else:
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

                # Update user info
                user_info = await users_info_mgr.get_user_info(uid)
                has_change = False
                if decoded_token.get("name") and user_info.name != decoded_token.get("name"):
                    user_info.name = decoded_token.get("name")
                    has_change = True
                if decoded_token.get("picture") and user_info.avatar_third_party != decoded_token.get("picture"):
                    user_info.avatar_third_party = decoded_token.get("picture")
                    has_change = True
                if has_change:
                    await user_info.commit_to_database('avatar_third_party', 'name')
            else:
                login_type = 0
                if sign_in_provider == "facebook.com":
                    login_type = LOGIN_FACEBOOK
                elif sign_in_provider == "google.com":
                    login_type = LOGIN_GOOGLE
                elif sign_in_provider == "apple.com":
                    login_type = LOGIN_APPLE
                
                user_name = decoded_token.get("name")
                if not user_name:
                    user_name = "tressette player"
                avatar_url = decoded_token.get("picture")
              
                is_exist_acc = False
                if guest_id != '':
                    # try get user info by guest id
                    guest = await session.get(GuestsSchema, guest_id)
                    if guest:
                        uid = guest.uid
                        is_exist_acc = True
                if is_exist_acc:
                    # Update user info
                    user_info = await users_info_mgr.get_user_info(uid)
                    if user_info.login_type != LOGIN_GUEST: # allow link only guest account
                        return
                    user_info.login_type = login_type
                    user_info.avatar_third_party = avatar_url
                    if avatar_url:
                        user_info.avatar = avatar_url
                    
                    # Add 100k gold to user as a reward for linking account
                    user_info.add_gold(100000)

                    user_info.name = user_name
                    await user_info.commit_to_database('avatar_third_party', 'name', 'login_type', 'avatar', 'gold')
                else:
                    # Create a new user
                    basic_user = self.create_new_basic_user()
                    basic_user.name = user_name
                
                    basic_user.avatar_third_party = decoded_token.get("picture")
                    if not basic_user.avatar_third_party:
                        basic_user.avatar = str(random.choice(AVATAR_IDS))
                    else:
                        basic_user.avatar = basic_user.avatar_third_party
                    basic_user.login_type = login_type

                    session.add(basic_user)
                    await session.commit()
                    await session.refresh(basic_user)
                    uid = basic_user.uid

                firebase_auth = FirebaseAuthSchema()
                firebase_auth.firebase_user_id = firebase_uid
                firebase_auth.uid = uid
                firebase_auth.name = decoded_token.get("name")
                firebase_auth.sign_in_provider = sign_in_provider
                firebase_auth.email = decoded_token.get("email")
                firebase_auth.picture = decoded_token.get("picture")

                session.add(firebase_auth)
                await session.commit()

                write_log(uid, "new_user", "firebase", [])
        
        # generate a new token
        new_token = create_login_token({
            "uid": uid
        })
        return new_token
    
    # IOS can not use firebase auth, so we need to use google auth -> login to firebase -> login to our server
    async def login_by_google_token(self, token):
        API_KEY = settings.FIREBASE_KEY  # Found in Firebase Console > Project settings
        url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithIdp?key={API_KEY}"
        
        payload = {
            "postBody": f"id_token={token}&providerId=google.com",
            "requestUri": "http://localhost",  # Can be any valid URL
            "returnSecureToken": True
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                firebase_data = await response.json()

                # Check for errors in Firebase response
                if response.status != 200:
                    error_message = firebase_data.get("error", {}).get("message", "Unknown error")
                    return {"success": False, "error": error_message}

                # Extract the Firebase ID token
                firebase_token = firebase_data.get("idToken")
                if not firebase_token:
                    return {"success": False, "error": "No ID token returned"}

                return {"success": True, "firebase_token": firebase_token}

    async def login_by_apple_token(self, token):
        API_KEY = settings.FIREBASE_KEY # Replace with your Firebase API key
        url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithIdp?key={API_KEY}"

        payload = {
            "postBody": f"id_token={token}&providerId=apple.com",
            "requestUri": "http://localhost",  # Can be any valid URL
            "returnSecureToken": True
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                firebase_data = await response.json()
                print("apple firebase_data:::", firebase_data)

                # Check for errors in Firebase response
                if response.status != 200:
                    error_message = firebase_data.get("error", {}).get("message", "Unknown error")
                    return {"success": False, "error": error_message}

                # Extract the Firebase ID token
                firebase_token = firebase_data.get("idToken")
                if not firebase_token:
                    return {"success": False, "error": "No ID token returned"}

                return {"success": True, "firebase_token": firebase_token}
