from sqlalchemy.orm import Session
from src.dtos.user import *
from src.models.user import User
from fastapi import HTTPException
from src.utils import auth
from datetime import datetime, timedelta
from src.utils.settings import settings
from src.utils.cache import set_cached_user
from redis.asyncio import Redis
import jwt

def register(user:UserDTO, db:Session):

    is_user_present= db.query(User).filter(User.email==user.email).first()

    #verify if user email exists already
    if is_user_present:
        raise HTTPException(400, detail="User email already exists")

    #get hashed password
    hashed_password= auth.get_password_hash(user.password)

    #create user object
    new_user= User(name= user.name, email= user.email, password= hashed_password)
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


async def login(data:LoginDTO, db:Session, redis:Redis):

    user= db.query(User).filter(User.email==data.email).first()
    if not user:
        raise HTTPException(404, detail="User email not found!")

    pass_verification = auth.verify_password(data.password, user.password)
    if not pass_verification:
        raise HTTPException(400, detail="Incorrect Password")

    exp_time= datetime.now()+timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token= jwt.encode({"email":user.email, "exp":exp_time}, settings.SECRET_KEY, 
                             settings.ALGORITHM)
    await set_cached_user(redis, user)
    return {
        "access_token": access_token,
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
        },
    }
