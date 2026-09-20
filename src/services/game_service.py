from sqlalchemy.orm import Session
from src.services.room_service import validate_room_code
from fastapi import HTTPException
from src.models.user import User
from src.utils.constant import RoomStatus
from src.utils.settings import settings
from src.models.room_player import Room_Player
from src.models.game import Game
from src.models.game_player import GamePlayer
from src.utils.constant import Roles, Action, Phase, GameStatus, Winner
import random
from src.dtos.gameAction import ActionRequest, NightActionResponse, DetectiveResult
from src.models.game_action import GameAction
from datetime import datetime
from src.models.room import Room

async def start_game(user_id, db:Session, room_code:str):

    # 1. verify the room by code
    room= validate_room_code(room_code, db)
    if not room:
        raise HTTPException(404, detail="Room not found")


    # 2. check if user is the host, only host can start the game
    if room.host_id != user_id:
        raise HTTPException(403, detail="Only host is allowed to start the game")


    # 3. Room must be waiting
    if room.status!= RoomStatus.WAITING:
        raise HTTPException(400, "The game has already started")


    # 4. Check if room has required number of players
    room_players= db.query(Room_Player).filter(Room_Player.room_id==room.room_id).all()
    if len(room_players) < settings.MIN_PLAYERS:
        raise HTTPException(400, detail=f"Atleast {settings.MIN_PLAYERS} players are required to start the game")


    # 5. Create game
    game= Game(room_id= room.room_id)
    db.add(game)

    # Flush so game.game_id is available, changes not committed yet
    db.flush()


    # 6. Create role list (1 mafia at 5–6 players, 2 mafia at 7+)
    roles = [
        Roles.MAFIA,
        Roles.DETECTIVE,
        Roles.DOCTOR,
        Roles.VILLAGER,
        Roles.VILLAGER,
    ]
    if len(room_players) >= 7:
        roles.append(Roles.MAFIA)
    while len(roles) < len(room_players):
        roles.append(Roles.VILLAGER)
    roles = roles[:len(room_players)]


    # 7. Shuffle roles
    random.shuffle(roles)


    # 8. Assign roles
    for player, role in zip(room_players, roles):

        game_player = GamePlayer(
            game_id=game.game_id,
            user_id=player.user_id,
            role=role,
            is_alive=True
        )

        db.add(game_player)


    # 9. Update the room status
    room.status=RoomStatus.IN_PROGRESS


    # 10. Commit everything
    db.commit()

    return {"msg":"Game started Successfully", "game_id": game.game_id, "room_id":room.room_id}






ROLE_ACTIONS = {
    Roles.MAFIA: Action.KILL,
    Roles.DOCTOR: Action.PROTECT,
    Roles.DETECTIVE: Action.INVESTIGATE,
}


