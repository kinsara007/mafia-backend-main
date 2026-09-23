import json
from starlette.requests import HTTPConnection
from redis.asyncio import Redis
from src.utils.settings import settings
from src.models.user import User


def get_redis(connection: HTTPConnection) -> Redis:
    return connection.app.state.redis


def user_email_key(email: str) -> str:
    return f"user:email:{email.lower()}"


def user_from_cache_payload(payload: dict) -> User:
    return User(id=payload["id"], name=payload["name"], email=payload["email"])


async def get_cached_user(redis: Redis, email: str) -> dict | None:
    try:
        raw = await redis.get(user_email_key(email))
    except Exception:
        return None
    if not raw:
        return None
    return json.loads(raw)


async def set_cached_user(redis: Redis, user: User) -> None:
    payload = json.dumps({
        "id": user.id,
        "name": user.name,
        "email": user.email,
    })
    try:
        await redis.set(user_email_key(user.email), payload, ex=settings.CACHE_TTL)
    except Exception:
        return

    
async def invalidate_cached_user(redis: Redis, email: str) -> None:
    try:
        await redis.delete(user_email_key(email))
    except Exception:
        return


#---------------------------------------------------------------------------------------------------------------------------
# Room cache
#---------------------------------------------------------------------------------------------------------------------------
def room_lobby_key(room_id: str) -> str:
    return f"room:{room_id}:lobby"


def room_code_lobby_key(room_code: str) -> str:
    return f"room:code:{room_code}:lobby"


async def get_cached_lobby(redis: Redis, room_id: str) -> dict | None:
    try:
        raw = await redis.get(room_lobby_key(room_id))
        if not raw:
            return None
        return json.loads(raw)
    except Exception:
        return None


async def get_cached_lobby_by_code(redis: Redis, room_code: str) -> dict | None:
    try:
        raw = await redis.get(room_code_lobby_key(room_code))
        if not raw:
            return None
        return json.loads(raw)
    except Exception:
        return None


async def set_cached_lobby(redis: Redis, room_id: str, payload: dict) -> None:
    try:
        body = json.dumps(payload)
        await redis.set(room_lobby_key(room_id), body, ex=settings.CACHE_TTL)
        room_code = payload.get("room_code")
        if room_code:
            await redis.set(room_code_lobby_key(room_code), body, ex=settings.CACHE_TTL)
    except Exception:
        return


async def invalidate_cached_lobby(redis: Redis, room_id: str, room_code: str | None = None) -> None:
    try:
        if not room_code:
            cached = await get_cached_lobby(redis, room_id)
            if cached:
                room_code = cached.get("room_code")
        keys = [room_lobby_key(room_id)]
        if room_code:
            keys.append(room_code_lobby_key(room_code))
        await redis.delete(*keys)
    except Exception:
        return