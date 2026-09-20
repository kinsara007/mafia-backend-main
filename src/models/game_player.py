from sqlalchemy import Column, Integer, String, ForeignKey, Enum, Boolean
from src.utils.constant import Roles
import uuid
from src.utils.db import Base


class GamePlayer(Base):
    __tablename__="game_player"
    game_player_id= Column(String, primary_key=True, default=lambda:str(uuid.uuid4()))
    user_id= Column(Integer, ForeignKey("users.id"), nullable=False)
    game_id= Column(String, ForeignKey("game.game_id"), nullable=False)
    role= Column(Enum(Roles), nullable=False)
    is_alive= Column(Boolean, default=True, nullable=False)

