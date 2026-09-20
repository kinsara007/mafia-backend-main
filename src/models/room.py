from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Enum 
from src.utils.db import Base
import uuid
from datetime import datetime
from src.utils.constant import RoomStatus

class Room(Base):
    __tablename__ = "room"
    room_id = Column(
        String,
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    roomcode = Column(String, unique=True, nullable=False)
    host_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(
        Enum(RoomStatus),
        default=RoomStatus.WAITING,
        nullable=False
    )
    created_at = Column(DateTime, default=datetime.now, nullable=False)