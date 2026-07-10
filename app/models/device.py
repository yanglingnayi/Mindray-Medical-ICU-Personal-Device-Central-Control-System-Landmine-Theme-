from sqlalchemy import Column, Integer, String, DateTime, Boolean
from datetime import datetime
from app.database.database import Base

class Device(Base):
    __tablename__ = "device"
    id = Column(Integer, primary_key=True)
    sn = Column(String, unique=True, index=True, comment="设备SN")
    ip_addr = Column(String, comment="设备接入IP")
    online = Column(Boolean, default=False)
    last_active = Column(DateTime, default=datetime.now)
    create_time = Column(DateTime, default=datetime.now)