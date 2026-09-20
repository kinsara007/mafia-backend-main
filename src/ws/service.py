from src.utils.db import get_db
from sqlalchemy.orm import Session
from src.models.game import Game
from src.utils.constant import GameStatus, Phase, Roles, Action, NIGHT_DURATION_SECONDS, DISCUSSION_DURATION_SECONDS, VOTING_DURATION_SECONDS
from src.dtos.gameAction import ActionRequest
from src.services.game_service import night_action, resolve_night, cast_vote, resolve_voting
from src.ws.connection_manager import manager
from src.models.game_action import GameAction
from src.models.game_player import GamePlayer
from fastapi import HTTPException
from src.dtos.gameAction import NightActionResponse
import asyncio
from src.utils.db import Session as SessionLocal



#------------------------------------------------------------------------------------------------
# Check which game is active for the current room
#------------------------------------------------------------------------------------------------

def get_active_game_for_room(room_id: str, db: Session):
    return (
        db.query(Game).filter(Game.room_id == room_id,Game.status 
                              == GameStatus.IN_PROGRESS).first()
    )





#------------------------------------------------------------------------------------------------
# Check if all night actions have been submitted
#------------------------------------------------------------------------------------------------
def all_night_actions_submitted(
    game_id: str,
    round_number: str,
    db: Session
):
    # 1. Get the active game
    game = (db.query(Game).filter(Game.game_id == game_id,
            Game.current_phase == Phase.NIGHT,
            Game.status == GameStatus.IN_PROGRESS
        )
        .first()
    )

    if not game:
        return False

    # 2. Roles that are required to perform a night action
    night_action_roles = [
        Roles.MAFIA,
        Roles.DOCTOR,
        Roles.DETECTIVE
    ]

    # 3. Get all alive players who have a night action
    required_players = (
        db.query(GamePlayer).filter(
            GamePlayer.game_id == game.game_id,
            GamePlayer.is_alive == True,
            GamePlayer.role.in_(night_action_roles)
        )
        .all()
    )

    # 4. Get actions submitted for the CURRENT round only
    actions = (
        db.query(GameAction)
        .filter(
            GameAction.game_id == game.game_id,
            GameAction.round_number == round_number,
            GameAction.phase == Phase.NIGHT
        )
        .all()
    )

    # 5. IDs of players who are required to act
    required_user_ids = {
        player.user_id
        for player in required_players
    }

    # 6. IDs of players who already submitted an action
    submitted_user_ids = {
        action.actor_id
        for action in actions
    }

    # 7. Check whether every required player has submitted
    return required_user_ids.issubset(submitted_user_ids)






#------------------------------------------------------------------------------------------------
# Check wheather all players have submitted the votes
#------------------------------------------------------------------------------------------------

def all_votes_submitted(
    game_id: str,
    round_number: int,
    db: Session,
    voting_attempt: int
):
    # 1. Get the active game
    game = (
        db.query(Game)
        .filter(
            Game.game_id == game_id,
            Game.current_phase == Phase.VOTING,
            Game.status == GameStatus.IN_PROGRESS
        )
        .first()
    )

    if not game:
        return False

    # 2. Get all alive players
    required_players = (
        db.query(GamePlayer)
        .filter(
            GamePlayer.game_id == game.game_id,
            GamePlayer.is_alive == True
        )
        .all()
    )

    # 3. Get ONLY VOTE actions for this round
    votes = (
        db.query(GameAction)
        .filter(
            GameAction.game_id == game.game_id,
            GameAction.round_number == round_number,
            GameAction.action_type == Action.VOTE,
            GameAction.voting_attempt == voting_attempt,
            GameAction.phase == Phase.VOTING
        )
        .all()
    )

    # 4. IDs of players who must vote
    required_user_ids = {
        player.user_id
        for player in required_players
    }

    # 5. IDs of players who have voted
    submitted_user_ids = {
        vote.actor_id
        for vote in votes
    }

    # Debug
    # print("Required players:", required_user_ids)
    # print("Submitted votes:", submitted_user_ids)
    # print("Missing votes:", required_user_ids - submitted_user_ids)

    # 6. Everyone must have voted
    return required_user_ids.issubset(submitted_user_ids)





#------------------------------------------------------------------------------------------------
#Trigger once all night players have submitted their action
#------------------------------------------------------------------------------------------------

