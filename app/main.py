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
# 1. 初始化本地 SQLite 数据库表结构（确保所有模型已被 SQLAlchemy 注册）
# ========================================================
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="OpenMonitor Pro 🖤🎀", 
    description="地雷系高精度医疗级双栈实时采集核心后台"
)

# ========================================================
# 2. 核心解药：彻底放行跨域，解决公网 IPv6 访问时 WebSocket 报 403 的 Bug
# ========================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源（全面兼容局域网IPv4与外网公网IPv6环境）
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========================================================
# 3. 注册模块化路由（包含数字化API与地雷系UI静态映射）
# ========================================================
app.include_router(vital_api.router)
app.include_router(device_api.router)
app.include_router(ui_router)  # 引入我们在 router.py 里死定 E:\OpenMonitor\img\tu.jpg 的前端页面

# ========================================================
# 4. WebSocket 高性能数据双向推流实时全透传通道
# ========================================================
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    接收前端控制台的 WebSocket 握手请求
    并将来自 MLLP 引擎解析到的迈瑞监护仪体征及原始日志源源不断地推向前端
    """
    await ws_manager.connect(websocket)
    try:
        while True:
            # 维持网络双栈心跳连接，静默接收前端可能发来的校准指令
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)

# ========================================================
# 5. 异步生命周期管理：随主服务一同拉起 MLLP 2575 采集引擎
# ========================================================
@app.on_event("startup")
async def startup_event():
    """
    在 FastAPI 启动时，利用 asyncio.create_task 将 MLLP 服务挂到后台运行
    这样既保证 2575 端口能洗入迈瑞 HL7 报文，又不会阻塞 8000 端口的前端网页渲染
    """
    asyncio.create_task(MLLP_SERVER.start_server())

# ========================================================
# 6. 本地直接调试入口（如果通过 python main.py 启动）
# ========================================================
if __name__ == "__main__":
    import uvicorn
    # 绑定 0.0.0.0 确保无论本地环回还是网卡物理 IPv4/IPv6 均能无死角监听
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)