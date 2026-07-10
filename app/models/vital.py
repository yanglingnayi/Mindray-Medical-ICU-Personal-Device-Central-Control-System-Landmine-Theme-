from sqlalchemy import Column, Integer, Float, DateTime, String
from datetime import datetime
from app.database.database import Base

class Vital(Base):
    __tablename__ = "vital"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String, index=True, comment="监护仪设备编号")
    patient_name = Column(String, comment="患者姓名")
    hr = Column(Integer, comment="心率")
    spo2 = Column(Integer, comment="血氧")
    rr = Column(Integer, comment="呼吸频率")
    temp = Column(Float, comment="体温")
    sys = Column(Integer, comment="收缩压")
    dia = Column(Integer, comment="舒张压")
    map = Column(Integer, comment="平均动脉压")
    created = Column(DateTime, default=datetime.now, index=True)