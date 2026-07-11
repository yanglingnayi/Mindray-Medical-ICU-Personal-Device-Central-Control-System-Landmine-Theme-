from sqlalchemy import Column, Integer, String, DateTime, Text
from datetime import datetime
from app.database.database import Base

class Patient(Base):
    __tablename__ = "patient"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String, unique=True, index=True, comment="监护仪设备编号（作为关联 key）")
    patient_name = Column(String, comment="患者姓名")
    gender = Column(String, comment="性别：男/女")
    age = Column(Integer, comment="年龄")
    department = Column(String, comment="科室：ICU/内科/外科等")
    hospital = Column(String, comment="医院名称")
    bed_id = Column(String, comment="床位号")
    id_card = Column(String, comment="身份证号")
    phone = Column(String, comment="联系电话")
    diagnosis = Column(String, comment="初步诊断/主诉")
    admission_time = Column(String, comment="入院时间")
    doctor = Column(String, comment="主管医生")
    note = Column(String, comment="备注")
    photo = Column(Text, comment="患者头像（base64 Data URI，用于前端直接渲染）")
    created = Column(DateTime, default=datetime.now, comment="档案创建时间")
    updated = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="档案更新时间")