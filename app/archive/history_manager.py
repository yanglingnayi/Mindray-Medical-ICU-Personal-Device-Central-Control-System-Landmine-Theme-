"""
监护仪历史数据档案管理器
===========================

独立模块，用于调取、检索、分析监护仪传回的历史数据。

核心功能：
    - 按设备/时间范围查询生命体征历史数据
    - 按设备/类型/级别查询报警历史
    - 生成统计分析报告（平均值、峰值、越限次数等）
    - 导出数据为 CSV/JSON
    - 生成可视化趋势图（matplotlib）
    - 设备在线状态追踪
    - 交互式命令行模式

运行方式：
    python -m app.archive.history_manager
"""

import os
import sys
import json
import csv
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field, asdict
from collections import defaultdict


# ====================================================================
# 数据库相关导入（优雅降级）
# ====================================================================
try:
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker, Session
    _SQLALCHEMY_AVAILABLE = True
except ImportError:
    _SQLALCHEMY_AVAILABLE = False

# 尝试读取项目配置
_DEFAULT_DB_PATH = ""
try:
    from app.config import config as _config
    if hasattr(_config, "DATABASE"):
        _DEFAULT_DB_PATH = _config.DATABASE
except Exception:
    pass


# ====================================================================
# 可视化库（可选）
# ====================================================================
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    _MATPLOTLIB_AVAILABLE = True
    # 中文字体支持
    from matplotlib import rcParams
    rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    rcParams["axes.unicode_minus"] = False
except ImportError:
    _MATPLOTLIB_AVAILABLE = False


# ====================================================================
# 数据结构定义
# ====================================================================

@dataclass
class VitalRecord:
    """单条生命体征记录"""
    id: int = 0
    device_id: str = ""
    patient_name: str = ""
    department: str = ""
    bed_id: str = ""
    doctor: str = ""
    diagnosis: str = ""
    admission_diagnosis: str = ""
    timestamp: str = ""
    hr: float = 0.0
    spo2: float = 0.0
    rr: float = 0.0
    temp: float = 0.0
    sys: float = 0.0
    dia: float = 0.0
    map: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "device_id": self.device_id,
            "patient_name": self.patient_name, "department": self.department,
            "bed_id": self.bed_id, "doctor": self.doctor,
            "diagnosis": self.diagnosis,
            "admission_diagnosis": self.admission_diagnosis,
            "timestamp": self.timestamp,
            "hr": self.hr, "spo2": self.spo2, "rr": self.rr, "temp": self.temp,
            "sys": self.sys, "dia": self.dia, "map": self.map,
        }


# 生命体征正常范围（用于越限判断）
VITAL_NORMALS: Dict[str, Tuple[float, float]] = {
    "hr": (60.0, 100.0),
    "spo2": (95.0, 100.0),
    "rr": (12.0, 20.0),
    "temp": (36.0, 37.5),
    "sys": (90.0, 140.0),
    "dia": (60.0, 90.0),
    "map": (70.0, 105.0),
}


def check_abnormal(param: str, value: float) -> str:
    """判断参数是否越限，返回 'high'/'low'/''"""
    if not value or value <= 0:
        return ""
    if param not in VITAL_NORMALS:
        return ""
    low, high = VITAL_NORMALS[param]
    if value > high:
        return "high"
    if value < low:
        return "low"
    return ""


@dataclass
class AlarmRecord:
    """单条报警记录"""
    id: int = 0
    device_id: str = ""
    alarm_text: str = ""
    alarm_parsed: str = ""
    mdc_code: str = ""
    mdc_name: str = ""
    param_name: str = ""
    severity: str = ""
    timestamp: str = ""
    alarm_level: str = ""
    alarm_category: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "device_id": self.device_id,
            "alarm_text": self.alarm_text, "alarm_parsed": self.alarm_parsed,
            "mdc_code": self.mdc_code, "mdc_name": self.mdc_name,
            "param_name": self.param_name, "severity": self.severity,
            "timestamp": self.timestamp,
            "alarm_level": self.alarm_level, "alarm_category": self.alarm_category,
        }


@dataclass
class DeviceRecord:
    """设备信息"""
    sn: str = ""
    ip_addr: str = ""
    online: bool = False
    last_active: str = ""
    create_time: str = ""
    vital_count: int = 0
    alarm_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sn": self.sn, "ip_addr": self.ip_addr, "online": self.online,
            "last_active": self.last_active, "create_time": self.create_time,
            "vital_count": self.vital_count, "alarm_count": self.alarm_count,
        }


@dataclass
class StatisticsReport:
    """统计分析报告"""
    device_id: str = ""
    time_range: str = ""
    total_records: int = 0
    total_alarms: int = 0
    parameter_stats: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    alarm_summary: Dict[str, int] = field(default_factory=dict)
    generated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "device_id": self.device_id, "time_range": self.time_range,
            "total_records": self.total_records, "total_alarms": self.total_alarms,
            "parameter_stats": self.parameter_stats,
            "alarm_summary": self.alarm_summary,
            "generated_at": self.generated_at,
        }


# ====================================================================
# 辅助函数
# ====================================================================

