from pwdlib import PasswordHash
from fastapi import Request, Depends, HTTPException
from src.utils.db import Session as SessionLocal
from jwt import InvalidTokenError
import jwt
from src.utils.settings import settings
from src.models.user import User
from redis.asyncio import Redis
from src.utils.cache import get_redis, get_cached_user, user_from_cache_payload, set_cached_user

password_hash = PasswordHash.recommended()

def get_password_hash(password):
    return password_hash.hash(password)

def verify_password(plain_password, hashed_password):
    return password_hash.verify(plain_password, hashed_password)


# def decode_access_token(access_token: str) -> dict:
#     return jwt.decode(access_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])

def decode_access_token(token: str, expected_type: str = "access") -> dict:
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    if payload.get("type") != expected_type:      # stops a refresh token being used as an access token
        raise InvalidTokenError("Wrong token type")
    return payload


from datetime import datetime, timedelta, timezone

def create_token(email: str, token_type: str, expires: timedelta) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"email": email, "type": token_type, "iat": now, "exp": now + expires},
        settings.SECRET_KEY, algorithm=settings.ALGORITHM,
    )


async def is_authenticated(request:Request, redis: Redis = Depends(get_redis)):
    db = None
    try:
        access_token= request.headers.get("access_token")

        data= decode_access_token(access_token)

        email= data.get("email")
        if not email:
            raise HTTPException(401, "Unauthorized user")
        
        cached= await get_cached_user(redis, email)
        if cached:
            return user_from_cache_payload(cached)

        db = SessionLocal()
        user= db.query(User).filter(User.email==email).first()

        if not user:
            raise HTTPException(401, "Unauthorized user")
        await set_cached_user(redis, user)
        return user

    except(InvalidTokenError) as e:
        print("error:", e)
        raise HTTPException(401, "Unauthorized user")
    finally:
        if db is not None:
            db.close()
