from pydantic import BaseModel
from typing import List
from src.utils.constant import RoomStatus
from src.dtos.user import UserResponse

class RoomPlayerResponse(BaseModel):
    room_id:str
    host_id: int
    players:List[UserResponse]
    room_status: RoomStatus
