# Id, game_id, round_number, phase, actor_id, action_type, target_id, created_at 

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum
from src.utils.db import Base
import uuid
from src.utils.constant import Phase, Action
from datetime import datetime

class GameAction(Base):
    __tablename__="game_action"
    game_action_id= Column(String, primary_key=True, default=lambda:str(uuid.uuid4()))
    game_id= Column(String, ForeignKey("game.game_id"), nullable=False)
    round_number = Column(Integer, nullable=False )
    phase= Column(Enum(Phase), default=Phase.NIGHT)
    actor_id= Column(Integer, ForeignKey("users.id"), nullable=False)
    action_type= Column(Enum(Action), nullable=False)
    target_id= Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at= Column(DateTime, default=datetime.now, nullable=False)
    voting_attempt = Column(Integer)

