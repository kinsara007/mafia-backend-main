from enum import Enum

class RoomStatus(str, Enum):
    WAITING = "WAITING"
    IN_PROGRESS = "IN_PROGRESS"
    FINISHED = "FINISHED"

class GameStatus(str, Enum):
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"

class Phase(str, Enum):
    NIGHT = "NIGHT"
    MORNING = "MORNING"
    VOTING = "VOTING"
    ENDED = "ENDED"
    DAY_DISCUSSION="DAY_DISCUSSION"

class Roles(str, Enum):
    MAFIA= "MAFIA"
    VILLAGER= "VILLAGER"
    DOCTOR= "DOCTOR"
    DETECTIVE= "DETECTIVE"

class Winner(str, Enum):
    MAFIA = "MAFIA"
    VILLAGERS = "VILLAGERS"

class Action(str, Enum):
    KILL= "KILL"
    INVESTIGATE= "INVESTIGATE"
    PROTECT= "PROTECT"
    VOTE= "VOTE"

# Client timers and server phase timeouts must stay in sync.
NIGHT_DURATION_SECONDS = 180
DISCUSSION_DURATION_SECONDS = 180
VOTING_DURATION_SECONDS = 180