# Take a night action (KILL, INVESTIGATE, PROTECT)
def night_action(user_id: str, game_id: str, action_data: ActionRequest, db: Session):

    # 1. Check if the game is present
    game = db.query(Game).filter(Game.game_id == game_id).first()
    if not game:
        raise HTTPException(404, detail="No game found for this id")

    # 2. Check game is currently in NIGHT phase
    if game.current_phase != Phase.NIGHT:
        raise HTTPException(
            status_code=400,
            detail="This action can only be performed during the night"
        )

    # 3. Fetch actor and target
    actor = db.query(GamePlayer).filter(
        GamePlayer.user_id == user_id,
        GamePlayer.game_id == game.game_id
    ).first()

    target_user = db.query(GamePlayer).filter(
        GamePlayer.user_id == action_data.target_id,
        GamePlayer.game_id == game.game_id
    ).first()

    if not actor:
        raise HTTPException(400, detail="User not present in this game")

    # 4. Dead players cannot perform actions
    if not actor.is_alive:
        raise HTTPException(
            status_code=400,
            detail="Dead players cannot perform actions"
        )

    # 5. Check whether this role can perform this action
    allowed_action = ROLE_ACTIONS.get(actor.role)
    if allowed_action != action_data.action_type:
        raise HTTPException(
            status_code=403,
            detail=f"{actor.role.value} cannot perform {action_data.action_type.value}"
        )

    # 6. Check if target user is part of this game
    if not target_user:
        raise HTTPException(400, detail="Target user not present in this game")

    # 7. Self-targeting rule
    #    Doctor is allowed to self-protect; Mafia/Detective cannot target self.
    #    Adjust this if your ruleset differs.
    if actor.user_id == target_user.user_id and actor.role != Roles.DOCTOR:
        raise HTTPException(400, detail="You cannot perform this action on yourself")

    # 8. Target must be alive
    if not target_user.is_alive:
        raise HTTPException(
            status_code=400,
            detail="Cannot target a dead player"
        )

    # 9. Upsert action — one action per actor per round/phase.
    #    Lets a player change their mind before the phase resolves,
    #    and prevents duplicate rows from breaking resolution logic.
    existing_action = db.query(GameAction).filter(
        GameAction.game_id == game_id,
        GameAction.round_number == game.round_number,
        GameAction.phase == Phase.NIGHT,
        GameAction.actor_id == user_id
    ).first()

    if existing_action:
        existing_action.target_id = action_data.target_id
        existing_action.action_type = action_data.action_type
        db.commit()
        db.refresh(existing_action)
        return {
            "message": "Night action updated successfully",
            "action_id": existing_action.game_action_id
        }

    game_action = GameAction(
        game_id=game_id,
        round_number=game.round_number,
        phase=Phase.NIGHT,
        actor_id=user_id,
        action_type=action_data.action_type,
        target_id=action_data.target_id
    )

    db.add(game_action)
    db.commit()
    db.refresh(game_action)

    return {
        "message": "Night action submitted successfully",
        "action_id": game_action.game_action_id
    }

# DETERMINE THE WINNER

# Helper: check win condition. Returns winning side or None if game continues.
def check_win_condition(game_id: str, db: Session):
    alive_players = db.query(GamePlayer).filter(
        GamePlayer.game_id == game_id,
        GamePlayer.is_alive == True
    ).all()

    mafia_count = sum(1 for p in alive_players if p.role == Roles.MAFIA)
    villager_count = len(alive_players) - mafia_count

    if mafia_count == 0:
        return Winner.VILLAGERS
    if mafia_count >= villager_count:
        return Winner.MAFIA
    return None




# RESOLVE NIGHT ACTIONS
def resolve_night(game_id:str, db:Session):

    game= db.query(Game).filter(Game.game_id==game_id).first()
    if not game:
        raise HTTPException(404, detail="No game found")

    if game.current_phase != Phase.NIGHT:
        raise HTTPException(400, detail="Game is not in the night phase")

    actions = (db.query(GameAction).filter(
        GameAction.game_id == game_id,
        GameAction.round_number == game.round_number,
        GameAction.phase == Phase.NIGHT
    )
    .all())

    mafia_targets = []
    doctor_target = None
    detective_target = None

    for action in actions:

        if action.action_type == Action.KILL:
            mafia_targets.append(action.target_id)

        elif action.action_type == Action.PROTECT:
            doctor_target = action.target_id

        elif action.action_type == Action.INVESTIGATE:
            detective_target = action.target_id

    mafia_target = None
    if mafia_targets:
        counts = {}
        for t in mafia_targets:
            counts[t] = counts.get(t, 0) + 1
        max_votes = max(counts.values())
        top_targets = [t for t, c in counts.items() if c == max_votes]
        mafia_target = top_targets[0]

    # Determine who dies
    killed_player_id = None

    if mafia_target is not None:
        if mafia_target != doctor_target:
            killed_player_id = mafia_target

    if killed_player_id:
        victim = db.query(GamePlayer).filter(
            GamePlayer.game_id == game_id,
            GamePlayer.user_id == killed_player_id
        ).first()
        if victim:
            victim.is_alive = False

    game.current_phase = Phase.DAY_DISCUSSION
    db.commit()

    winner = check_win_condition(game_id, db)
    if winner:
        game.status = GameStatus.COMPLETED
        game.current_phase = Phase.ENDED
        game.winner = winner
        game.ended_at = datetime.now()
        db.commit()

 #********************************** ONLY FOR DETECTIVE TO KNOW **********************************
    detective_result = None
    if detective_target is not None:
        investigated_player = db.query(GamePlayer).filter(
            GamePlayer.game_id == game_id,
            GamePlayer.user_id == detective_target
        ).first()
        if investigated_player:
            actual_is_mafia = investigated_player.role == Roles.MAFIA
            detective_result = DetectiveResult(
                target_id=detective_target,
                is_mafia=actual_is_mafia,
            )
