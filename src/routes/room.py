from fastapi import APIRouter, Depends, status
from src.utils.db import get_db
from src.utils.auth import is_authenticated
from src.services import room_service
from src.dtos.room import RoomPlayerResponse
from src.ws.connection_manager import manager

room_routes= APIRouter(prefix="/room")


#create a room 
@room_routes.post("/create", status_code=status.HTTP_201_CREATED)
async def create_room(db=Depends(get_db), user= Depends(is_authenticated)):
    return room_service.create_room(db, user.id)


#player joining a room
@room_routes.post("/{room_code}/join", status_code=status.HTTP_201_CREATED)
async def join_room(room_code:str, db=Depends(get_db), user= Depends(is_authenticated)):
    result= await room_service.join_room(room_code, db, user)
    await manager.broadcast_to_room(result["room_id"], {
        "event": "lobby_updated",
        "data": {**result["lobby"], "reason": "player_joined", "user_id": user.id}
    })
    return result


#get room details and players list (no trailing slash — polling clients would 307-loop)
@room_routes.get("/{room_code}",
                 response_model=RoomPlayerResponse,
                 status_code=status.HTTP_200_OK)
async def get_room_details(room_code:str, db=Depends(get_db), user=Depends(is_authenticated)):
    return room_service.fetch_room_details(room_code, db, user.id)


@room_routes.get("/{room_code}/get-details",
                 response_model=RoomPlayerResponse,
                 status_code=status.HTTP_200_OK,
                 include_in_schema=False)
async def get_room_details_legacy(room_code:str, db=Depends(get_db), user=Depends(is_authenticated)):
    return room_service.fetch_room_details(room_code, db, user.id)


#leave a room
@room_routes.post("/{room_code}/leave", status_code=status.HTTP_200_OK)
async def leave_room(room_code:str, db=Depends(get_db), user=Depends(is_authenticated)):
    return await room_service.leave_room(room_code, user.id, db)

#start the game
# @room_routes.post()