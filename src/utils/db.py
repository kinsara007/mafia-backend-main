from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from src.utils.settings import settings

Base= declarative_base()
database_url = settings.DATABASE_URL
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
engine= create_engine(url=database_url)
Session= sessionmaker(bind=engine)

def get_db():
    session= Session()
    try:
        yield session
    finally:
        session.close()