#********************************** ONLY FOR DETECTIVE TO KNOW **********************************

    return NightActionResponse(
        killed_player_id=killed_player_id,
        winner=winner,
        detective_result=detective_result,
        phase=game.current_phase.value,   
        round_number=game.round_number  
    )


def get_detective_result(
    game_id: str,
    user_id: int,
    db: Session
):
    # Check game exists
    game = (
        db.query(Game)
        .filter(Game.game_id == game_id)
        .first()
    )

    if not game:
        raise HTTPException(
            status_code=404,
            detail="No game found"
        )

    # Check player
    player = (
        db.query(GamePlayer)
        .filter(
            GamePlayer.game_id == game_id,
            GamePlayer.user_id == user_id
        )
        .first()
    )

    if not player:
        raise HTTPException(
            status_code=403,
            detail="You are not part of this game"
        )

    # Make sure player is Detective
    if player.role != Roles.DETECTIVE:
        raise HTTPException(
            status_code=403,
            detail="Only the Detective can view this result"
        )

    # Get this Detective's investigation
    investigation = (
        db.query(GameAction)
        .filter(
            GameAction.game_id == game_id,
            GameAction.round_number == game.round_number,
            GameAction.phase == Phase.NIGHT,
            GameAction.actor_id == user_id,
            GameAction.action_type == Action.INVESTIGATE
        )
        .first()
    )

    if not investigation:
        raise HTTPException(
            status_code=404,
            detail="No investigation found for this night"
        )

    # Get investigated player
    target = (
        db.query(GamePlayer)
        .filter(
            GamePlayer.game_id == game_id,
            GamePlayer.user_id == investigation.target_id
        )
        .first()
    )

    if not target:
        raise HTTPException(
            status_code=404,
            detail="Investigated player not found"
        )

    return DetectiveResult(
        target_id=target.user_id,
        is_mafia=target.role == Roles.MAFIA
    )


# VOTING ENDPOINT
def cast_vote(game_id:str, db:Session, vote_data: ActionRequest, user_id:int):

    # 1. check for game
    game= db.query(Game).filter(Game.game_id==game_id).first()
    if not game:
        raise HTTPException(404, detail="Game not found")

    # 2. Check phase
    if game.current_phase != Phase.VOTING:
        raise HTTPException(
            status_code=400,
            detail="Voting is not currently active"
        )

      # 3. Check voter belongs to game
    voter = (
        db.query(GamePlayer)
        .filter(
            GamePlayer.game_id == game_id,
            GamePlayer.user_id == user_id
        )
        .first()
    )

    if not voter:
        raise HTTPException(
            status_code=403,
            detail="You are not part of this game"
        )

    # 4. Dead players cannot vote
    if not voter.is_alive:
        raise HTTPException(
            status_code=400,
            detail="Dead players cannot vote"
        )
    # 4. Check if the player has voted already

   

    # 5. Check target belongs to game
    target = (
        db.query(GamePlayer)
        .filter(
            GamePlayer.game_id == game_id,
            GamePlayer.user_id == vote_data.target_id
        )
        .first()
    )

    if not target:
        raise HTTPException(
            status_code=400,
            detail="Target player is not part of this game"
        )

    # 6. Cannot vote for a dead player
    if not target.is_alive:
        raise HTTPException(
            status_code=400,
            detail="Cannot vote for a dead player"
        )

    # 7. Prevent voting multiple times
    existing_vote = (
        db.query(GameAction)
        .filter(
            GameAction.game_id == game_id,
            GameAction.round_number == game.round_number,
            GameAction.phase == Phase.VOTING,
            GameAction.actor_id == user_id,
            GameAction.action_type == Action.VOTE,
            GameAction.voting_attempt == game.voting_attempt
        )
        .first()
    )
    if existing_vote:
            raise HTTPException(400, "You have voted already")

    # 8. Store vote
    vote = GameAction(
        game_id=game_id,
        round_number=game.round_number,
        phase=Phase.VOTING,
        actor_id=user_id,
        action_type=Action.VOTE,
        target_id=vote_data.target_id,
        voting_attempt=game.voting_attempt,
    )

    db.add(vote)
    db.commit()
    db.refresh(vote)

    return "Vote casted successfully "



