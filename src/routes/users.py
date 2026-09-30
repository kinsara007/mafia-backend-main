from fastapi import APIRouter, Depends, status, HTTPException
from src.dtos.user import *
from src.utils.db import get_db
from src.services import user_service
from src.utils import auth
from src.utils.cache import get_redis
from jwt import InvalidTokenError
from src.models.user import User
from datetime import datetime, timedelta
from src.utils.settings import settings

user_route= APIRouter(prefix="/user")

#Registration route
@user_route.post("/register", status_code=status.HTTP_201_CREATED, response_model=UserResponse)
def register(user:UserDTO, db=Depends(get_db)):
    return user_service.register(user, db)


#Login route
@user_route.post("/login", status_code=status.HTTP_200_OK)
async def login(data:LoginDTO, db=Depends(get_db), redis=Depends(get_redis)):
    return await user_service.login(data, db, redis)


#Refresh token
@user_route.post("/refresh")
def refresh(body: RefreshDTO, db = Depends(get_db)):
    try:
        payload = auth.decode_access_token(body.refresh_token, expected_type="refresh")
    except InvalidTokenError:
        raise HTTPException(401, "Invalid refresh token")
    user = db.query(User).filter(User.email == payload["email"]).first()
    if not user:
        raise HTTPException(401, "Invalid refresh token")
    return {
        "access_token": auth.create_token(user.email, "access", timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)),
        "refresh_token": auth.create_token(user.email, "refresh", timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)),  # rolling: active players never get logged out
    }