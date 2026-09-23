from fastapi import FastAPI
from src.utils.db import engine, Base
from src.models import *
from src.routes.users import user_route
from src.routes.room import room_routes
from src.routes.game import game_route
from src.ws.route import router
from fastapi.middleware.cors import CORSMiddleware
from src.utils.settings import settings
from contextlib import asynccontextmanager
from redis.asyncio import Redis

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting Redis...")
    if settings.REDIS_URL:
        app.state.redis = Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
        )
    else:
        app.state.redis = Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            decode_responses=True,
        )
    yield
    print("Closing Redis...")
    await app.state.redis.close()


Base.metadata.create_all(engine)

app= FastAPI(title="Mafia game", lifespan=lifespan)


origins = [
    "http://localhost:4200",
    "http://localhost",
    "http://localhost:8080",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
    "https://tdn7vk4x-3000.inc1.devtunnels.ms",
]
if settings.FRONTEND_URL:
    origins.append(settings.FRONTEND_URL.rstrip("/"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(user_route)
app.include_router(room_routes)
app.include_router(game_route)
app.include_router(router)
