from sqlalchemy import Column, ForeignKey, Integer, String, Enum, DateTime
from src.utils.db import Base
from src.utils.constant import GameStatus, Phase, Winner
import uuid
from datetime import datetime

class Game(Base):
    __tablename__="game"
    game_id= Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    room_id=Column(String, ForeignKey("room.room_id"), nullable=False)
    status= Column(Enum(GameStatus), default=GameStatus.IN_PROGRESS)
    current_phase= Column(Enum(Phase), default=Phase.NIGHT)
    round_number = Column(Integer, default=1, nullable=False)
    started_at = Column(DateTime, default=datetime.now, nullable=False)
    ended_at= Column(DateTime, nullable=True)
    winner= Column(Enum(Winner), nullable=True)
    voting_attempt = Column(Integer, default=1)

