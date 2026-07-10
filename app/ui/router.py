import os
from fastapi import APIRouter
from fastapi.responses import HTMLResponse, FileResponse

router = APIRouter(tags=["超天酱地雷系核心UI-v4.2"])

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _read_html(filename):
    """从 ui/ 目录读取 HTML 模板文件"""
    with open(os.path.join(_BASE_DIR, filename), "r", encoding="utf-8") as f:
        return f.read()


@router.get("/img/tu.jpg")
async def get_local_avatar():
    avatar_path = r"E:\OpenMonitor\img\tu.jpg"
    if os.path.exists(avatar_path):
        return FileResponse(avatar_path)
    return FileResponse(avatar_path)


@router.get("/img/logo.png")
async def get_favicon():
    logo_path = r"E:\OpenMonitor\img\logo.png"
    return FileResponse(logo_path, media_type="image/png")


@router.get("/audio/no.mp3")
async def get_no_signal_audio():
    audio_path = r"E:\OpenMonitor\audio\no.mp3"
    return FileResponse(audio_path, media_type="audio/mpeg")


@router.get("/audio/admin.mp3")
async def get_admin_audio():
    audio_path = r"E:\OpenMonitor\audio\adimin.mp3"
    return FileResponse(audio_path, media_type="audio/mpeg")


@router.get("/audio/end.mp3")
async def get_end_audio():
    audio_path = r"E:\OpenMonitor\audio\end.mp3"
    return FileResponse(audio_path, media_type="audio/mpeg")


@router.get("/", response_class=HTMLResponse)
async def index():
    """主监护页面（超天酱地雷系风格）"""
    return _read_html("index.html")


@router.get("/admin", response_class=HTMLResponse)
async def admin_page():
    """患者档案管理后台（仅在此页面可修改档案信息）"""
    return _read_html("admin.html")


@router.get("/easter", response_class=HTMLResponse)
async def easter_egg():
    """彩蛋页：末音专属 — the end"""
    return _read_html("easter.html")