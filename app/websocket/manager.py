from fastapi import WebSocket
from typing import List, Dict, Any

class WebSocketManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: Dict[str, Any]):
        # 推送给所有网页前端
        for conn in self.active_connections:
            try:
                await conn.send_json(message)
            except Exception:
                self.disconnect(conn)

ws_manager = WebSocketManager()