import os
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from app.database.database import Base, engine
from app.api import vital_api, device_api
from app.ui.router import router as ui_router
from app.websocket.manager import ws_manager
from app.hl7.mllp_server import MLLP_SERVER
from app.models.vital import Vital
from app.models.alert import Alert
from app.models.device import Device
from app.models.patient import Patient

# ========================================================
# 1. 初始化本地 SQLite 数据库表结构
# ========================================================
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="OpenMonitor Pro 🖤🎀",
    description="地雷系高精度医疗级双栈实时采集核心后台",
)

# ========================================================
# 2. CORS
# ========================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========================================================
# 3. 路由注册
# ========================================================
app.include_router(vital_api.router)
app.include_router(device_api.router)
app.include_router(ui_router)


# ========================================================
# 4. WebSocket
# ========================================================
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)


# ========================================================
# 5. 异步生命周期管理（MLLP）
# ========================================================
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(MLLP_SERVER.start_server())


# ========================================================
# 6. 本地直接调试入口
# ========================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)