from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime
from app.database.database import get_db
from app.models.device import Device

router = APIRouter(prefix="/device", tags=["监护设备"])

class DeviceRegister(BaseModel):
    sn: str
    ip_addr: str = ""

@router.get("/list")
def list_devices(db: Session = Depends(get_db)):
    devs = db.query(Device).all()
    return [
        {
            "sn": d.sn,
            "ip": d.ip_addr,
            "online": d.online,
            "last_active": d.last_active.strftime("%Y-%m-%d %H:%M:%S") if d.last_active else "",
            "create_time": d.create_time.strftime("%Y-%m-%d %H:%M:%S") if d.create_time else "",
        }
        for d in devs
    ]

@router.post("/register")
def register_device(payload: DeviceRegister, db: Session = Depends(get_db)):
    d = db.query(Device).filter(Device.sn == payload.sn).first()
    if not d:
        d = Device(sn=payload.sn, ip_addr=payload.ip_addr, online=False,
                   last_active=datetime.now(), create_time=datetime.now())
        db.add(d)
    else:
        d.ip_addr = payload.ip_addr
        d.last_active = datetime.now()
    db.commit()
    return {"ok": True, "msg": "设备已登记"}

@router.delete("/delete")
def delete_device(sn: str = Query(...), db: Session = Depends(get_db)):
    d = db.query(Device).filter(Device.sn == sn).first()
    if not d:
        return {"ok": False, "msg": "未找到设备"}
    db.delete(d)
    db.commit()
    return {"ok": True, "msg": "设备已删除"}