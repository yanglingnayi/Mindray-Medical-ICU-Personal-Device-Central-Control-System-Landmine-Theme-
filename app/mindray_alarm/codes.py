"""
迈瑞监护仪 MDC 编码映射表
========================

基于 ISO/IEEE 11073-10101 医疗设备命名规范（Nomenclature）
与迈瑞 (Mindray) 监护仪实际 HL7 报文扩展实现。

MDC 编码结构：
    - 每个生理参数、报警事件、技术状态均有唯一数字编码
    - 编码通常为 6 位数字，形如 149530
    - OBX-3 字段格式：MDC_CODE^中文描述^ISO
"""

from typing import Dict, Optional, Tuple

# =========================================================================
# 报警级别定义
# =========================================================================
# Level 1: 红色高优先级 - 危及生命，需立即处理
# Level 2: 黄色中优先级 - 需关注，短时间内处理
# Level 3: 白色/青色低优先级 - 提示信息，常规关注
# =========================================================================

ALARM_LEVEL_MAP: Dict[int, str] = {
    1: "红色报警（高危）",
    2: "黄色报警（中危）",
    3: "白色报警（低危）",
}

ALARM_PRIORITY_MAP: Dict[str, int] = {
    "HIGH": 1,
    "MEDIUM": 2,
    "LOW": 3,
    "紧急": 1,
    "警告": 2,
    "提示": 3,
    "CRITICAL": 1,
    "WARNING": 2,
    "INFO": 3,
}


# =========================================================================
# 生理参数正常值范围（成人默认值，临床场景下可动态调整）
# =========================================================================

PHYSIOLOGICAL_LIMITS: Dict[str, Dict[str, float]] = {
    "HR": {"low": 60.0, "high": 100.0, "unit": "bpm"},
    "PULSE": {"low": 60.0, "high": 100.0, "unit": "bpm"},
    "SPO2": {"low": 95.0, "high": 100.0, "unit": "%"},
    "RR": {"low": 12.0, "high": 20.0, "unit": "rpm"},
    "TEMP": {"low": 36.0, "high": 37.5, "unit": "°C"},
    "SYS": {"low": 90.0, "high": 140.0, "unit": "mmHg"},
    "DIA": {"low": 60.0, "high": 90.0, "unit": "mmHg"},
    "MAP": {"low": 70.0, "high": 105.0, "unit": "mmHg"},
    "ETCO2": {"low": 35.0, "high": 45.0, "unit": "mmHg"},
    "ST": {"low": -0.1, "high": 0.1, "unit": "mV"},
}


# =========================================================================
# MDC 代码主映射表
# =========================================================================
# 每条目结构：
#   code: MDC 编码（字符串）
#   name_zh: 中文描述
#   name_en: 英文描述
#   parameter: 参数键名（与 Vital 模型对应）
#   unit: 单位
#   alarm_level: 默认报警级别
#   category: 分类（physiological/technical/arrhythmia）
# =========================================================================

