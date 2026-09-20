from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean, UniqueConstraint
from src.utils.db import Base
import uuid
from datetime import datetime

# Id, room_id, user_id, role, is_alive, joined_at 

class Room_Player(Base):
    __tablename__="room_player"
    id = Column(
        String,
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    room_id=Column(String, ForeignKey("room.room_id"))
    user_id=Column(Integer, ForeignKey("users.id"))
    joined_at = Column(
        DateTime,
        default=datetime.now,
        nullable=False
    )

    __table_args__ = (
        UniqueConstraint("room_id", "user_id"),
    )