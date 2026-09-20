from pwdlib import PasswordHash
from fastapi import Request, Depends, HTTPException
from src.utils.db import get_db
from jwt import InvalidTokenError
import jwt
from src.utils.settings import settings
from src.models.user import User

password_hash = PasswordHash.recommended()

def get_password_hash(password):
    return password_hash.hash(password)

def verify_password(plain_password, hashed_password):
    return password_hash.verify(plain_password, hashed_password)


def decode_access_token(access_token: str) -> dict:
    return jwt.decode(access_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])


def is_authenticated(request:Request, db=Depends(get_db)):
    try:
        access_token= request.headers.get("access_token")

        data= decode_access_token(access_token)

        email= data.get("email")

        user= db.query(User).filter(User.email==email).first()

        if not user:
            raise HTTPException(401, "Unauthorized user")
        return user

    except(InvalidTokenError) as e:
        print("error:", e)
        raise HTTPException(401, "Unauthorized user")