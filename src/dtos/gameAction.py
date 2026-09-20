from pydantic import BaseModel
from src.utils.constant import Action, Winner, Phase


class ActionRequest(BaseModel):
    target_id: int
    action_type: Action


class DetectiveResult(BaseModel):
    target_id: int
    is_mafia: bool


class NightActionResponse(BaseModel):
    killed_player_id: int | None
    winner: Winner | None
    detective_result: DetectiveResult | None
    phase: Phase | None
    round_number: int = 1
