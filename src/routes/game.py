from fastapi import APIRouter, Depends, status
from src.utils.db import get_db
from src.utils.auth import is_authenticated
from src.services import game_service
from src.utils.constant import Action
from src.dtos.gameAction import ActionRequest, NightActionResponse
import asyncio
from src.utils.db import Session as SessionLocal
from src.ws.service import start_night_timer
from src.ws.connection_manager import manager
from src.utils.constant import NIGHT_DURATION_SECONDS
from src.utils.cache import get_redis

game_route= APIRouter(prefix="/game")

#start a game
@game_route.post("/{room_code}/start", status_code= status.HTTP_201_CREATED)
async def start_game(room_code:str, user=Depends(is_authenticated), db=Depends(get_db), redis=Depends(get_redis)):
    result = await game_service.start_game(
        user.id,
        db,
        room_code,
        redis,
    )
    await manager.broadcast_to_room( result["room_id"], {
        "event": "game_started",
        "data": {
            "game_id": result["game_id"],
            "phase": "NIGHT",
            "round_number": 1,
            "duration_seconds": NIGHT_DURATION_SECONDS,
        }
    })


    asyncio.create_task(
        start_night_timer(
            result["room_id"],
            result["game_id"],
            SessionLocal,
            NIGHT_DURATION_SECONDS
        )
    )


    return result
    # return game_service.start_game(user.id, db, room_code)


#take a night action
@game_route.post("/{game_id}/action", status_code=status.HTTP_201_CREATED)
def night_action(game_id, action_data: ActionRequest ,db=Depends(get_db), user=Depends(is_authenticated)):
    return game_service.night_action(user.id, game_id, action_data,db)


#resolve night actions
@game_route.get("/{game_id}/resolve-night", status_code=status.HTTP_200_OK, 
                response_model=NightActionResponse)
def resolve_night(game_id:str, db=Depends(get_db)):
    return game_service.resolve_night(game_id, db)


#detective's endpoint
@game_route.get("/{game_id}/detective-result")
def detective_result(game_id: str,current_user = Depends(is_authenticated),
                     db = Depends(get_db)):
    return game_service.get_detective_result(game_id=game_id, user_id=current_user.id,db=db)


#Voting
@game_route.post("/{game_id}/vote")
def vote(game_id:str, vote_data:ActionRequest ,user=Depends(is_authenticated), db=Depends(get_db)):
    return game_service.cast_vote(game_id, db, vote_data, user.id)


#Resolve morning
@game_route.post("/{game_id}/resolve-morning")
def resolve_morning(game_id:str , db=Depends(get_db)):
    return game_service.resolve_voting(game_id, db)



# endpoint for fetching the current state of the game
@game_route.get("/game/{room_code}/state")
async def get_game_state(
    room_code: str,
    user = Depends(is_authenticated),
    db = Depends(get_db),
    redis = Depends(get_redis),
):
    return await game_service.fetch_state(db, room_code, user, redis)