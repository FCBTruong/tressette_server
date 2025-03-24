from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from typing import Union

SECRET_KEY = "jTd9UwjMsYEAuyN"  # Replace with a secure secret key
ALGORITHM = "HS256"
SESSION_TOKEN_EXPIRE_MINUTES = 60 * 24 * 1  # Token expiration time in minutes # 1 days
LOGIN_TOKEN_EXPIRE_MINUTES = 60 * 24 * 90  # Token expiration time in minutes # 90 days


# Function to create JWT token
def create_session_token(data: dict, expires_delta: Union[timedelta, None] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=SESSION_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def create_login_token(data: dict, expires_delta: Union[timedelta, None] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=LOGIN_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# Function to verify JWT token
def verify_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None