async def trigger_night_resolution(room_id:str, game_id:str, db:Session):
    result= resolve_night(game_id, db)
    players = db.query(GamePlayer).filter(GamePlayer.game_id == game_id).all()

    # Get the updated game
    game = db.query(Game).filter(Game.game_id == game_id).first()
        
    # If all players have voted and game continues,
    # resolve_night() will have moved the game to NIGHT
    if game and game.current_phase == Phase.DAY_DISCUSSION:
        asyncio.create_task(start_discussion_timer(room_id,game.game_id,SessionLocal,DISCUSSION_DURATION_SECONDS))
 
    public_payload = {
        "killed_player_id": result.killed_player_id,
        "killed_player_role": None,
        "phase": result.phase.value if hasattr(result.phase, "value") else result.phase,
        "round_number": result.round_number,
        "winner": result.winner.value if result.winner else None,
        "duration_seconds": DISCUSSION_DURATION_SECONDS,
    }
    if result.killed_player_id:
        victim = db.query(GamePlayer).filter(
            GamePlayer.game_id == game_id,
            GamePlayer.user_id == result.killed_player_id,
        ).first()
        if victim and not victim.is_alive:
            public_payload["killed_player_role"] = victim.role.value

    await manager.broadcast_to_room(room_id, {
        "event": "night_resolved",
        "data": public_payload,
    })

    for player in players:
        if player.role != Roles.DETECTIVE:
            continue
        payload = build_payload_per_user(player, result, db)
        await manager.send_to_player(room_id, player.user_id, {
            "event": "night_resolved",
            "data": payload,
        })




#------------------------------------------------------------------------------------------------
#Build the payload as per the user: detetive should have info about the mafia but other 
# players shouldn't
#------------------------------------------------------------------------------------------------

def build_payload_per_user(player:GamePlayer,result:NightActionResponse, db:Session)->dict:
    """Filter the full night result down to what this specific player is allowed to see."""

    killed_role = None
    if result.killed_player_id:
        victim = db.query(GamePlayer).filter(
            GamePlayer.game_id == player.game_id,
            GamePlayer.user_id == result.killed_player_id
        ).first()
        if victim and not victim.is_alive:
            killed_role = victim.role.value

    base = {
        "killed_player_id": result.killed_player_id,
        "killed_player_role": killed_role,
        "phase": result.phase,
        "round_number": result.round_number,
        "winner": result.winner.value if result.winner else None,
        "duration_seconds": DISCUSSION_DURATION_SECONDS,
    }

    if player.role == Roles.DETECTIVE and result.detective_result:
        det = result.detective_result
        base["detective_result"] = det.model_dump() if hasattr(det, "model_dump") else det

    return base





#------------------------------------------------------------------------------------------------
#Trigger once all players have submitted their votes
#------------------------------------------------------------------------------------------------
async def trigger_voting_resolution(room_id:str, game_id:str, db:Session):
    result= resolve_voting(game_id, db)
   # players = db.query(GamePlayer).filter(GamePlayer.game_id == game_id).all()

    # Get the updated game
    game = db.query(Game).filter(Game.game_id == game_id).first()
    
    # Tie: start another voting timer
    if game and game.current_phase == Phase.VOTING:
        asyncio.create_task(start_voting_timer(room_id,game_id,SessionLocal,VOTING_DURATION_SECONDS))
        
    # If a player was eliminated and game continues,
    # resolve_morning() will have moved the game to NIGHT
    elif game and game.current_phase == Phase.NIGHT:

        asyncio.create_task(start_night_timer(room_id,game.game_id,SessionLocal,NIGHT_DURATION_SECONDS))

    await manager.broadcast_to_room(room_id, {
                "event": "morning_resolved",
                "data": result
        })
        #for player in players:
   
        # await manager.send_to_player(room_id, player.user_id, {
        #     "event": "morning_resolved",
        #     "data": result
        # })




#------------------------------------------------------------------------------------------------
# Timer for night actions
#------------------------------------------------------------------------------------------------

async def start_night_timer(room_id: str, game_id: str, db_factory, timeout_seconds: int = NIGHT_DURATION_SECONDS):
    print("Night timer started: ")
    await asyncio.sleep(timeout_seconds)
    db = db_factory()
    try:
        game = db.query(Game).filter(Game.game_id == game_id).first()
        if game.current_phase == Phase.NIGHT:  # hasn't been resolved yet
            await trigger_night_resolution(room_id, game_id, db)
    finally:
        db.close()




#------------------------------------------------------------------------------------------------
# Timer for morning actions: VOTING
#------------------------------------------------------------------------------------------------

async def start_voting_timer(room_id: str, game_id: str, db_factory, timeout_seconds: int = VOTING_DURATION_SECONDS):
    await asyncio.sleep(timeout_seconds)
    db= db_factory()
    try:
        game= db.query(Game).filter(Game.game_id==game_id).first()
        if game.current_phase== Phase.VOTING:
            await trigger_voting_resolution(room_id, game_id, db)
    finally:
            db.close()