# # Resolve Morning
# def resolve_morning(game_id: str, db: Session):

#     game = (
#         db.query(Game)
#         .filter(Game.game_id == game_id)
#         .first()
#     )

#     if not game:
#         raise HTTPException(
#             status_code=404,
#             detail="No game found"
#         )

#     if game.current_phase != Phase.MORNING:
#         raise HTTPException(
#             status_code=400,
#             detail="Game is not in the morning phase"
#         )

#     # Get all votes for this round
#     actions = (
#         db.query(GameAction)
#         .filter(
#             GameAction.game_id == game_id,
#             GameAction.round_number == game.round_number,
#             GameAction.phase == Phase.VOTING,
#             GameAction.action_type == Action.VOTE
#         )
#         .all()
#     )

#     if not actions:
#         raise HTTPException(
#             status_code=400,
#             detail="No votes have been cast"
#         )

#     # Count votes
#     vote_counts = {}

#     for action in actions:
#         vote_counts[action.target_id] = (
#             vote_counts.get(action.target_id, 0) + 1
#         )

#     max_votes = max(vote_counts.values())

#     top_targets = [
#         target_id
#         for target_id, count in vote_counts.items()
#         if count == max_votes
#     ]

#     # For now, first target wins in case of a tie
#     eliminated_player_id = top_targets[0]

#     # Find player in this game
#     player = (
#         db.query(GamePlayer)
#         .filter(
#             GamePlayer.game_id == game_id,
#             GamePlayer.user_id == eliminated_player_id
#         )
#         .first()
#     )

#     if not player:
#         raise HTTPException(
#             status_code=404,
#             detail="Eliminated player not found"
#         )

#     # Eliminate player
#     player.is_alive = False

#     # Check winner AFTER elimination
#     winner = check_win_condition(game_id, db)

#     if winner:

#         game.status = GameStatus.COMPLETED
#         game.current_phase = Phase.ENDED
#         game.winner = winner
#         game.ended_at = datetime.now()

#     else:

#         # Start next round
#         game.round_number += 1
#         game.current_phase = Phase.NIGHT

#     db.commit()

#     return {
#         "eliminated_player_id": eliminated_player_id,
#         "winner": winner
#     }

# Resolve Morning
def resolve_voting(game_id: str, db: Session):

    game = (
        db.query(Game)
        .filter(Game.game_id == game_id)
        .first()
    )

    if not game:
        raise HTTPException(
            status_code=404,
            detail="No game found"
        )

    if game.current_phase != Phase.VOTING:
        raise HTTPException(
            status_code=400,
            detail="Game is not in the morning phase"
        )

    # Get all votes for this round
    actions = (
        db.query(GameAction)
        .filter(
            GameAction.game_id == game_id,
            GameAction.round_number == game.round_number,
            GameAction.phase == Phase.VOTING,
            GameAction.action_type == Action.VOTE,
            GameAction.voting_attempt == game.voting_attempt,
        )
        .all()
    )

    if not actions:
        raise HTTPException(
            status_code=400,
            detail="No votes have been cast"
        )

    # Count votes
    vote_counts = {}

    for action in actions:
        vote_counts[action.target_id] = (
            vote_counts.get(action.target_id, 0) + 1
        )

    # Find maximum votes
    max_votes = max(vote_counts.values())

    # Find all players having maximum votes
    top_targets = [
        target_id
        for target_id, count in vote_counts.items()
        if count == max_votes
    ]

    # Tie: nobody is eliminated
    if len(top_targets) > 1:
        game.voting_attempt += 1
        db.commit()

        return {
            "eliminated_player_id": None,
            "winner": None,
            "message": "It is a tie. No player was eliminated. Vote again."
        }

    eliminated_player_id = top_targets[0]
    

    player = (
        db.query(GamePlayer)
        .filter(
            GamePlayer.game_id == game_id,
            GamePlayer.user_id == eliminated_player_id
        )
        .first()
    )

    if not player:
        raise HTTPException(
            status_code=404,
            detail="Eliminated player not found"
        )

    player.is_alive = False

    winner = check_win_condition(game_id, db)

    if winner:

        game.status = GameStatus.COMPLETED
        game.current_phase = Phase.ENDED
        game.winner = winner
        game.ended_at = datetime.now()

    else:

        # New game round
        game.round_number += 1

        # Reset voting attempts for the new round
        game.voting_attempt = 1

        game.current_phase = Phase.NIGHT
    db.commit()


    return {
        "eliminated_player_id": eliminated_player_id,
        "eliminated_player_role": player.role.value,
        "winner": winner,
        "message": f"Player {eliminated_player_id} was eliminated."
    }





