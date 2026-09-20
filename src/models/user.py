from sqlalchemy import Column, Integer, String, DateTime
from src.utils.db import Base

class User(Base):
    __tablename__= "users"
    id= Column(Integer, primary_key=True)
    name= Column(String, nullable=False)
    password= Column(String, nullable=False)
    email= Column(String, nullable=False)