def _safe_float(val) -> float:
    """安全转换为浮点数"""
    try:
        if val is None or val == "":
            return 0.0
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def _parse_datetime(dt_str: str) -> Optional[datetime]:
    """解析日期时间字符串"""
    if not dt_str:
        return None
    formats = [
        "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
        "%Y/%m/%d %H:%M:%S.%f", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y/%m/%d",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(str(dt_str).strip(), fmt)
        except ValueError:
            continue
    return None


def _classify_alarm(alarm_text: str) -> Tuple[str, str, str, str, str, str]:
    """解析原始报警文本
    返回: (level, category, parsed_text, mdc_code, mdc_name, param_name)
    """
    text = str(alarm_text or "").strip()
    raw = text
    parsed = raw
    mdc_code = ""
    mdc_name = ""
    param_name = ""

    # 尝试用项目中已有的 mindray_alarm 模块解析
    try:
        from app.mindray_alarm import parse as _parse_alarm
        from app.mindray_alarm.codes import MDC_CODE_MAP
        import re
        m = re.search(r"(\d{5,6})", text)
        if m:
            mdc_code = m.group(1)
            if mdc_code in MDC_CODE_MAP:
                mdc_name = str(MDC_CODE_MAP[mdc_code].get("name", ""))
                param_name = str(MDC_CODE_MAP[mdc_code].get("param", ""))
    except Exception:
        pass

    # 精确匹配 MDC 编码：提取 ^...^ 中间的代码段，避免 VF/VT 等子串匹配造成误判
    code_tokens = set()
    if "^" in text:
        for part in text.split("^"):
            p = part.strip()
            if p:
                code_tokens.add(p)
                # 提取 MDC_EVT_ 或 MNDRY_EVT_ 后部分
                if p.startswith("MDC_EVT_"):
                    code_tokens.add(p[8:])
                if p.startswith("MNDRY_EVT_"):
                    code_tokens.add(p[10:])

    if "MDC_EVT_ALARM" in text:
        import re
        m = re.search(r"(\d{5,6})", text)
        if m:
            mdc_code = m.group(1)

        # 根据精确编码 token 判断报警内容
        if "MDC_EVT_STAT_OFF" in code_tokens or "STAT_OFF" in code_tokens:
            parsed = "报警停止/解除"
        elif "MDC_EVT_HI_VAL_GT_LIM" in code_tokens or "HI_VAL_GT_LIM" in code_tokens:
            parsed = "参数数值超出上限"
            param_name = param_name or "生命体征参数"
        elif "MDC_EVT_LO_VAL_LT_LIM" in code_tokens or "LO_VAL_LT_LIM" in code_tokens:
            parsed = "参数数值低于下限"
            param_name = param_name or "生命体征参数"
        elif "MDC_EVT_ALM_START" in code_tokens or "ALM_START" in code_tokens:
            parsed = "报警激活"
        elif "MDC_EVT_ALM_TECH" in code_tokens or "ALM_TECH" in code_tokens:
            parsed = "技术类报警"
        elif "MDC_EVT_VF" in code_tokens or "ECG_VF" in code_tokens:
            parsed = "室颤"
        elif "MDC_EVT_VT" in code_tokens or "ECG_VT" in code_tokens:
            parsed = "室速"
        elif "MDC_EVT_ASYSTOLE" in code_tokens or "ASYSTOLE" in code_tokens:
            parsed = "停搏/心搏停止"
        elif "MDC_EVT_BRADY" in code_tokens or "ECG_BRADY" in code_tokens:
            parsed = "心动过缓"
        elif "MDC_EVT_TACHY" in code_tokens or "ECG_TACHY" in code_tokens:
            parsed = "心动过速"
        elif "MDC_EVT_PVC" in code_tokens or "PVC" in code_tokens:
            parsed = "室性早搏"
        elif "MDC_EVT_APNEA" in code_tokens or "APNEA" in code_tokens:
            parsed = "窒息"
        elif "MDC_EVT_LEAD_OFF" in code_tokens or "LEAD_OFF" in code_tokens:
            parsed = "导联脱落"
        elif "MDC_EVT_NOISY" in code_tokens or "NOISY" in code_tokens:
            parsed = "信号干扰"
        elif "MDC_EVT_ECG_AFIB" in code_tokens or "MNDRY_EVT_ECG_AFIB" in code_tokens or "ECG_AFIB" in code_tokens:
            parsed = "房颤"
        elif "MDC_EVT_ECG_CARD_BEAT_RATE_IRREG" in code_tokens or "CARD_BEAT_RATE_IRREG" in code_tokens:
            parsed = "心率不齐"
        elif "MNDRY_EVT_SEARCHING_PULSE" in code_tokens or "SEARCHING_PULSE" in code_tokens:
            parsed = "搜索脉搏"
        elif "MNDRY_EVT_SPO2_NO_PLUSE" in code_tokens or "SPO2_NO_PLUSE" in code_tokens or "SPO2_NO_PULSE" in code_tokens:
            parsed = "无脉搏信号"
        elif "MNDRY_EVT_POOR_CONTACT" in code_tokens or "POOR_CONTACT" in code_tokens:
            parsed = "电极接触不良"
        elif "SPO2_LOW_PERFUSION" in code_tokens:
            parsed = "低灌注（血氧）"
        elif "MNDRY_EVT_NIBP_LOSE_CUFF" in code_tokens or "NIBP_LOSE_CUFF" in code_tokens:
            parsed = "袖带脱落"
        elif mdc_name:
            parsed = mdc_name
        else:
            parsed = "报警事件"
        if mdc_name and mdc_name != parsed:
            parsed = "{} ({})".format(parsed, mdc_name)

    # 如果上面没匹配到，尝试关键词分类
    if parsed == raw:
        # 纯中文/其他格式的报警文本直接使用
        if any(k in text for k in ["过高", "过低", "越限"]):
            parsed = text.strip()
        elif any(k in text for k in ["停搏", "停博"]):
            parsed = "停搏"
        elif any(k in text for k in ["房颤", "房顫"]):
            parsed = "房颤"
        elif any(k in text for k in ["室颤", "室顫"]):
            parsed = "室颤"
        elif any(k in text for k in ["停止", "解除", "关闭"]):
            parsed = "报警解除"
        elif any(k in text for k in ["上限", "越上限", "超高"]):
            parsed = "参数越上限"
        elif any(k in text for k in ["下限", "越下限", "超低"]):
            parsed = "参数越下限"
        elif text.strip():
            parsed = text.strip()

    # 级别/分类判断
    level, category = _alarm_level(parsed, text)

    return (level, category, parsed, mdc_code, mdc_name, param_name)


def _alarm_level(parsed: str, raw: str) -> Tuple[str, str]:
    """根据解析后的内容判断报警级别和分类"""
    combined = "{} {}".format(parsed, raw).lower()
    red_keywords = ["停搏", "室颤", "室速", "vf", "vt", "asystole",
                   "st段抬高", "st_elevation", "qt延长", "窒息", "apnea",
                   "无脉", "休克", "心搏停止", "torsade"]
    tech_keywords = ["脱落", "off", "故障", "fault", "通信", "中断",
                    "探头", "电极", "袖带", "电池", "自检", "连接", "lost",
                    "设备", "离线", "paper", "纸张", "导联", "lead"]
    arr_keywords = ["早搏", "pvc", "pac", "房颤", "af", "心动过缓", "心动过速",
                   "二联律", "三联律", "心律失常", "r-on-t", "扑动", "brady", "tachy"]
    yellow_keywords = ["越上限", "越下限", "上限", "下限", "high", "low", "超出"]

    if any(k in combined for k in red_keywords):
        return ("🔴红色(高危)", "arrhythmia")
    if any(k in combined for k in tech_keywords):
        return ("🟡黄色(中危)", "technical")
    if any(k in combined for k in arr_keywords):
        return ("🟡黄色(中危)", "arrhythmia")
    if any(k in combined for k in yellow_keywords):
        return ("🟡黄色(中危)", "physiological")
    if "解除" in combined or "stop" in combined:
        return ("⚪白色(提示)", "physiological")
    return ("🟡黄色(中危)", "physiological")


# ====================================================================
# 历史档案管理器核心类
# ====================================================================



# ====================================================================
# 自动诊断分析：根据生命体征数据智能分析每条记录
# ====================================================================

def auto_diagnose(hr, spo2, rr, temp, sys_bp, dia_bp, map_val):
    """
    根据单条生命体征数据自动分析病情。
    返回中文诊断文本，例如"正常"、"心动过缓"、"发热+低血氧"
    """
    findings = []

    if hr and hr > 0:
        if hr < 50:
            findings.append("心动过缓")
        elif hr < 60:
            findings.append("窦性心动过缓")
        elif hr > 140:
            findings.append("心动过速(危)")
        elif hr > 100:
            findings.append("窦性心动过速")

    if spo2 and spo2 > 0:
        if spo2 < 85:
            findings.append("严重低血氧(危)")
        elif spo2 < 90:
            findings.append("低血氧")
        elif spo2 < 95:
            findings.append("血氧偏低")

    if rr and rr > 0:
        if rr > 30:
            findings.append("呼吸急促(危)")
        elif rr > 20:
            findings.append("呼吸偏快")
        elif rr < 10:
            findings.append("呼吸过缓")

    if temp and temp > 0:
        if temp >= 39.0:
            findings.append("高热(危)")
        elif temp >= 37.5:
            findings.append("发热")
        elif temp < 36.0:
            findings.append("低体温")

    if sys_bp and sys_bp > 0:
        if sys_bp >= 180:
            findings.append("高血压危象(危)")
        elif sys_bp >= 160:
            findings.append("2级高血压")
        elif sys_bp >= 140:
            findings.append("1级高血压")
        elif sys_bp < 90:
            findings.append("低血压")
    elif dia_bp and dia_bp > 0:
        if dia_bp >= 110:
            findings.append("舒张压偏高")
        elif dia_bp < 60:
            findings.append("舒张压偏低")

    if not findings:
        return "正常"

    result = "，".join(findings[:3])
    if len(findings) > 3:
        result += " 等"
    return result



class HistoryArchiveManager:
    """监护仪历史数据档案管理器"""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or self._detect_db_path()
        self.engine = None
        self.SessionLocal = None
        self._initialize_engine()
        self._cache: Dict[str, Any] = {}

    def _detect_db_path(self) -> str:
        """自动检测数据库路径"""
        if _DEFAULT_DB_PATH:
            # 如果是绝对路径直接用
            if os.path.isabs(_DEFAULT_DB_PATH) or os.path.exists(_DEFAULT_DB_PATH):
                return _DEFAULT_DB_PATH
            # 相对路径则以项目根为基准
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            project_root = os.path.dirname(project_root)  # 再上一级
            candidate = os.path.join(project_root, _DEFAULT_DB_PATH)
            if os.path.exists(candidate):
                return candidate

        # 自动查找当前项目下的 .db 文件
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        project_root = os.path.dirname(project_root)  # 到 OpenMonitor 根目录
        for root, dirs, files in os.walk(project_root):
            for f in files:
                if f.endswith(".db"):
                    return os.path.join(root, f)

        # 默认兜底
        default_dir = os.path.join(project_root, "data")
        os.makedirs(default_dir, exist_ok=True)
        return os.path.join(default_dir, "monitor_data.db")

    def _initialize_engine(self):
        """初始化数据库引擎"""
        if not _SQLALCHEMY_AVAILABLE:
            print("⚠️  SQLAlchemy 未安装，数据库功能受限")
            print("   请执行: pip install sqlalchemy")
            return
        try:
            db_url = f"sqlite:///{os.path.abspath(self.db_path)}"
            self.engine = create_engine(db_url, connect_args={"check_same_thread": False}, pool_pre_ping=True)
            self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        except Exception as e:
            print(f"⚠️  数据库初始化失败: {e}")

    def _get_session(self) -> Optional[Session]:
        """获取数据库会话"""
        if self.SessionLocal is None:
            return None
        return self.SessionLocal()

    # ================================================================
    # 数据库状态检查
    # ================================================================

    def get_database_info(self) -> Dict[str, Any]:
        """获取数据库基本信息"""
        info = {
            "db_path": self.db_path,
            "db_exists": os.path.exists(self.db_path),
            "db_size_mb": 0,
            "tables": {},
            "status": "ready" if self.engine else "unavailable",
        }
        try:
            if os.path.exists(self.db_path):
                info["db_size_mb"] = round(os.path.getsize(self.db_path) / (1024 * 1024), 2)
        except Exception:
            pass

        session = self._get_session()
        if session is None:
            return info

        try:
            for table_name in ["vital", "alert", "device", "patient"]:
                try:
                    result = session.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                    count = result.scalar() or 0
                    info["tables"][table_name] = int(count)
                except Exception:
                    info["tables"][table_name] = 0

            for table_name, time_col in [("vital", "created"), ("alert", "created")]:
                if info["tables"].get(table_name, 0) > 0:
                    try:
                        min_r = session.execute(text(f"SELECT MIN({time_col}) FROM {table_name}")).scalar()
                        max_r = session.execute(text(f"SELECT MAX({time_col}) FROM {table_name}")).scalar()
                        info[f"{table_name}_range"] = {"from": str(min_r or "-"), "to": str(max_r or "-")}
                    except Exception:
                        pass
        finally:
            session.close()

        return info

    # ================================================================
    # 设备管理
    # ================================================================

    def list_devices(self, include_stats: bool = True) -> List[DeviceRecord]:
        """列出所有接入的监护设备"""
        session = self._get_session()
        if session is None:
            return []
        devices = []
        try:
            try:
                result = session.execute(text(
                    "SELECT sn, ip_addr, online, last_active, create_time FROM device ORDER BY create_time DESC"
                ))
                device_rows = result.fetchall()
            except Exception:
                device_rows = []

            for row in device_rows:
                dev = DeviceRecord(
                    sn=str(row[0]) if row[0] else "",
                    ip_addr=str(row[1]) if row[1] else "",
                    online=bool(row[2]) if row[2] is not None else False,
                    last_active=str(row[3]) if row[3] else "",
                    create_time=str(row[4]) if row[4] else "",
                )
                if include_stats and dev.sn:
                    try:
                        v_count = session.execute(text(
                            "SELECT COUNT(*) FROM vital WHERE device_id = :sn"
                        ), {"sn": dev.sn}).scalar() or 0
                        a_count = session.execute(text(
                            "SELECT COUNT(*) FROM alert WHERE device_id = :sn"
                        ), {"sn": dev.sn}).scalar() or 0
                        dev.vital_count = int(v_count)
                        dev.alarm_count = int(a_count)
                    except Exception:
                        pass
                devices.append(dev)
        finally:
            session.close()
        return devices

    def get_device_info(self, device_sn: str) -> Optional[DeviceRecord]:
        """获取单个设备的详细信息"""
        for dev in self.list_devices(include_stats=True):
            if dev.sn == device_sn:
                return dev
        return None

    # ================================================================
    # 生命体征数据查询
    # ================================================================

    def query_vitals(
        self, device_id: Optional[str] = None,
        start_time: Optional[str] = None, end_time: Optional[str] = None,
        patient_name: Optional[str] = None,
        limit: int = 0, offset: int = 0, order: str = "desc",
    ) -> List[VitalRecord]:
        """查询生命体征历史数据（含患者信息JOIN）"""
        session = self._get_session()
        if session is None:
            return []
        records = []
        try:
            # 检查是否有 patient 表
            has_patient = False
            try:
                r = session.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='patient'"))
                has_patient = r.scalar() is not None
            except Exception:
                has_patient = False

            conditions = []
            params = {}
            if device_id:
                conditions.append("v.device_id = :device_id")
                params["device_id"] = device_id
            if start_time:
                conditions.append("v.created >= :start_time")
                params["start_time"] = start_time
            if end_time:
                conditions.append("v.created <= :end_time")
                params["end_time"] = end_time
            if patient_name:
                conditions.append("v.patient_name LIKE :patient_name")
                params["patient_name"] = f"%{patient_name}%"

            where = "WHERE " + " AND ".join(conditions) if conditions else ""
            order_by = f"ORDER BY v.created {order.upper()}" if order.upper() in ["ASC", "DESC"] else "ORDER BY v.created DESC"
            lim = f"LIMIT {limit}" if limit > 0 else ""
            off = f"OFFSET {offset}" if offset > 0 and limit > 0 else ""

            if has_patient:
                sql = (
                    "SELECT v.id, v.device_id, v.patient_name, v.created, v.hr, v.spo2, v.rr, v.temp, v.sys, v.dia, v.map, "
                    "COALESCE(p.department, ''), COALESCE(p.bed_id, ''), COALESCE(p.doctor, ''), COALESCE(p.diagnosis, '') "
                    "FROM vital v "
                    "LEFT JOIN patient p ON v.device_id = p.device_id "
                    f"{where} {order_by} {lim} {off}"
                )
                result = session.execute(text(sql), params)
                rows = result.fetchall()

                for row in rows:
                    _adm_diag = str(row[14]) if row[14] else ""
                    rec = VitalRecord(
                        id=int(row[0]) if row[0] else 0,
                        device_id=str(row[1]) if row[1] else "",
                        patient_name=str(row[2]) if row[2] else "",
                        timestamp=str(row[3]) if row[3] else "",
                        hr=_safe_float(row[4]), spo2=_safe_float(row[5]),
                        rr=_safe_float(row[6]), temp=_safe_float(row[7]),
                        sys=_safe_float(row[8]), dia=_safe_float(row[9]),
                        map=_safe_float(row[10]),
                        department=str(row[11]) if row[11] else "",
                        bed_id=str(row[12]) if row[12] else "",
                        doctor=str(row[13]) if row[13] else "",
                        admission_diagnosis=_adm_diag,
                    )
                    records.append(rec)
            else:
                sql = (
                    "SELECT id, device_id, patient_name, created, hr, spo2, rr, temp, sys, dia, map "
                    f"FROM vital v {where} {order_by} {lim} {off}"
                )
                result = session.execute(text(sql), params)
                rows = result.fetchall()
                for row in rows:
                    rec = VitalRecord(
                        id=int(row[0]) if row[0] else 0,
                        device_id=str(row[1]) if row[1] else "",
                        patient_name=str(row[2]) if row[2] else "",
                        timestamp=str(row[3]) if row[3] else "",
                        hr=_safe_float(row[4]), spo2=_safe_float(row[5]),
                        rr=_safe_float(row[6]), temp=_safe_float(row[7]),
                        sys=_safe_float(row[8]), dia=_safe_float(row[9]),
                        map=_safe_float(row[10]),
                    )
                    records.append(rec)

            # ====================================================================
            # 关联匹配：根据时间窗口，为每条 vital 记录匹配监护仪报警事件
            # ====================================================================
            if records:
                device_ids = {r.device_id for r in records if r.device_id}
                timestamps = [r.timestamp for r in records if r.timestamp]
                if device_ids and timestamps:
                    min_ts = min(timestamps)
                    max_ts = max(timestamps)

                    try:
                        alert_conditions = []
                        alert_params = {}
                        alert_conditions.append("device_id IN ({})".format(
                            ", ".join([f":dev_{i}" for i in range(len(device_ids))])
                        ))
                        for i, d in enumerate(device_ids):
                            alert_params[f"dev_{i}"] = d
                        alert_conditions.append("created >= :a_min")
                        alert_conditions.append("created <= :a_max")
                        alert_params["a_min"] = min_ts
                        alert_params["a_max"] = max_ts

                        alert_sql = (
                            "SELECT device_id, created, alarm_text "
                            "FROM alert WHERE {} "
                            "ORDER BY created ASC"
                        ).format(" AND ".join(alert_conditions))
                        alert_result = session.execute(text(alert_sql), alert_params)
                        alert_rows = alert_result.fetchall()

                        # 按设备分组
                        from collections import defaultdict
                        alerts_by_device = defaultdict(list)
                        for arow in alert_rows:
                            dev_id = str(arow[0]) if arow[0] else ""
                            a_created = str(arow[1]) if arow[1] else ""
                            a_text = str(arow[2]) if arow[2] else ""
                            alerts_by_device[dev_id].append((a_created, a_text))

                        # 解析并匹配（每条 vital ±30 秒内的报警）
                        TIME_WINDOW_SECONDS = 30
                        for rec in records:
                            if not rec.timestamp:
                                continue
                            dt_v = _parse_datetime(rec.timestamp)
                            if dt_v is None:
                                continue
                            matched = []
                            for a_created, a_text in alerts_by_device.get(rec.device_id, []):
                                dt_a = _parse_datetime(a_created)
                                if dt_a is None:
                                    continue
                                diff = abs((dt_v - dt_a).total_seconds())
                                if diff <= TIME_WINDOW_SECONDS:
                                    _lv, _cat, parsed_text, _mc, _mn, _pn = _classify_alarm(a_text)
                                    # 过滤掉"报警停止/解除"这种非诊断类信息
                                    if parsed_text and "停止" not in parsed_text and "解除" not in parsed_text:
                                        if parsed_text not in matched:
                                            matched.append(parsed_text)
                            if matched:
                                rec.diagnosis = "、".join(matched)
                    except Exception as ex:
                        pass
        finally:
            session.close()
        return records

    def get_vitals_count(
        self, device_id: Optional[str] = None,
        start_time: Optional[str] = None, end_time: Optional[str] = None,
    ) -> int:
        """获取符合条件的记录总数"""
        session = self._get_session()
        if session is None:
            return 0
        try:
            conditions = []
            params = {}
            if device_id:
                conditions.append("device_id = :device_id")
                params["device_id"] = device_id
            if start_time:
                conditions.append("created >= :start_time")
                params["start_time"] = start_time
            if end_time:
                conditions.append("created <= :end_time")
                params["end_time"] = end_time
            where = "WHERE " + " AND ".join(conditions) if conditions else ""
            return int(session.execute(text(f"SELECT COUNT(*) FROM vital {where}"), params).scalar() or 0)
        finally:
            session.close()

    # ================================================================
    # 报警数据查询
    # ================================================================

    def query_alarms(
        self, device_id: Optional[str] = None,
        start_time: Optional[str] = None, end_time: Optional[str] = None,
        keyword: Optional[str] = None,
        limit: int = 0, offset: int = 0, order: str = "desc",
        classify: bool = True,
    ) -> List[AlarmRecord]:
        """查询报警历史数据"""
        session = self._get_session()
        if session is None:
            return []
        records = []
        try:
            conditions = []
            params = {}
            if device_id:
                conditions.append("device_id = :device_id")
                params["device_id"] = device_id
            if start_time:
                conditions.append("created >= :start_time")
                params["start_time"] = start_time
            if end_time:
                conditions.append("created <= :end_time")
                params["end_time"] = end_time
            if keyword:
                conditions.append("alarm_text LIKE :keyword")
                params["keyword"] = f"%{keyword}%"

            where = "WHERE " + " AND ".join(conditions) if conditions else ""
            order_by = f"ORDER BY created {order.upper()}" if order.upper() in ["ASC", "DESC"] else "ORDER BY created DESC"
            lim = f"LIMIT {limit}" if limit > 0 else ""
            off = f"OFFSET {offset}" if offset > 0 and limit > 0 else ""

            sql = f"SELECT id, device_id, alarm_text, created FROM alert {where} {order_by} {lim} {off}"
            result = session.execute(text(sql), params)
            rows = result.fetchall()

            for row in rows:
                alarm_text = str(row[2]) if row[2] else ""
                level, category, parsed, mdc_code, mdc_name, param_name = ("", "", alarm_text, "", "", "")
                if classify:
                    level, category, parsed, mdc_code, mdc_name, param_name = _classify_alarm(alarm_text)
                rec = AlarmRecord(
                    id=int(row[0]) if row[0] else 0,
                    device_id=str(row[1]) if row[1] else "",
                    alarm_text=alarm_text,
                    alarm_parsed=parsed,
                    mdc_code=mdc_code,
                    mdc_name=mdc_name,
                    param_name=param_name,
                    severity=level,
                    timestamp=str(row[3]) if row[3] else "",
                    alarm_level=level, alarm_category=category,
                )
                records.append(rec)
        finally:
            session.close()
        return records

    def get_alarms_count(
        self, device_id: Optional[str] = None,
        start_time: Optional[str] = None, end_time: Optional[str] = None,
        keyword: Optional[str] = None,
    ) -> int:
        """获取符合条件的报警总数"""
        session = self._get_session()
        if session is None:
            return 0
        try:
            conditions = []
            params = {}
            if device_id:
                conditions.append("device_id = :device_id")
                params["device_id"] = device_id
            if start_time:
                conditions.append("created >= :start_time")
                params["start_time"] = start_time
            if end_time:
                conditions.append("created <= :end_time")
                params["end_time"] = end_time
            if keyword:
                conditions.append("alarm_text LIKE :keyword")
                params["keyword"] = f"%{keyword}%"
            where = "WHERE " + " AND ".join(conditions) if conditions else ""
            return int(session.execute(text(f"SELECT COUNT(*) FROM alert {where}"), params).scalar() or 0)
        finally:
            session.close()

    # ================================================================
    # 数据删除（供人工清理不合理数据）
    # ================================================================

    def delete_vital(self, vital_id: int) -> bool:
        """删除单条生命体征记录"""
        if vital_id <= 0:
            return False
        session = self._get_session()
        if session is None:
            return False
        try:
            session.execute(text("DELETE FROM vital WHERE id = :id"), {"id": vital_id})
            session.commit()
            return True
        except Exception:
            try:
                session.rollback()
            except Exception:
                pass
            return False
        finally:
            session.close()

    def delete_vitals(self, vital_ids: List[int]) -> int:
        """批量删除生命体征记录，返回实际删除数量"""
        if not vital_ids:
            return 0
        session = self._get_session()
        if session is None:
            return 0
        count = 0
        try:
            for vid in vital_ids:
                if vid <= 0:
                    continue
                r = session.execute(text("DELETE FROM vital WHERE id = :id"), {"id": vid})
                count += r.rowcount or 0
            session.commit()
        except Exception:
            try:
                session.rollback()
            except Exception:
                pass
            return 0
        finally:
            session.close()
        return count

    def delete_alarm(self, alarm_id: int) -> bool:
        """删除单条报警记录"""
        if alarm_id <= 0:
            return False
        session = self._get_session()
        if session is None:
            return False
        try:
            session.execute(text("DELETE FROM alert WHERE id = :id"), {"id": alarm_id})
            session.commit()
            return True
        except Exception:
            try:
                session.rollback()
            except Exception:
                pass
            return False
        finally:
            session.close()

    def delete_alarms(self, alarm_ids: List[int]) -> int:
        """批量删除报警记录，返回实际删除数量"""
        if not alarm_ids:
            return 0
        session = self._get_session()
        if session is None:
            return 0
        count = 0
        try:
            for aid in alarm_ids:
                if aid <= 0:
                    continue
                r = session.execute(text("DELETE FROM alert WHERE id = :id"), {"id": aid})
                count += r.rowcount or 0
            session.commit()
        except Exception:
            try:
                session.rollback()
            except Exception:
                pass
            return 0
        finally:
            session.close()
        return count

    # ================================================================
    # 统计分析
    # ================================================================

    def analyze_vitals(
        self, device_id: Optional[str] = None,
        start_time: Optional[str] = None, end_time: Optional[str] = None,
    ) -> StatisticsReport:
        """对生命体征数据进行统计分析"""
        records = self.query_vitals(device_id, start_time, end_time)
        alarms = self.query_alarms(device_id, start_time, end_time, classify=True)

        report = StatisticsReport(
            device_id=device_id or "ALL_DEVICES",
            total_records=len(records), total_alarms=len(alarms),
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        if start_time or end_time:
            report.time_range = f"{start_time or '最早'} 至 {end_time or '最新'}"
        else:
            report.time_range = "全部历史数据"

        params = {
            "hr": {"name": "心率", "unit": "bpm", "low": 60, "high": 100},
            "spo2": {"name": "血氧饱和度", "unit": "%", "low": 95, "high": 100},
            "rr": {"name": "呼吸频率", "unit": "rpm", "low": 12, "high": 20},
            "temp": {"name": "体温", "unit": "°C", "low": 36, "high": 37.5},
            "sys": {"name": "收缩压", "unit": "mmHg", "low": 90, "high": 140},
            "dia": {"name": "舒张压", "unit": "mmHg", "low": 60, "high": 90},
            "map": {"name": "平均动脉压", "unit": "mmHg", "low": 70, "high": 105},
        }

        for param_key, info in params.items():
            values = []
            for rec in records:
                val = getattr(rec, param_key)
                if val and val > 0:
                    values.append(float(val))
            if values:
                sorted_vals = sorted(values)
                n = len(values)
                avg = sum(values) / n
                low_count = sum(1 for v in values if v < info["low"])
                high_count = sum(1 for v in values if v > info["high"])
                report.parameter_stats[param_key] = {
                    "name": info["name"], "unit": info["unit"], "count": n,
                    "mean": round(avg, 1), "min": round(min(values), 1),
                    "max": round(max(values), 1),
                    "median": round(sorted_vals[n // 2], 1),
                    "normal_range": f"{info['low']}-{info['high']}",
                    "low_count": low_count, "high_count": high_count,
                    "violation_rate": round((low_count + high_count) / n * 100, 1),
                }
            else:
                report.parameter_stats[param_key] = {
                    "name": info["name"], "unit": info["unit"], "count": 0,
                    "mean": 0, "min": 0, "max": 0, "median": 0,
                    "normal_range": f"{info['low']}-{info['high']}",
                    "low_count": 0, "high_count": 0, "violation_rate": 0,
                }

        red_count = sum(1 for a in alarms if "红" in a.alarm_level)
        yellow_count = sum(1 for a in alarms if "黄" in a.alarm_level)
        white_count = sum(1 for a in alarms if "白" in a.alarm_level)
        physio = sum(1 for a in alarms if a.alarm_category == "physiological")
        tech = sum(1 for a in alarms if a.alarm_category == "technical")
        arr = sum(1 for a in alarms if a.alarm_category == "arrhythmia")
        report.alarm_summary = {
            "total": len(alarms), "red": red_count, "yellow": yellow_count,
            "white": white_count, "physiological": physio,
            "technical": tech, "arrhythmia": arr,
        }
        return report

    # ================================================================
    # 数据导出
    # ================================================================

    def export_to_csv(
        self, output_path: str,
        device_id: Optional[str] = None,
        start_time: Optional[str] = None, end_time: Optional[str] = None,
        data_type: str = "vitals",
    ) -> str:
        """导出数据到 CSV 文件"""
        out_dir = os.path.dirname(os.path.abspath(output_path))
        os.makedirs(out_dir, exist_ok=True)

        if data_type == "vitals":
            records = self.query_vitals(device_id, start_time, end_time)
            with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["ID", "设备编号", "患者姓名", "时间",
                                "心率(bpm)", "血氧(%)", "呼吸(rpm)", "体温(°C)",
                                "收缩压(mmHg)", "舒张压(mmHg)", "平均压(mmHg)"])
                for rec in records:
                    writer.writerow([rec.id, rec.device_id, rec.patient_name,
                                    rec.timestamp, rec.hr, rec.spo2, rec.rr,
                                    rec.temp, rec.sys, rec.dia, rec.map])
        elif data_type == "alarms":
            records = self.query_alarms(device_id, start_time, end_time, classify=True)
            with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["ID", "设备编号", "报警内容", "报警级别", "报警类型", "时间"])
                for rec in records:
                    writer.writerow([rec.id, rec.device_id, rec.alarm_text,
                                    rec.alarm_level, rec.alarm_category, rec.timestamp])
        else:
            raise ValueError(f"不支持的数据类型: {data_type}")
        return output_path

    def export_to_json(
        self, output_path: str,
        device_id: Optional[str] = None,
        start_time: Optional[str] = None, end_time: Optional[str] = None,
    ) -> str:
        """导出数据到 JSON 文件"""
        out_dir = os.path.dirname(os.path.abspath(output_path))
        os.makedirs(out_dir, exist_ok=True)

        vitals = self.query_vitals(device_id, start_time, end_time)
        alarms = self.query_alarms(device_id, start_time, end_time, classify=True)
        stats = self.analyze_vitals(device_id, start_time, end_time)

        data = {
            "export_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "query": {"device_id": device_id, "start_time": start_time, "end_time": end_time},
            "statistics": stats.to_dict(),
            "vitals": [v.to_dict() for v in vitals],
            "alarms": [a.to_dict() for a in alarms],
        }
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return output_path

    # ================================================================
    # 可视化
    # ================================================================

    def get_hourly_trend(
        self, device_id: str, start_time: str, end_time: str,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """生成按小时聚合的趋势数据"""
        session = self._get_session()
        if session is None:
            return {}
        trends = {}
        params = ["hr", "spo2", "rr", "temp", "sys", "dia", "map"]
        try:
            for param in params:
                sql = f"""
                    SELECT strftime('%Y-%m-%d %H:00:00', created) as hour,
                        AVG({param}), MIN({param}), MAX({param}), COUNT(*)
                    FROM vital WHERE device_id = :device_id AND created >= :start AND created <= :end
                    AND {param} > 0 GROUP BY hour ORDER BY hour
                """
                result = session.execute(text(sql), {"device_id": device_id, "start": start_time, "end": end_time})
                rows = result.fetchall()
                trends[param] = [
                    {"time": r[0], "avg": round(float(r[1]), 1) if r[1] else 0,
                     "min": round(float(r[2]), 1) if r[2] else 0,
                     "max": round(float(r[3]), 1) if r[3] else 0,
                     "count": int(r[4]) if r[4] else 0}
                    for r in rows
                ]
        finally:
            session.close()
        return trends

    def plot_vital_trends(
        self, output_path: str, device_id: str,
        start_time: str, end_time: str,
        params: Optional[List[str]] = None,
    ) -> Optional[str]:
        """绘制生命体征趋势图"""
        if not _MATPLOTLIB_AVAILABLE:
            print("⚠️  matplotlib 未安装，执行: pip install matplotlib")
            return None
        trends = self.get_hourly_trend(device_id, start_time, end_time)
        if not params:
            params = ["hr", "spo2", "rr"]
        valid = [p for p in params if trends.get(p)]
        if not valid:
            print("⚠️  该时间范围内无可用数据")
            return None

        fig, axes = plt.subplots(len(valid), 1, figsize=(12, 3 * len(valid)))
        if len(valid) == 1:
            axes = [axes]

        labels = {"hr": "心率 (bpm)", "spo2": "血氧 (%)", "rr": "呼吸 (rpm)",
                  "temp": "体温 (°C)", "sys": "收缩压 (mmHg)", "dia": "舒张压 (mmHg)", "map": "平均压 (mmHg)"}
        ranges = {"hr": (60, 100), "spo2": (95, 100), "rr": (12, 20),
                  "temp": (36, 37.5), "sys": (90, 140), "dia": (60, 90), "map": (70, 105)}

        for i, param in enumerate(valid):
            ax = axes[i]
            data = trends[param]
            x = list(range(len(data)))
            avg_vals = [d["avg"] for d in data]
            min_vals = [d["min"] for d in data]
            max_vals = [d["max"] for d in data]

            if param in ranges:
                low, high = ranges[param]
                ax.axhspan(low, high, alpha=0.1, color="green", label="正常范围")

            ax.plot(x, avg_vals, "b-", linewidth=2, label="平均")
            ax.fill_between(x, min_vals, max_vals, alpha=0.2, color="blue", label="区间")

            for j, v in enumerate(avg_vals):
                if param in ranges:
                    low, high = ranges[param]
                    if v > 0 and (v < low or v > high):
                        ax.plot(j, v, "ro", markersize=6)

            ax.set_title(f"{labels.get(param, param)} - 设备 {device_id}")
            ax.set_ylabel(labels.get(param, param))
            ax.set_xlabel("时间")
            ax.grid(True, alpha=0.3)
            ax.legend(loc="upper right")

            step = max(1, len(data) // 10)
            tick_x = x[::step]
            tick_labels = [data[i]["time"][5:13] for i in tick_x]
            ax.set_xticks(tick_x)
            ax.set_xticklabels(tick_labels, rotation=45, ha="right")

        plt.suptitle(f"生命体征趋势\n{start_time} ~ {end_time}", fontsize=14, y=1.02)
        plt.tight_layout()
        out_dir = os.path.dirname(os.path.abspath(output_path))
        os.makedirs(out_dir, exist_ok=True)
        plt.savefig(output_path, dpi=100, bbox_inches="tight")
        plt.close(fig)
        return output_path

    def plot_alarm_statistics(
        self, output_path: str, device_id: Optional[str] = None,
        start_time: Optional[str] = None, end_time: Optional[str] = None,
    ) -> Optional[str]:
        """绘制报警统计柱状图"""
        if not _MATPLOTLIB_AVAILABLE:
            print("⚠️  matplotlib 未安装")
            return None
        alarms = self.query_alarms(device_id, start_time, end_time, classify=True)
        if not alarms:
            print("⚠️  无报警数据")
            return None

        cat_counts = defaultdict(int)
        level_counts = defaultdict(int)
        for a in alarms:
            cat_counts[a.alarm_category or "未知"] += 1
            level_counts[a.alarm_level or "未知"] += 1

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

        cat_labels = {"physiological": "生理报警", "technical": "技术报警",
                      "arrhythmia": "心律失常", "未知": "未分类"}
        cats = list(cat_counts.keys())
        cat_display = [cat_labels.get(c, c) for c in cats]
        cat_colors = {"physiological": "#FFB74D", "technical": "#81C784",
                      "arrhythmia": "#E57373", "未知": "#B0BEC5"}
        colors1 = [cat_colors.get(c, "#B0BEC5") for c in cats]

        ax1.bar(range(len(cats)), [cat_counts[c] for c in cats], color=colors1)
        ax1.set_xticks(range(len(cats)))
        ax1.set_xticklabels(cat_display, rotation=15)
        ax1.set_ylabel("次数")
        ax1.set_title("按类型统计")
        ax1.grid(True, axis="y", alpha=0.3)
        for i, v in enumerate([cat_counts[c] for c in cats]):
            ax1.text(i, v, str(v), ha="center", va="bottom", fontweight="bold")

        levels = list(level_counts.keys())
        lvl_colors = {"红色报警（高危）": "#E53935", "黄色报警（中危）": "#FBC02D",
                      "白色报警（低危）": "#90A4AE", "未知": "#B0BEC5"}
        colors2 = [lvl_colors.get(l, "#B0BEC5") for l in levels]
        ax2.bar(range(len(levels)), [level_counts[l] for l in levels], color=colors2)
        ax2.set_xticks(range(len(levels)))
        ax2.set_xticklabels(levels, rotation=15)
        ax2.set_ylabel("次数")
        ax2.set_title("按级别统计")
        ax2.grid(True, axis="y", alpha=0.3)
        for i, v in enumerate([level_counts[l] for l in levels]):
            ax2.text(i, v, str(v), ha="center", va="bottom", fontweight="bold")

        device_label = device_id or "全部设备"
        plt.suptitle(f"报警统计 - 设备: {device_label}\n共 {len(alarms)} 条报警", fontsize=14)
        plt.tight_layout()
        out_dir = os.path.dirname(os.path.abspath(output_path))
        os.makedirs(out_dir, exist_ok=True)
        plt.savefig(output_path, dpi=100, bbox_inches="tight")
        plt.close(fig)
        return output_path

    # ================================================================
    # 综合报告
    # ================================================================

    def generate_full_report(
        self, output_dir: str,
        device_id: Optional[str] = None, hours: int = 24,
    ) -> Dict[str, str]:
        """生成完整的数据报告（CSV + JSON + 图表）"""
        os.makedirs(output_dir, exist_ok=True)
        end = datetime.now()
        start = end - timedelta(hours=hours)
        start_str = start.strftime("%Y-%m-%d %H:%M:%S")
        end_str = end.strftime("%Y-%m-%d %H:%M:%S")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        device_label = device_id or "ALL"
        files = {}

        csv1 = os.path.join(output_dir, f"vitals_{device_label}_{timestamp}.csv")
        files["csv_vitals"] = self.export_to_csv(csv1, device_id, start_str, end_str, "vitals")

        csv2 = os.path.join(output_dir, f"alarms_{device_label}_{timestamp}.csv")
        files["csv_alarms"] = self.export_to_csv(csv2, device_id, start_str, end_str, "alarms")

        json_path = os.path.join(output_dir, f"report_{device_label}_{timestamp}.json")
        files["json_report"] = self.export_to_json(json_path, device_id, start_str, end_str)

        if device_id:
            chart = os.path.join(output_dir, f"trends_{device_label}_{timestamp}.png")
            r1 = self.plot_vital_trends(chart, device_id, start_str, end_str)
            if r1:
                files["chart_trends"] = r1

        chart2 = os.path.join(output_dir, f"alarm_stats_{device_label}_{timestamp}.png")
        r2 = self.plot_alarm_statistics(chart2, device_id, start_str, end_str)
        if r2:
            files["chart_alarms"] = r2

        report_path = os.path.join(output_dir, f"summary_{device_label}_{timestamp}.txt")
        report = self.analyze_vitals(device_id, start_str, end_str)
        files["text_report"] = self._write_text_report(report_path, report, device_label, start_str, end_str)

        return files

    def _write_text_report(
        self, output_path: str, report: StatisticsReport,
        device_label: str, start_str: str, end_str: str,
    ) -> str:
        lines = []
        lines.append("=" * 60)
        lines.append("  监护仪数据分析报告")
        lines.append("=" * 60)
        lines.append(f"生成时间: {report.generated_at}")
        lines.append(f"设备: {device_label}")
        lines.append(f"时间范围: {start_str} ~ {end_str}")
        lines.append(f"生命体征: {report.total_records} 条")
        lines.append(f"报警记录: {report.total_alarms} 条")
        lines.append("")
        lines.append("-" * 60)
        lines.append("  参数统计")
        lines.append("-" * 60)
        for param, stats in report.parameter_stats.items():
            if stats["count"] == 0:
                lines.append(f"\n{stats['name']:<12}: 无数据")
                continue
            lines.append(f"\n{stats['name']} ({stats['unit']}):")
            lines.append(f"  样本: {stats['count']}  平均: {stats['mean']}  最小: {stats['min']}  最大: {stats['max']}  中位: {stats['median']}")
            lines.append(f"  正常范围: {stats['normal_range']}")
            lines.append(f"  越下限: {stats['low_count']}次 | 越上限: {stats['high_count']}次 | 越限率: {stats['violation_rate']}%")

        lines.append("")
        lines.append("-" * 60)
        lines.append("  报警统计")
        lines.append("-" * 60)
        a = report.alarm_summary
        lines.append(f"总数: {a['total']}")
        lines.append(f"红色(高危): {a['red']} | 黄色(中危): {a['yellow']} | 白色(低危): {a['white']}")
        lines.append(f"生理报警: {a['physiological']} | 技术报警: {a['technical']} | 心律失常: {a['arrhythmia']}")
        lines.append("")
        lines.append("=" * 60)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return output_path

    # ================================================================
    # 交互式 Shell 模式
    # ================================================================

    def interactive_mode(self):
        """交互式查询模式"""
        print("\n" + "=" * 60)
        print("  监护仪历史档案管理器 - 交互模式")
        print("=" * 60)
        info = self.get_database_info()
        print(f"\n📊 数据库状态:")
        print(f"   路径: {info['db_path']}")
        print(f"   大小: {info['db_size_mb']:.2f} MB")
        print(f"   生命体征: {info['tables'].get('vital', 0)} 条")
        print(f"   报警记录: {info['tables'].get('alert', 0)} 条")
        print(f"   设备数: {info['tables'].get('device', 0)} 台")

        commands = {
            "1": ("列出所有设备", self._cmd_list_devices),
            "2": ("查询生命体征", self._cmd_query_vitals),
            "3": ("查询报警记录", self._cmd_query_alarms),
            "4": ("生成统计分析", self._cmd_analyze),
            "5": ("导出 CSV", self._cmd_export_csv),
            "6": ("导出 JSON 报告", self._cmd_export_json),
            "7": ("生成趋势图", self._cmd_plot_trends),
            "8": ("生成报警统计图", self._cmd_plot_alarms),
            "9": ("生成完整报告包", self._cmd_full_report),
        }

        while True:
            print("\n" + "-" * 50)
            print("可用命令:")
            for k in sorted(commands.keys()):
                print(f"  {k}. {commands[k][0]}")
            print("  0. 退出")
            print("-" * 50)
            choice = input("请选择 [0-9]: ").strip()
            if choice == "0":
                print("👋 退出交互模式")
                break
            if choice in commands:
                try:
                    commands[choice][1]()
                except Exception as e:
                    print(f"⚠️  出错: {e}")
                    import traceback
                    traceback.print_exc()
            else:
                print("❌ 无效选项")

    def _cmd_list_devices(self):
        devices = self.list_devices(include_stats=True)
        print(f"\n共发现 {len(devices)} 台设备:")
        for i, dev in enumerate(devices, 1):
            icon = "🟢" if dev.online else "⚪"
            print(f"  [{i}] {dev.sn} ({dev.ip_addr}) {icon}")
            print(f"       生命体征: {dev.vital_count} 条 | 报警: {dev.alarm_count} 条")
            print(f"       最后活跃: {dev.last_active}")

    def _cmd_query_vitals(self):
        device_id = input("设备编号 (回车=全部): ").strip()
        start = input("起始时间 YYYY-MM-DD HH:MM:SS (回车=最早): ").strip()
        end = input("结束时间 YYYY-MM-DD HH:MM:SS (回车=最新): ").strip()
        n = input("返回条数 (回车=100): ").strip() or "100"
        limit = int(n) if n.isdigit() else 100

        records = self.query_vitals(
            device_id=device_id or None, start_time=start or None,
            end_time=end or None, limit=limit,
        )
        total = self.get_vitals_count(device_id or None, start or None, end or None)
        print(f"\n共 {total} 条，显示前 {len(records)} 条:")
        print(f"{'ID':<6}{'设备':<22}{'时间':<20}HR  SpO2  RR   Temp  BP")
        for rec in records[:50]:
            bp = f"{int(rec.sys)}/{int(rec.dia)}" if (rec.sys > 0 or rec.dia > 0) else "-/-"
            print(f"{rec.id:<6}{rec.device_id[:20]:<22}{str(rec.timestamp)[5:19]:<20}"
                  f"{int(rec.hr):<4} {rec.spo2:<5.0f} {rec.rr:<4.0f} {rec.temp:<5.1f} {bp}")
        if len(records) > 50:
            print(f"  ... 还有 {len(records) - 50} 条")

    def _cmd_query_alarms(self):
        device_id = input("设备编号 (回车=全部): ").strip()
        start = input("起始时间 (回车=最早): ").strip()
        end = input("结束时间 (回车=最新): ").strip()
        keyword = input("关键词 (回车=全部): ").strip()
        n = input("返回条数 (回车=50): ").strip() or "50"
        limit = int(n) if n.isdigit() else 50

        records = self.query_alarms(
            device_id=device_id or None, start_time=start or None,
            end_time=end or None, keyword=keyword or None, limit=limit,
        )
        total = self.get_alarms_count(device_id or None, start or None, end or None, keyword or None)
        print(f"\n共 {total} 条报警，显示前 {len(records)} 条:")
        for rec in records:
            icon = "🔴" if "红" in rec.alarm_level else "🟡" if "黄" in rec.alarm_level else "⚪"
            print(f"  {icon} {rec.alarm_level:<12} {rec.alarm_category:<14} "
                  f"{rec.alarm_text[:40]:<42} {str(rec.timestamp)[5:19]}")

    def _cmd_analyze(self):
        device_id = input("设备编号 (回车=全部): ").strip()
        start = input("起始时间 (回车=最早): ").strip()
        end = input("结束时间 (回车=最新): ").strip()
        report = self.analyze_vitals(device_id or None, start or None, end or None)

        print(f"\n📊 分析报告 - {report.device_id}")
        print(f"   时间范围: {report.time_range}")
        print(f"   记录数: {report.total_records} | 报警数: {report.total_alarms}")

        print(f"\n{'参数':<12}{'样本':<8}{'均值':<10}{'最小':<10}{'最大':<10}"
              f"{'中位':<12}{'越下限':<8}{'越上限':<8}{'越限率':<8}")
        for param, stats in report.parameter_stats.items():
            if stats["count"] == 0: continue
            print(f"{stats['name']:<12}{stats['count']:<8}{stats['mean']:<10.1f}"
                  f"{stats['min']:<10.1f}{stats['max']:<10.1f}{stats['median']:<12.1f}"
                  f"{stats['low_count']:<8}{stats['high_count']:<8}{stats['violation_rate']:<8.1f}%")

        print(f"\n报警统计:")
        a = report.alarm_summary
        print(f"  红色(高危): {a['red']} | 黄色(中危): {a['yellow']} | 白色(低危): {a['white']}")
        print(f"  生理报警: {a['physiological']} | 技术报警: {a['technical']} | 心律失常: {a['arrhythmia']}")

    def _cmd_export_csv(self):
        dtype = input("导出类型 [1=生命体征, 2=报警记录]: ").strip()
        device_id = input("设备编号 (回车=全部): ").strip()
        start = input("起始时间 (回车=最早): ").strip()
        end = input("结束时间 (回车=最新): ").strip()
        out = input("输出路径 (回车=data/export.csv): ").strip() or "data/export.csv"
        data_type = "vitals" if dtype == "1" else "alarms"
        path = self.export_to_csv(out, device_id or None, start or None, end or None, data_type)
        print(f"✅ 已导出: {os.path.abspath(path)}")

    def _cmd_export_json(self):
        device_id = input("设备编号 (回车=全部): ").strip()
        start = input("起始时间 (回车=最早): ").strip()
        end = input("结束时间 (回车=最新): ").strip()
        out = input("输出路径 (回车=data/report.json): ").strip() or "data/report.json"
        path = self.export_to_json(out, device_id or None, start or None, end or None)
        print(f"✅ 已导出: {os.path.abspath(path)}")

    def _cmd_plot_trends(self):
        devices = self.list_devices(include_stats=False)
        if not devices:
            print("⚠️  没有可用设备")
            return
        for i, d in enumerate(devices, 1):
            print(f"  [{i}] {d.sn}")
        idx = input("选择设备编号: ").strip()
        if not idx.isdigit() or int(idx) < 1 or int(idx) > len(devices):
            print("❌ 无效选择")
            return
        device_id = devices[int(idx) - 1].sn
        start = input("起始时间 (回车=最近24h): ").strip()
        end = input("结束时间 (回车=现在): ").strip()
        if not start and not end:
            e = datetime.now()
            s = e - timedelta(hours=24)
            start, end = s.strftime("%Y-%m-%d %H:%M:%S"), e.strftime("%Y-%m-%d %H:%M:%S")
        out = input("输出路径 (回车=data/trends.png): ").strip() or "data/trends.png"
        result = self.plot_vital_trends(out, device_id, start, end)
        if result:
            print(f"✅ 已生成: {os.path.abspath(result)}")

    def _cmd_plot_alarms(self):
        device_id = input("设备编号 (回车=全部): ").strip()
        start = input("起始时间 (回车=最早): ").strip()
        end = input("结束时间 (回车=最新): ").strip()
        out = input("输出路径 (回车=data/alarm_stats.png): ").strip() or "data/alarm_stats.png"
        result = self.plot_alarm_statistics(out, device_id or None, start or None, end or None)
        if result:
            print(f"✅ 已生成: {os.path.abspath(result)}")

    def _cmd_full_report(self):
        devices = self.list_devices(include_stats=True)
        if devices:
            print("可用设备:")
            for i, d in enumerate(devices, 1):
                print(f"  [{i}] {d.sn} ({d.vital_count} 条记录)")
            print("  [0] 全部设备")
        choice = input("选择设备: ").strip()
        device_id = None
        if choice.isdigit() and int(choice) > 0 and int(choice) <= len(devices):
            device_id = devices[int(choice) - 1].sn
        hours = input("分析最近多少小时 (回车=24): ").strip() or "24"
        hours = int(hours) if hours.isdigit() else 24
        out_dir = input("输出目录 (回车=data/reports): ").strip() or "data/reports"
        files = self.generate_full_report(out_dir, device_id, hours)
        print(f"\n✅ 完整报告已生成:")
        for key, path in files.items():
            print(f"  {key:<15}: {os.path.abspath(path)}")


# ====================================================================
# 快速测试 & 模块导入示例
# ====================================================================

def quick_demo():
    """快速功能演示（无需交互模式）"""
    print("\n" + "=" * 50)
    print("  历史档案管理器 - 快速演示")
    print("=" * 50)
    mgr = HistoryArchiveManager()
    info = mgr.get_database_info()
    print(f"数据库: {info['db_path']}")
    print(f"大小: {info['db_size_mb']:.2f} MB")
    print(f"状态: {info['status']}")

    if not info["db_exists"]:
        print("⚠️  数据库不存在，无法继续演示")
        return

    # 设备列表
    devices = mgr.list_devices()
    print(f"\n接入设备数: {len(devices)}")
    for d in devices[:5]:
        print(f"  - {d.sn} ({d.ip_addr}) 生命体征:{d.vital_count} 报警:{d.alarm_count}")

    # 统计分析
    if devices:
        dev = devices[0].sn
        print(f"\n📊 对设备 {dev} 进行分析...")
        report = mgr.analyze_vitals(device_id=dev)
        print(f"  记录数: {report.total_records}, 报警数: {report.total_alarms}")
        for param, stats in report.parameter_stats.items():
            if stats["count"] > 0:
                print(f"  {stats['name']}: 平均={stats['mean']}, 越限率={stats['violation_rate']}%")

    # 导出 CSV 示例
    print(f"\n📦 正在导出数据...")
    out_csv = mgr.export_to_csv("data/demo_vitals.csv", data_type="vitals")
    print(f"  生命体征 CSV: {os.path.abspath(out_csv)}")


# ====================================================================
# 命令行入口
# ====================================================================

def main():
    """命令行程序入口"""
    print("\n╔" + "═" * 58 + "╗")
    print("║" + "  监护仪历史数据档案管理器".center(56) + "║")
    print("╚" + "═" * 58 + "╝")

    manager = HistoryArchiveManager()
    info = manager.get_database_info()

    if not info["db_exists"]:
        print(f"\n⚠️  数据库文件不存在: {manager.db_path}")
        print("   请先启动监护仪数据采集服务产生数据")

    # 支持命令行参数快速模式
    if len(sys.argv) > 1:
        if sys.argv[1] == "demo":
            quick_demo()
            return
        if sys.argv[1] == "info":
            info2 = manager.get_database_info()
            print(json.dumps(info2, ensure_ascii=False, indent=2))
            return

    manager.interactive_mode()


if __name__ == "__main__":
    main()