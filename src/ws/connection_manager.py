from fastapi import WebSocket

class ConnectionManager:
    def __init__(self):
        # room_id -> {user_id: WebSocket}
        self.active_connections: dict[str, dict[str, WebSocket]] = {}

    # first wait for websocket to accept the req, then add it to the connections dictionary
    async def connect(self, room_id:str, user_id:int, websocket:WebSocket):
        await websocket.accept()
        room = self.active_connections.setdefault(room_id, {})
        previous = room.get(user_id)
        if previous is not None and previous is not websocket:
            try:
                await previous.close(code=4000)
            except Exception:
                pass
        room[user_id] = websocket

    # while disconnecting, remove the connection from the connections dictionary
    def disconnect(self, room_id:str, user_id:int):
        if room_id in self.active_connections:
            self.active_connections[room_id].pop(user_id, None)

    #sending any message to the player: get the connection and then call send_json
    async def send_to_player(self, room_id:str, user_id:int, message:dict):
        ws= self.active_connections.get(room_id,{}).get(user_id)
        if not ws:
            return
        try:
            await ws.send_json(message)
        except Exception:
            self.disconnect(room_id, user_id)

    async def broadcast_to_room(self, room_id: str, message: dict, exclude: set[str] = None):
        exclude = exclude or set()
        dead = []
        for uid, ws in list(self.active_connections.get(room_id, {}).items()):
            if uid in exclude:
                continue
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(uid)
        for uid in dead:
            self.disconnect(room_id, uid)



manager = ConnectionManager()




# What happens when Alice joins?

# Alice opens:

# /ws/rooms/123

# FastAPI accepts the connection:

# await websocket.accept()

# Then:

# manager.active_connections["123"]["alice"] = alice_websocket

# Now FastAPI knows:

# Room 123
#     Alice → Alice's WebSocket

# Bob joins:

# Room 123
#     Alice → Alice's WebSocket
#     Bob   → Bob's WebSocket

# And so on.