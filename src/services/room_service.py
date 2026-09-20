from sqlalchemy.orm import Session
from src.utils.constant import RoomStatus
from src.models.room import Room
from src.models.room_player import Room_Player
from fastapi import HTTPException
from src.models.user import User
from src.utils.settings import settings
from src.dtos.room import RoomPlayerResponse
from src.dtos.user import UserResponse
from src.ws.connection_manager import manager

import random
import string

ACTIVE_STATUSES = [
    RoomStatus.WAITING,
    RoomStatus.IN_PROGRESS
]


def generate_room_code(db:Session):
    while True:
        code = ''.join(
            random.choices(
                string.ascii_uppercase + string.digits,
                k=6
            )
        )

        existing_room = (
            db.query(Room)
            .filter(
                Room.roomcode == code,
                Room.status.in_(ACTIVE_STATUSES)
            )
            .first()
        )

        if not existing_room:
            return code


#create a room
def create_room(db:Session, user_id:int):

    room_code= generate_room_code(db)
    room= Room(roomcode=room_code, host_id=user_id, status=RoomStatus.WAITING)

    db.add(room)
    db.commit()
    db.refresh(room)

    # Add host as the first Room_Player so they:
    #   1. can call GET /room/{code}/get-details/ (which checks Room_Player membership)
    #   2. appear in the room's player list immediately
    #   3. receive WS broadcasts scoped to this room
    host_player = Room_Player(room_id=room.room_id, user_id=user_id)
    db.add(host_player)
    db.commit()

    return {"room_code": room.roomcode, "room_id": room.room_id}


#Find the room by room code
def validate_room_code(room_code:str, db:Session):
    room= db.query(Room).filter(Room.roomcode==room_code).first()
    return room


#join a room
async def join_room(room_code:str, db:Session, user:User):

    # 1. find the room
    room= validate_room_code(room_code, db)
    if not room:
        raise HTTPException(404, "No room found with the entered code")

    # 2. check if status of room is waiting
    if room.status != RoomStatus.WAITING:
        raise HTTPException(
            status_code=400,
            detail="Cannot join this room"
        )
    
    # 3. Check if user is already in the room
    existing_player = (
        db.query(Room_Player)
        .filter(
            Room_Player.room_id == room.room_id,
            Room_Player.user_id == user.id
        )
        .first()
    )

    if existing_player:
        raise HTTPException(409, "You are already in this room")

    # 4. Check if room is full
    player_count= db.query(Room_Player).filter(Room_Player.room_id==room.room_id).count()
    if player_count>settings.MAX_PLAYERS:
        raise HTTPException(400, detail="Room is full")

    # 5. create room player
    room_player= Room_Player(
        room_id=room.room_id,
        user_id= user.id
    )

    db.add(room_player)
    db.commit()
    db.refresh(room_player)
    room_players = db.query(Room_Player).filter(Room_Player.room_id == room.room_id).all()

    return {
        "msg":"User joined the room successfully",
        "room_players": room_players,
        "room_id": room.room_id,
        "lobby": room_snapshot(room, db),
    }



def serialize_room_details(room: Room, db: Session) -> RoomPlayerResponse:
    players = (
        db.query(Room_Player, User)
        .join(User, Room_Player.user_id == User.id)
        .filter(Room_Player.room_id == room.room_id)
        .all()
    )
    player_response = [
        UserResponse(id=user.id, email=user.email, name=user.name)
        for _room_player, user in players
    ]
    return RoomPlayerResponse(
        room_id=room.room_id,
        host_id=room.host_id,
        players=player_response,
        room_status=room.status,
    )


def room_snapshot(room: Room, db: Session) -> dict:
    return serialize_room_details(room, db).model_dump()


#get room details
def fetch_room_details(room_code:str, db:Session, user_id:int):

    # 1. find room
    room= validate_room_code(room_code, db)
    if not room:
        raise HTTPException(404, detail="Room does not exist")

    # 2.  Check whether the requesting user belongs to this room
    is_user= db.query(Room_Player).filter(Room_Player.user_id==user_id,
                                          Room_Player.room_id == room.room_id).first()
    if not is_user:
            raise HTTPException(403, "You are not allowed to access this room")

    return serialize_room_details(room, db)



#Leave a room
async def leave_room(room_code: str, user_id: int, db: Session):
    room = db.query(Room).filter(Room.roomcode == room_code).first()
    if not room:
        raise HTTPException(404, detail="Room not found")

    room_player = db.query(Room_Player).filter(
        Room_Player.room_id == room.room_id,
        Room_Player.user_id == user_id
    ).first()
    if not room_player:
        raise HTTPException(400, detail="You are not in this room")

    # Guard: leaving is only allowed before the game starts
    if room.status != RoomStatus.WAITING:
        raise HTTPException(400, detail="Cannot leave a room once the game has started")

    is_host = room.host_id == user_id

    if is_host:
        # Host leaving = room is dissolved. Delete dependent rows first
        # to avoid FK constraint errors, then the room itself.
        db.query(Room_Player).filter(Room_Player.room_id == room.room_id).delete()
        db.delete(room)
        db.commit()

        # Notify everyone still connected before their sockets become orphaned
        await manager.broadcast_to_room(room.room_id, {
            "event": "room_closed",
            "data": {"reason": "host_left"}
        })

        return {"message": "Room closed because host left"}

    # Non-host leaving: just remove them, room continues normally
    db.delete(room_player)
    db.commit()

    snapshot = room_snapshot(room, db)
    await manager.broadcast_to_room(room.room_id, {
        "event": "lobby_updated",
        "data": {**snapshot, "reason": "player_left", "user_id": user_id}
    })

    return {"message": "Left room successfully"}