#------------------------------------------------------------------------------------------------
#Day discussion function
#------------------------------------------------------------------------------------------------
async def handle_chat(room_id:str, user_id:int, payload, db:Session):
    game= get_active_game_for_room(room_id, db)
    if not game:
        raise HTTPException(404, detail="game not found")

    if game.current_phase!= Phase.DAY_DISCUSSION:
        raise HTTPException(400, detail="Chat is not active yet")

    player = db.query(GamePlayer).filter(GamePlayer.game_id == game.game_id,
            GamePlayer.user_id == user_id).first()
    

    if not player:
        raise HTTPException(status_code=403, detail="You are not part of this game")

    if not player.is_alive:
        raise HTTPException(status_code=403,detail="Dead players cannot participate in discussion")

    message = payload.get("message", "").strip()
    if not message:
        raise HTTPException(status_code=400,detail="Message cannot be empty")

    await manager.broadcast_to_room(
        room_id,
        {
            "event": "chat_message",
            "data": {"user_id": user_id, "text": message}
        }
    )
   


#------------------------------------------------------------------------------------------------
# resolve day discussion
#------------------------------------------------------------------------------------------------

async def resolve_day_discussion(
    room_id: str,
    game_id: str,
    db: Session
):
    game = (db.query(Game).filter(Game.game_id == game_id).first())

    if not game:
        return

    game.current_phase = Phase.VOTING
    game.voting_attempt = 1

    db.commit()

    await manager.broadcast_to_room(room_id, {
        "event": "voting_started",
        "data": {
            "phase": Phase.VOTING.value,
            "round_number": game.round_number,
            "duration_seconds": VOTING_DURATION_SECONDS,
        }
    })

    asyncio.create_task(start_voting_timer(room_id,game_id,SessionLocal,VOTING_DURATION_SECONDS))



#------------------------------------------------------------------------------------------------
#Day discussion timer
#------------------------------------------------------------------------------------------------
async def start_discussion_timer(
    room_id: str,
    game_id: str,
    db_factory,
    timeout_seconds: int = DISCUSSION_DURATION_SECONDS
):
    await asyncio.sleep(timeout_seconds)
    db = db_factory()

    try:
        game = (db.query(Game).filter(Game.game_id == game_id).first())

        if game and game.current_phase == Phase.DAY_DISCUSSION:

            await resolve_day_discussion(room_id, game_id,db)

    finally:
        db.close()


#------------------------------------------------------------------------------------------------
#Base for handling all the incoming events from the client
#------------------------------------------------------------------------------------------------
async def handle_incoming_message(room_id: str, user_id: int, data: dict, db:Session):
    event_type = data.get("event")

    try:
        if event_type == "night_action":
            game = get_active_game_for_room(room_id, db)
            action_data = ActionRequest(**data["payload"])
            result = night_action(user_id, game.game_id, action_data, db)

            # Notify just this player their action was recorded
            await manager.send_to_player(room_id, user_id, {
                "event": "action_confirmed",
                "data": result
            })

            # Check if everyone's submitted -> trigger resolution
            if all_night_actions_submitted(game.game_id, game.round_number, db):
                 await trigger_night_resolution(room_id, game.game_id, db)
            else: print("NO")

        elif event_type=="voting":
            try:
                # game_id:str, db:Session, vote_data: ActionRequest, user_id:int
                game = get_active_game_for_room(room_id, db)
                vote_data= ActionRequest(**data["payload"])
                result= cast_vote(game.game_id,db,vote_data,user_id)

                await manager.send_to_player(room_id, user_id,{
                    "event":"vote_confirmed",
                    "data":result
                })
                await manager.broadcast_to_room(room_id, {
                    "event": "vote_cast",
                    "data": {
                        "voter_id": user_id,
                        "target_id": vote_data.target_id,
                    }
                })
                # Check if everyone submitted their votes-> trigger resolution
                if all_votes_submitted(game.game_id, game.round_number, db, game.voting_attempt):
                    await trigger_voting_resolution(room_id, game.game_id, db)
                else: print("NO")
            except HTTPException as e:
                await manager.send_to_player(room_id, user_id,
                    {
                        "event": "error",
                        "status_code": e.status_code,
                        "message": e.detail
                    })

        elif event_type=="day_discussion":
            await handle_chat(room_id, user_id, data["payload"], db)
    

    except HTTPException as e:

            await manager.send_to_player(room_id,user_id,
                {
                    "event": "error",
                    "status_code": e.status_code,
                    "message": e.detail
                }
            )