MDC_CODE_MAP: Dict[str, Dict] = {
    # ---------------- 核心生命体征 ----------------
    "149530": {
        "name_zh": "心率", "name_en": "Heart Rate",
        "parameter": "HR", "unit": "bpm",
        "alarm_level": 2, "category": "physiological",
    },
    "150456": {
        "name_zh": "血氧饱和度", "name_en": "SpO2",
        "parameter": "SpO2", "unit": "%",
        "alarm_level": 1, "category": "physiological",
    },
    "151578": {
        "name_zh": "呼吸频率", "name_en": "Respiratory Rate",
        "parameter": "RR", "unit": "rpm",
        "alarm_level": 2, "category": "physiological",
    },
    "150364": {
        "name_zh": "体温", "name_en": "Temperature",
        "parameter": "TEMP", "unit": "°C",
        "alarm_level": 3, "category": "physiological",
    },
    "150288": {
        "name_zh": "收缩压", "name_en": "Systolic BP",
        "parameter": "SYS", "unit": "mmHg",
        "alarm_level": 2, "category": "physiological",
    },
    "150290": {
        "name_zh": "舒张压", "name_en": "Diastolic BP",
        "parameter": "DIA", "unit": "mmHg",
        "alarm_level": 2, "category": "physiological",
    },
    "150292": {
        "name_zh": "平均动脉压", "name_en": "Mean Arterial Pressure",
        "parameter": "MAP", "unit": "mmHg",
        "alarm_level": 2, "category": "physiological",
    },
    # ---------------- 扩展生理参数 ----------------
    "149532": {
        "name_zh": "脉率", "name_en": "Pulse Rate",
        "parameter": "PULSE", "unit": "bpm",
        "alarm_level": 2, "category": "physiological",
    },
    "151680": {
        "name_zh": "呼气末二氧化碳", "name_en": "EtCO2",
        "parameter": "ETCO2", "unit": "mmHg",
        "alarm_level": 2, "category": "physiological",
    },
    "151682": {
        "name_zh": "呼吸频率(CO2)", "name_en": "Respiratory Rate (CO2)",
        "parameter": "RR_CO2", "unit": "rpm",
        "alarm_level": 2, "category": "physiological",
    },
    # ---------------- ECG 与心律失常 ----------------
    "149534": {
        "name_zh": "ST段偏移(I)", "name_en": "ST Segment I",
        "parameter": "ST_I", "unit": "mV",
        "alarm_level": 2, "category": "arrhythmia",
    },
    "149536": {
        "name_zh": "ST段偏移(II)", "name_en": "ST Segment II",
        "parameter": "ST_II", "unit": "mV",
        "alarm_level": 2, "category": "arrhythmia",
    },
    "149538": {
        "name_zh": "ST段偏移(III)", "name_en": "ST Segment III",
        "parameter": "ST_III", "unit": "mV",
        "alarm_level": 2, "category": "arrhythmia",
    },
    "149540": {
        "name_zh": "QT间期", "name_en": "QT Interval",
        "parameter": "QT", "unit": "ms",
        "alarm_level": 2, "category": "arrhythmia",
    },
    "149542": {
        "name_zh": "校正QT间期(QTc)", "name_en": "QTc Interval",
        "parameter": "QTC", "unit": "ms",
        "alarm_level": 1, "category": "arrhythmia",
    },
    # ---------------- 生理报警（参数越限） ----------------
    "196608": {
        "name_zh": "心率过高", "name_en": "HR High",
        "parameter": "HR_HIGH", "unit": "bpm",
        "alarm_level": 1, "category": "physiological",
    },
    "196609": {
        "name_zh": "心率过低", "name_en": "HR Low",
        "parameter": "HR_LOW", "unit": "bpm",
        "alarm_level": 1, "category": "physiological",
    },
    "196610": {
        "name_zh": "血氧饱和度过低", "name_en": "SpO2 Low",
        "parameter": "SPO2_LOW", "unit": "%",
        "alarm_level": 1, "category": "physiological",
    },
    "196611": {
        "name_zh": "呼吸频率过高", "name_en": "RR High",
        "parameter": "RR_HIGH", "unit": "rpm",
        "alarm_level": 2, "category": "physiological",
    },
    "196612": {
        "name_zh": "呼吸频率过低", "name_en": "RR Low",
        "parameter": "RR_LOW", "unit": "rpm",
        "alarm_level": 2, "category": "physiological",
    },
    "196613": {
        "name_zh": "收缩压过高", "name_en": "Systolic High",
        "parameter": "SYS_HIGH", "unit": "mmHg",
        "alarm_level": 2, "category": "physiological",
    },
    "196614": {
        "name_zh": "收缩压过低", "name_en": "Systolic Low",
        "parameter": "SYS_LOW", "unit": "mmHg",
        "alarm_level": 1, "category": "physiological",
    },
    "196615": {
        "name_zh": "舒张压过高", "name_en": "Diastolic High",
        "parameter": "DIA_HIGH", "unit": "mmHg",
        "alarm_level": 2, "category": "physiological",
    },
    "196616": {
        "name_zh": "舒张压过低", "name_en": "Diastolic Low",
        "parameter": "DIA_LOW", "unit": "mmHg",
        "alarm_level": 2, "category": "physiological",
    },
    "196617": {
        "name_zh": "体温过高", "name_en": "Temperature High",
        "parameter": "TEMP_HIGH", "unit": "°C",
        "alarm_level": 2, "category": "physiological",
    },
    "196618": {
        "name_zh": "体温过低", "name_en": "Temperature Low",
        "parameter": "TEMP_LOW", "unit": "°C",
        "alarm_level": 2, "category": "physiological",
    },
    "196619": {
        "name_zh": "平均动脉压过高", "name_en": "MAP High",
        "parameter": "MAP_HIGH", "unit": "mmHg",
        "alarm_level": 2, "category": "physiological",
    },
    "196620": {
        "name_zh": "平均动脉压过低", "name_en": "MAP Low",
        "parameter": "MAP_LOW", "unit": "mmHg",
        "alarm_level": 1, "category": "physiological",
    },
    "196621": {
        "name_zh": "脉率过高", "name_en": "Pulse High",
        "parameter": "PULSE_HIGH", "unit": "bpm",
        "alarm_level": 2, "category": "physiological",
    },
    "196622": {
        "name_zh": "脉率过低", "name_en": "Pulse Low",
        "parameter": "PULSE_LOW", "unit": "bpm",
        "alarm_level": 2, "category": "physiological",
    },
    "196623": {
        "name_zh": "呼气末二氧化碳过低", "name_en": "EtCO2 Low",
        "parameter": "ETCO2_LOW", "unit": "mmHg",
        "alarm_level": 2, "category": "physiological",
    },
    "196624": {
        "name_zh": "呼气末二氧化碳过高", "name_en": "EtCO2 High",
        "parameter": "ETCO2_HIGH", "unit": "mmHg",
        "alarm_level": 2, "category": "physiological",
    },
    # ---------------- 心律失常报警 ----------------
    "197000": {
        "name_zh": "心脏停搏", "name_en": "Asystole",
        "parameter": "ASYSTOLE", "unit": "",
        "alarm_level": 1, "category": "arrhythmia",
    },
    "197001": {
        "name_zh": "心室颤动", "name_en": "Ventricular Fibrillation",
        "parameter": "VF", "unit": "",
        "alarm_level": 1, "category": "arrhythmia",
    },
    "197002": {
        "name_zh": "室性心动过速", "name_en": "Ventricular Tachycardia",
        "parameter": "VT", "unit": "",
        "alarm_level": 1, "category": "arrhythmia",
    },
    "197003": {
        "name_zh": "心动过速", "name_en": "Tachycardia",
        "parameter": "TACHYCARDIA", "unit": "",
        "alarm_level": 2, "category": "arrhythmia",
    },
    "197004": {
        "name_zh": "心动过缓", "name_en": "Bradycardia",
        "parameter": "BRADYCARDIA", "unit": "",
        "alarm_level": 2, "category": "arrhythmia",
    },
    "197005": {
        "name_zh": "频发室性早搏", "name_en": "Frequent PVCs",
        "parameter": "PVC_FREQ", "unit": "",
        "alarm_level": 2, "category": "arrhythmia",
    },
    "197006": {
        "name_zh": "成对室早", "name_en": "Couplet PVC",
        "parameter": "PVC_COUPLET", "unit": "",
        "alarm_level": 2, "category": "arrhythmia",
    },
    "197007": {
        "name_zh": "室性二联律", "name_en": "Bigeminy",
        "parameter": "BIGEMINY", "unit": "",
        "alarm_level": 2, "category": "arrhythmia",
    },
    "197008": {
        "name_zh": "室性三联律", "name_en": "Trigeminy",
        "parameter": "TRIGEMINY", "unit": "",
        "alarm_level": 2, "category": "arrhythmia",
    },
    "197009": {
        "name_zh": "R-on-T 事件", "name_en": "R-on-T",
        "parameter": "RON_T", "unit": "",
        "alarm_level": 1, "category": "arrhythmia",
    },
    "197010": {
        "name_zh": "房性早搏", "name_en": "Premature Atrial Contraction",
        "parameter": "PAC", "unit": "",
        "alarm_level": 3, "category": "arrhythmia",
    },
    "197011": {
        "name_zh": "心房颤动", "name_en": "Atrial Fibrillation",
        "parameter": "AFIB", "unit": "",
        "alarm_level": 2, "category": "arrhythmia",
    },
    "197012": {
        "name_zh": "心房扑动", "name_en": "Atrial Flutter",
        "parameter": "AFLUTTER", "unit": "",
        "alarm_level": 2, "category": "arrhythmia",
    },
    "197013": {
        "name_zh": "ST段抬高", "name_en": "ST Elevation",
        "parameter": "ST_ELEV", "unit": "",
        "alarm_level": 1, "category": "arrhythmia",
    },
    "197014": {
        "name_zh": "ST段压低", "name_en": "ST Depression",
        "parameter": "ST_DEPRESS", "unit": "",
        "alarm_level": 2, "category": "arrhythmia",
    },
    "197015": {
        "name_zh": "QT间期延长", "name_en": "QT Prolongation",
        "parameter": "QT_LONG", "unit": "",
        "alarm_level": 1, "category": "arrhythmia",
    },
    "197016": {
        "name_zh": "无脉电活动", "name_en": "Pulseless Electrical Activity",
        "parameter": "PEA", "unit": "",
        "alarm_level": 1, "category": "arrhythmia",
    },
    "197017": {
        "name_zh": "起搏器未捕获", "name_en": "Pacemaker Not Capture",
        "parameter": "PM_NOCAP", "unit": "",
        "alarm_level": 2, "category": "arrhythmia",
    },
    "197018": {
        "name_zh": "起搏器未起搏", "name_en": "Pacemaker Not Pacing",
        "parameter": "PM_NOPACE", "unit": "",
        "alarm_level": 2, "category": "arrhythmia",
    },
    # ---------------- 技术报警（设备/探头故障） ----------------
    "198000": {
        "name_zh": "心电电极脱落", "name_en": "ECG Lead Off",
        "parameter": "ECG_LEAD_OFF", "unit": "",
        "alarm_level": 2, "category": "technical",
    },
    "198001": {
        "name_zh": "ECG 导联 I 脱落", "name_en": "Lead I Off",
        "parameter": "LEAD1_OFF", "unit": "",
        "alarm_level": 2, "category": "technical",
    },
    "198002": {
        "name_zh": "ECG 导联 II 脱落", "name_en": "Lead II Off",
        "parameter": "LEAD2_OFF", "unit": "",
        "alarm_level": 2, "category": "technical",
    },
    "198003": {
        "name_zh": "ECG 导联 III 脱落", "name_en": "Lead III Off",
        "parameter": "LEAD3_OFF", "unit": "",
        "alarm_level": 2, "category": "technical",
    },
    "198004": {
        "name_zh": "SpO2 探头脱落", "name_en": "SpO2 Probe Off",
        "parameter": "SPO2_OFF", "unit": "",
        "alarm_level": 2, "category": "technical",
    },
    "198005": {
        "name_zh": "SpO2 信号低弱", "name_en": "SpO2 Low Signal",
        "parameter": "SPO2_LOW_SIG", "unit": "",
        "alarm_level": 3, "category": "technical",
    },
    "198006": {
        "name_zh": "SpO2 干扰", "name_en": "SpO2 Interference",
        "parameter": "SPO2_INTERFERE", "unit": "",
        "alarm_level": 3, "category": "technical",
    },
    "198007": {
        "name_zh": "血压袖带脱落", "name_en": "NIBP Cuff Off",
        "parameter": "NIBP_OFF", "unit": "",
        "alarm_level": 3, "category": "technical",
    },
    "198008": {
        "name_zh": "血压测量失败", "name_en": "NIBP Measurement Error",
        "parameter": "NIBP_ERR", "unit": "",
        "alarm_level": 2, "category": "technical",
    },
    "198009": {
        "name_zh": "血压袖带漏气", "name_en": "NIBP Cuff Leak",
        "parameter": "NIBP_LEAK", "unit": "",
        "alarm_level": 3, "category": "technical",
    },
    "198010": {
        "name_zh": "体温探头脱落", "name_en": "Temp Probe Off",
        "parameter": "TEMP_OFF", "unit": "",
        "alarm_level": 3, "category": "technical",
    },
    "198011": {
        "name_zh": "呼末二氧化碳探头脱落", "name_en": "EtCO2 Probe Off",
        "parameter": "ETCO2_OFF", "unit": "",
        "alarm_level": 3, "category": "technical",
    },
    "198012": {
        "name_zh": "电池电量低", "name_en": "Low Battery",
        "parameter": "LOW_BATTERY", "unit": "",
        "alarm_level": 2, "category": "technical",
    },
    "198013": {
        "name_zh": "设备自检失败", "name_en": "Self Test Failed",
        "parameter": "SELF_TEST_FAIL", "unit": "",
        "alarm_level": 1, "category": "technical",
    },
    "198014": {
        "name_zh": "通信中断", "name_en": "Communication Lost",
        "parameter": "COMM_LOST", "unit": "",
        "alarm_level": 2, "category": "technical",
    },
    "198015": {
        "name_zh": "传感器故障", "name_en": "Sensor Failure",
        "parameter": "SENSOR_FAIL", "unit": "",
        "alarm_level": 2, "category": "technical",
    },
    "198016": {
        "name_zh": "ECG 信号干扰", "name_en": "ECG Interference",
        "parameter": "ECG_INTERFERE", "unit": "",
        "alarm_level": 3, "category": "technical",
    },
    "198017": {
        "name_zh": "报警暂停", "name_en": "Alarm Suspended",
        "parameter": "ALARM_SUSP", "unit": "",
        "alarm_level": 3, "category": "technical",
    },
    "198018": {
        "name_zh": "设备离线", "name_en": "Device Offline",
        "parameter": "DEVICE_OFFLINE", "unit": "",
        "alarm_level": 2, "category": "technical",
    },
    "198019": {
        "name_zh": "纸张用尽(打印机)", "name_en": "Paper Out",
        "parameter": "PAPER_OUT", "unit": "",
        "alarm_level": 3, "category": "technical",
    },
    "198020": {
        "name_zh": "温度过高(设备)", "name_en": "Device Over Temperature",
        "parameter": "DEV_OVERTEMP", "unit": "",
        "alarm_level": 2, "category": "technical",
    },
}


