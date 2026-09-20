from fastapi import APIRouter, Depends, status
from src.dtos.user import *
from src.utils.db import get_db
from src.services import user_service

user_route= APIRouter(prefix="/user")

#Registration route
@user_route.post("/register", status_code=status.HTTP_201_CREATED, response_model=UserResponse)
def register(user:UserDTO, db=Depends(get_db)):
    return user_service.register(user, db)


#Login route
@user_route.post("/login", status_code=status.HTTP_200_OK)
def login(data:LoginDTO, db=Depends(get_db)):
    return user_service.login(data, db)