def build_game_state_response(db: Session, game: Game, user: User) -> dict:
    """
    Builds the full current-state payload for a player re-syncing into an
    active game (called from GET /room/{room_code}/state when a Game exists).

    Visibility rules enforced here:
    - Every player's alive/dead status is public
    - A dead player's role is revealed to everyone
    - An alive player's role is hidden from everyone except themselves
    - The requester's own role is always included separately as `my_role`
    """

    requesting_player = db.query(GamePlayer).filter(
        GamePlayer.game_id == game.game_id,
        GamePlayer.user_id == user.id
    ).first()

    if not requesting_player:
        raise HTTPException(403, detail="You are not a participant in this game")

    all_players = db.query(GamePlayer).filter(
        GamePlayer.game_id == game.game_id
    ).all()

    players_public = []
    for p in all_players:
        user_row = db.query(User).filter(User.id == p.user_id).first()
        players_public.append({
            "user_id": p.user_id,
            "name": user_row.name if user_row else f"Player {p.user_id}",
            "is_alive": p.is_alive,
            # Role only visible once dead — same rule used in night/day resolution broadcasts
            "role": p.role.value if (not p.is_alive or game.status == GameStatus.COMPLETED or p.user_id == user.id) else None
        })

    # Has the requesting player already submitted an action for the CURRENT
    # phase/round? Used so the frontend doesn't re-show an action UI that's
    # already been completed (e.g. after a page refresh mid-night).
    my_action_this_round = None
    if game.current_phase in (Phase.NIGHT, Phase.VOTING):
        my_action_this_round = db.query(GameAction).filter(
            GameAction.game_id == game.game_id,
            GameAction.round_number == game.round_number,
            GameAction.phase == game.current_phase,
            GameAction.actor_id == user.id
        ).first()

    return {
        "status": "COMPLETED" if game.status == GameStatus.COMPLETED else "IN_PROGRESS",
        "game_id": game.game_id,
        "phase": game.current_phase.value,
        "round_number": game.round_number,
        "winner": game.winner.value if game.winner else None,
        "my_role": requesting_player.role.value,
        "my_is_alive": requesting_player.is_alive,
        "my_action_submitted": my_action_this_round is not None,
        "players": players_public
    }



def fetch_state(db: Session, room_code: str, user: User):
    room = db.query(Room).filter(Room.roomcode == room_code).first()
    if not room:
        raise HTTPException(404, detail="Room not found")

    # Confirm the requester is actually part of this room
    room_player = db.query(Room_Player).filter(
        Room_Player.room_id == room.room_id,
        Room_Player.user_id == user.id
    ).first()
    if not room_player:
        raise HTTPException(403, detail="You are not part of this room")

    game = db.query(Game).filter(Game.room_id == room.room_id).order_by(Game.started_at.desc()).first()

    if not game:
        # Game hasn't started yet — return lobby state
        all_room_players = db.query(Room_Player).filter(Room_Player.room_id == room.room_id).all()
        return {
            "status": "LOBBY",
            "room_code": room.roomcode,
            "host_id": room.host_id,
            "players": [rp.user_id for rp in all_room_players]
        }

    # Game exists — return full game state (your existing logic)
    return build_game_state_response(db, game, user)