# =========================================================================
# 按类别分组的代码列表（便于快速筛选）
# =========================================================================

MDC_PHYSIOLOGICAL_CODES = [
    code for code, info in MDC_CODE_MAP.items()
    if info["category"] == "physiological"
]

MDC_TECHNICAL_CODES = [
    code for code, info in MDC_CODE_MAP.items()
    if info["category"] == "technical"
]

MDC_ARRHYTHMIA_CODES = [
    code for code, info in MDC_CODE_MAP.items()
    if info["category"] == "arrhythmia"
]


# =========================================================================
# 常用文本关键词到 MDC 代码的反向映射（从 HL7 文本字段反查）
# =========================================================================

TEXT_KEYWORD_MAP: Dict[str, str] = {
    # 心率相关
    "HR HIGH": "196608", "心率过高": "196608", "心率高": "196608",
    "HR LOW": "196609", "心率过低": "196609", "心率低": "196609",
    "PULSE HIGH": "196621", "脉率过高": "196621",
    "PULSE LOW": "196622", "脉率过低": "196622",
    # 血氧相关
    "SPO2 LOW": "196610", "血氧低": "196610", "血氧过低": "196610",
    "SPO2 HIGH": "196610",
    # 呼吸相关
    "RR HIGH": "196611", "呼吸过高": "196611", "RR LOW": "196612", "呼吸过低": "196612",
    # 血压相关
    "SYS HIGH": "196613", "收缩压高": "196613",
    "SYS LOW": "196614", "收缩压低": "196614",
    "DIA HIGH": "196615", "舒张压高": "196615",
    "DIA LOW": "196616", "舒张压低": "196616",
    "MAP HIGH": "196619", "平均动脉压高": "196619",
    "MAP LOW": "196620", "平均动脉压低": "196620",
    # 体温相关
    "TEMP HIGH": "196617", "体温过高": "196617",
    "TEMP LOW": "196618", "体温过低": "196618",
    # EtCO2 相关
    "ETCO2 HIGH": "196624", "ETCO2 LOW": "196623",
    # 心律失常
    "ASYSTOLE": "197000", "心脏停搏": "197000", "停搏": "197000",
    "VF": "197001", "VENTRICULAR FIBRILLATION": "197001", "室颤": "197001",
    "VT": "197002", "VENTRICULAR TACHYCARDIA": "197002", "室速": "197002",
    "TACHYCARDIA": "197003", "心动过速": "197003",
    "BRADYCARDIA": "197004", "心动过缓": "197004",
    "PVC": "197005", "室性早搏": "197005",
    "COUPLET": "197006", "成对室早": "197006",
    "BIGEMINY": "197007", "二联律": "197007",
    "TRIGEMINY": "197008", "三联律": "197008",
    "R-ON-T": "197009", "RON-T": "197009",
    "PAC": "197010", "房性早搏": "197010",
    "AFIB": "197011", "ATRIAL FIBRILLATION": "197011", "房颤": "197011",
    "AFLUTTER": "197012", "ATRIAL FLUTTER": "197012", "房扑": "197012",
    "ST ELEVATION": "197013", "ST抬高": "197013",
    "ST DEPRESSION": "197014", "ST压低": "197014",
    "QT PROLONG": "197015", "QT延长": "197015",
    "PEA": "197016", "无脉电活动": "197016",
    # 技术报警
    "LEAD OFF": "198000", "LEAD I OFF": "198001", "LEAD II OFF": "198002",
    "LEAD III OFF": "198003", "电极脱落": "198000", "导联脱落": "198000",
    "ECG OFF": "198000", "ECG LEAD": "198000",
    "SPO2 OFF": "198004", "SPO2 PROBE": "198004", "血氧探头脱落": "198004",
    "SPO2 LOW SIGNAL": "198005", "SPO2 WEAK": "198005",
    "SPO2 INTERFERENCE": "198006", "SPO2 NOISY": "198006",
    "NIBP OFF": "198007", "CUFF OFF": "198007", "袖带脱落": "198007",
    "NIBP ERROR": "198008", "NIBP FAIL": "198008", "血压测量失败": "198008",
    "NIBP LEAK": "198009", "CUFF LEAK": "198009",
    "TEMP OFF": "198010", "TEMP PROBE OFF": "198010",
    "ETCO2 OFF": "198011", "ETCO2 PROBE": "198011",
    "LOW BATTERY": "198012", "BATTERY LOW": "198012", "电池低": "198012",
    "SELF TEST": "198013", "自检失败": "198013",
    "COMM LOST": "198014", "COMMUNICATION LOST": "198014", "通信中断": "198014",
    "SENSOR FAILURE": "198015", "传感器故障": "198015",
    "ECG INTERFERENCE": "198016", "ECG NOISY": "198016",
    "ALARM SUSPENDED": "198017", "报警暂停": "198017",
    "OFFLINE": "198018", "DEVICE OFFLINE": "198018", "设备离线": "198018",
    "PAPER OUT": "198019", "纸尽": "198019",
    "OVER TEMPERATURE": "198020", "设备过热": "198020",
}


