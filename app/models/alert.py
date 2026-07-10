from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime
from app.database.database import Base

class Alert(Base):
    __tablename__ = "alert"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String, index=True, comment="监护仪设备编号")
    alarm_text = Column(String, comment="报警详情")
    created = Column(DateTime, default=datetime.now, index=True)