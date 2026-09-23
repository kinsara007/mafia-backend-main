from fastapi import APIRouter, WebSocket, Query, Depends, WebSocketDisconnect
from jwt import InvalidTokenError
from src.utils.db import get_db
from src.models.user import User
from src.ws.connection_manager import manager
from src.ws.service import handle_incoming_message
from src.utils.auth import decode_access_token
from src.models.room import Room
from src.services.room_service import get_lobby
from redis.asyncio import Redis
from src.utils.cache import get_redis, get_cached_user, user_from_cache_payload, set_cached_user

router= APIRouter()


@router.websocket("/ws/room/{room_id}")
async def room_websocket(websocket: WebSocket, room_id: str, token: str = Query(...), 
                        db=Depends(get_db), redis: Redis = Depends(get_redis)):
    try:
        payload = decode_access_token(token)
        user_email = payload.get("email")
    except (InvalidTokenError, KeyError):
        await websocket.close(code=1008)
        return

    if not user_email:
        await websocket.close(code=1008)
        return

    cache = await get_cached_user(redis, user_email)
    if cache:
        usr = user_from_cache_payload(cache)
    else:
        usr = db.query(User).filter(User.email == user_email).first()
        if not usr:
            await websocket.close(code=1008)
            return
        await set_cached_user(redis, usr)
    
    await manager.connect(room_id, usr.id, websocket)
    room = db.query(Room).filter(Room.room_id == room_id).first()
    if room:
        snapshot = await get_lobby(room, db, redis)
        await manager.send_to_player(room_id, usr.id, {
            "event": "lobby_updated",
            "data": {**snapshot, "reason": "connected"}
        })

    try:
        while True:
            data = await websocket.receive_json()
            await handle_incoming_message(room_id, usr.id, data, db)
    except WebSocketDisconnect:
        manager.disconnect(room_id, usr.id)
        await manager.broadcast_to_room(room_id, {
            "event": "player_disconnected",
            "data": {"user_id": usr.id}
        })