# =========================================================================
# 查询函数
# =========================================================================

def get_alarm_description(code: str) -> Optional[str]:
    """根据 MDC 编码获取中文报警描述"""
    info = MDC_CODE_MAP.get(code)
    return info["name_zh"] if info else None


def get_alarm_level(code: str) -> Optional[int]:
    """根据 MDC 编码获取报警级别（1=红,2=黄,3=白）"""
    info = MDC_CODE_MAP.get(code)
    return info["alarm_level"] if info else None


def get_alarm_priority(code: str) -> Optional[str]:
    """根据 MDC 编码获取报警级别文字描述"""
    level = get_alarm_level(code)
    return ALARM_LEVEL_MAP.get(level) if level else None


def get_parameter_name(code: str) -> Optional[str]:
    """根据 MDC 编码获取参数键名"""
    info = MDC_CODE_MAP.get(code)
    return info["parameter"] if info else None


def get_parameter_unit(code: str) -> Optional[str]:
    """根据 MDC 编码获取参数单位"""
    info = MDC_CODE_MAP.get(code)
    return info["unit"] if info else None


def get_normal_range(param_key: str) -> Optional[Tuple[float, float, str]]:
    """根据参数键名获取正常值范围 (low, high, unit)"""
    limits = PHYSIOLOGICAL_LIMITS.get(param_key.upper())
    if limits:
        return (limits["low"], limits["high"], limits["unit"])
    return None


def lookup_code_by_text(text: str) -> Optional[str]:
    """根据报警文本关键词反查 MDC 编码（不区分大小写）"""
    if not text:
        return None
    text_upper = text.strip().upper()
    for keyword, code in TEXT_KEYWORD_MAP.items():
        if keyword.upper() in text_upper:
            return code
    return None