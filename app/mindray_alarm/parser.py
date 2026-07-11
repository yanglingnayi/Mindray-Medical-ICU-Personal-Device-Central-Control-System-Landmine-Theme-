r"""
迈瑞监护仪 HL7 报警消息解析器
==============================

解析迈瑞 (Mindray) 监护仪通过 HL7/MLLP 协议发送的报警报文。

支持的 HL7 段：
    - MSH: 消息头（设备信息、消息类型、时间戳）
    - OBX: 观察/结果段（参数数值 + 报警标识）
    - AL1: 过敏信息段（部分老型号使用）
    - EVN: 事件类型段
    - PID: 患者信息段

典型报警报文示例：
    MSH|^~\&|Mindray|BeneVision||20240101120000||ORU^R01|MSG001|P|2.3
    PID|1||P001||Zhang^San||19800101|M
    OBX|1|NM|196608^心率过高^ISO||125|bpm|100^120|H|||A
    OBX|2|ST|198004^SpO2探头脱落^ISO||FAULT|||||A
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple

from .codes import (
    MDC_CODE_MAP,
    get_alarm_description,
    get_alarm_level,
    get_alarm_priority,
    get_parameter_name,
    get_parameter_unit,
    get_normal_range,
    lookup_code_by_text,
)


# =========================================================================
# 数据结构
# =========================================================================

@dataclass
class ParsedAlarm:
    """解析后的单条报警信息"""
    device_sn: str = ""                          # 监护仪序列号 (MSH-3)
    device_ip: str = ""                          # 设备 IP
    patient_name: str = ""                       # 患者姓名 (PID-5)
    patient_id: str = ""                         # 患者 ID (PID-3)
    mdc_code: str = ""                           # MDC 编码 (OBX-3)
    parameter_key: str = ""                      # 参数键名
    alarm_text_zh: str = ""                      # 中文报警描述
    alarm_text_en: str = ""                      # 英文报警描述
    observed_value: str = ""                     # 观测值 (OBX-5)
    unit: str = ""                               # 单位 (OBX-6)
    reference_range: str = ""                    # 参考范围 (OBX-7)
    abnormal_flag: str = ""                      # 异常标识 (OBX-8: H/L/A/N)
    alarm_level: int = 0                         # 报警级别 1/2/3
    alarm_category: str = ""                     # 分类: physiological/technical/arrhythmia
    result_status: str = ""                      # 结果状态 (OBX-11: F/C/P)
    timestamp: str = ""                          # 报警时间戳 (MSH-7 或 OBX-14)
    raw_segment: str = ""                        # 原始 HL7 段文本
    is_valid: bool = False                       # 是否成功解析
    violation_type: str = ""                     # 越限类型: HIGH/LOW/FAULT/INFO
    response_suggestion: str = ""                # 处理建议

    def to_dict(self) -> Dict[str, Any]:
        return {
            "device_sn": self.device_sn,
            "device_ip": self.device_ip,
            "patient_name": self.patient_name,
            "patient_id": self.patient_id,
            "mdc_code": self.mdc_code,
            "parameter_key": self.parameter_key,
            "alarm_text_zh": self.alarm_text_zh,
            "alarm_text_en": self.alarm_text_en,
            "observed_value": self.observed_value,
            "unit": self.unit,
            "reference_range": self.reference_range,
            "abnormal_flag": self.abnormal_flag,
            "alarm_level": self.alarm_level,
            "alarm_category": self.alarm_category,
            "result_status": self.result_status,
            "timestamp": self.timestamp,
            "violation_type": self.violation_type,
            "response_suggestion": self.response_suggestion,
            "is_valid": self.is_valid,
        }

    @property
    def alarm_level_text(self) -> str:
        level_map = {1: "红色报警（高危）", 2: "黄色报警（中危）", 3: "白色报警（低危）"}
        return level_map.get(self.alarm_level, "未知")

    @property
    def summary(self) -> str:
        """生成简短报警摘要"""
        if not self.is_valid:
            return "未解析的报警信息"
        parts = [f"[{self.alarm_level_text}]"]
        if self.alarm_text_zh:
            parts.append(self.alarm_text_zh)
        if self.observed_value and self.unit:
            parts.append(f"{self.observed_value}{self.unit}")
        return " ".join(parts)


@dataclass
class AlarmMessage:
    """完整报警消息（可能包含多条报警）"""
    message_id: str = ""
    message_type: str = ""
    hl7_version: str = ""
    device_sn: str = ""
    timestamp: str = ""
    patient_name: str = ""
    patient_id: str = ""
    alarms: List[ParsedAlarm] = field(default_factory=list)
    raw_message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "message_type": self.message_type,
            "hl7_version": self.hl7_version,
            "device_sn": self.device_sn,
            "timestamp": self.timestamp,
            "patient_name": self.patient_name,
            "patient_id": self.patient_id,
            "alarm_count": len(self.alarms),
            "alarms": [a.to_dict() for a in self.alarms],
        }


# =========================================================================
# 处理建议生成规则
# =========================================================================

RESPONSE_RULES: Dict[str, str] = {
    "physiological": (
        "确认报警信息 → 检查患者状态 → 评估报警限设置是否合理 "
        "→ 根据临床情况调整参数或给予处置 → 记录报警事件"
    ),
    "technical": (
        "检查设备连接状态 → 重新固定/更换探头或电极 "
        "→ 确认设备自检通过 → 无法恢复时更换设备并记录"
    ),
    "arrhythmia": (
        "立即检查患者意识与生命体征 → 观察心电图波形 "
        "→ 准备急救药品与除颤仪 → 呼叫上级医师或急救团队"
    ),
}

LEVEL_RESPONSE_TIPS: Dict[int, str] = {
    1: "【立即处理】可能危及生命，需在数秒内响应",
    2: "【尽快处理】需在 1-3 分钟内评估并处理",
    3: "【常规关注】结合临床情况判断是否需要干预",
}


# =========================================================================
# 核心解析函数
# =========================================================================

def _split_hl7_fields(segment: str, sep: str = "|") -> List[str]:
    """将 HL7 段按分隔符拆分字段"""
    return segment.strip().split(sep)


def _parse_obx3(obx3_text: str) -> Tuple[str, str, str]:
    """
    解析 OBX-3 字段（标识符^描述^编码体系）
    
    例如: "196608^心率过高^ISO" → ("196608", "心率过高", "ISO")
         "MDC_HR^Heart Rate^MDC" → ("MDC_HR", "Heart Rate", "MDC")
    """
    if not obx3_text:
        return ("", "", "")
    parts = obx3_text.split("^")
    code = parts[0].strip() if len(parts) > 0 else ""
    desc = parts[1].strip() if len(parts) > 1 else ""
    system = parts[2].strip() if len(parts) > 2 else ""
    return (code, desc, system)


def _normalize_mdc_code(code_candidate: str, description: str) -> str:
    """
    从 OBX-3 的多种格式中提取标准 6 位 MDC 数字编码
    
    支持的输入：
        - "196608"          → 已是数字编码
        - "HR^心率过高"     → 通过描述文字查找
        - "MDC_HR_HIGH"    → 通过文本关键词查找
        - "NIBP_SYS^..."   → 识别关键参数名
    """
    if not code_candidate:
        # 尝试从描述文字反向查找
        return lookup_code_by_text(description) or ""
    
    # 如果是纯数字且在映射表中，直接使用
    if code_candidate.isdigit() and code_candidate in MDC_CODE_MAP:
        return code_candidate
    
    # 如果数字编码不在映射表，检查描述
    if code_candidate.isdigit():
        text_lookup = lookup_code_by_text(description)
        return text_lookup or code_candidate
    
    # 如果是非数字标识符，尝试关键词匹配
    text_lookup = lookup_code_by_text(code_candidate)
    if text_lookup:
        return text_lookup
    text_lookup = lookup_code_by_text(description)
    return text_lookup or ""


def _parse_timestamp(ts_str: str) -> str:
    """
    解析 HL7 时间戳（YYYYMMDDHHMMSS 格式）
    
    例如: "20240101120000" → "2024-01-01 12:00:00"
    """
    if not ts_str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        # 截取前14位标准时间
        ts = ts_str[:14]
        if len(ts) >= 14:
            dt = datetime(
                int(ts[0:4]), int(ts[4:6]), int(ts[6:8]),
                int(ts[8:10]), int(ts[10:12]), int(ts[12:14])
            )
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        elif len(ts) >= 8:
            dt = datetime(int(ts[0:4]), int(ts[4:6]), int(ts[6:8]))
            return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, IndexError):
        pass
    return ts_str


def _determine_violation_type(abnormal_flag: str, observed_value: str,
                              mdc_code: str) -> str:
    """判断越限类型"""
    flag = abnormal_flag.strip().upper() if abnormal_flag else ""
    if "H" in flag or ">" in flag:
        return "HIGH"
    if "L" in flag or "<" in flag:
        return "LOW"
    if "A" in flag or "FAULT" in observed_value.upper() or "ERR" in observed_value.upper():
        return "FAULT"
    if "N" in flag:
        return "NORMAL"
    
    # 从 MDC 代码推断
    if mdc_code:
        info = MDC_CODE_MAP.get(mdc_code, {})
        param = info.get("parameter", "")
        if "_HIGH" in param or "_H" in param:
            return "HIGH"
        if "_LOW" in param or "_L" in param:
            return "LOW"
        if info.get("category") == "technical":
            return "FAULT"
    
    return "INFO"


def _generate_response_suggestion(alarm: ParsedAlarm) -> str:
    """根据报警分类和级别生成处理建议"""
    parts = []
    if alarm.alarm_level in LEVEL_RESPONSE_TIPS:
        parts.append(LEVEL_RESPONSE_TIPS[alarm.alarm_level])
    if alarm.alarm_category in RESPONSE_RULES:
        parts.append(RESPONSE_RULES[alarm.alarm_category])
    return " | ".join(parts)


# =========================================================================
# HL7 段解析
# =========================================================================

def extract_device_info(msh_segment: str) -> Dict[str, str]:
    r"""
    解析 MSH 段，提取设备信息
    
    MSH 字段顺序（HL7 v2.3）：
        [0] MSH             段标识符
        [1] ^~\&            字段分隔符
        [2] 发送应用       Mindray
        [3] 发送设备       监护仪型号/序列号
        [4] 接收应用
        [5] 接收设备
        [6] 消息时间戳
        [7] 安全字段
        [8] 消息类型       ORU^R01
        [9] 消息控制ID
        [10] 处理ID        P (生产)
        [11] 版本号        2.3
    """
    result = {
        "device_sn": "",
        "message_type": "",
        "message_id": "",
        "hl7_version": "",
        "timestamp": "",
        "vendor": "",
    }
    if not msh_segment or not msh_segment.startswith("MSH"):
        return result
    
    fields = _split_hl7_fields(msh_segment)
    
    # 发送应用/设备信息
    if len(fields) > 2:
        result["vendor"] = fields[2]
    if len(fields) > 3:
        result["device_sn"] = fields[3]
    
    # 时间戳
    if len(fields) > 6:
        result["timestamp"] = _parse_timestamp(fields[6])
    
    # 消息类型
    if len(fields) > 8:
        result["message_type"] = fields[8]
    
    # 消息控制ID
    if len(fields) > 9:
        result["message_id"] = fields[9]
    
    # HL7 版本
    if len(fields) > 11:
        result["hl7_version"] = fields[11]
    
    return result


def extract_patient_info(pid_segment: str) -> Dict[str, str]:
    """
    解析 PID 段，提取患者信息
    
    PID 字段顺序：
        [0] PID             段标识符
        [1] 设置ID
        [2] 患者ID (外部)
        [3] 患者ID (内部)
        [4] 备用ID
        [5] 患者姓名        Zhang^San^Ming
        [6] 母亲姓名
        [7] 出生日期
        [8] 性别
    """
    result = {"patient_id": "", "patient_name": ""}
    if not pid_segment or not pid_segment.startswith("PID"):
        return result
    
    fields = _split_hl7_fields(pid_segment)
    
    # 患者ID
    if len(fields) > 3 and fields[3]:
        result["patient_id"] = fields[3]
    elif len(fields) > 2 and fields[2]:
        result["patient_id"] = fields[2]
    
    # 患者姓名 (Zhang^San → 张三)
    if len(fields) > 5 and fields[5]:
        name_parts = fields[5].split("^")
        # 过滤空值
        name_parts = [p for p in name_parts if p.strip()]
        # 尝试识别中文姓名（没有 ^ 分隔符时直接使用）
        if len(name_parts) == 1:
            result["patient_name"] = name_parts[0]
        elif len(name_parts) >= 2:
            # 中文姓名通常: 姓^名
            result["patient_name"] = f"{name_parts[0]}{name_parts[1]}"
        else:
            result["patient_name"] = fields[5]
    
    return result


def extract_alarm_from_obx(obx_segment: str, base_info: Optional[Dict] = None) -> Optional[ParsedAlarm]:
    """
    解析 OBX 段，提取报警信息
    
    OBX 字段顺序：
        [0] OBX             段标识符
        [1] 序号            1
        [2] 值类型          NM (数值) / ST (字符串)
        [3] 标识符          MDC_CODE^描述^ISO
        [4] 命名空间
        [5] 观测值          125 或 FAULT
        [6] 单位            bpm / % / mmHg
        [7] 参考范围        60^100
        [8] 异常标识        H (高) / L (低) / A (异常) / N (正常)
        [9] 概率
        [10] 异常性质
        [11] 结果状态       F (最终) / C (改正) / P (初步)
        [12] 日期时间
        [13] 操作者
        [14] 观测时间
    """
    if not obx_segment or not obx_segment.startswith("OBX"):
        return None
    
    fields = _split_hl7_fields(obx_segment)
    if len(fields) < 3:
        return None
    
    alarm = ParsedAlarm()
    alarm.raw_segment = obx_segment
    
    # 填充基础信息
    if base_info:
        alarm.device_sn = base_info.get("device_sn", "")
        alarm.timestamp = base_info.get("timestamp", "")
        alarm.patient_name = base_info.get("patient_name", "")
        alarm.patient_id = base_info.get("patient_id", "")
    
    # 解析 OBX-3 标识符
    obx3 = fields[3] if len(fields) > 3 else ""
    raw_code, description, _ = _parse_obx3(obx3)
    
    # 标准化 MDC 编码
    mdc_code = _normalize_mdc_code(raw_code, description)
    alarm.mdc_code = mdc_code
    alarm.alarm_text_en = description
    alarm.alarm_text_zh = description  # 先用原始描述
    
    # 查找映射表获取信息
    if mdc_code and mdc_code in MDC_CODE_MAP:
        info = MDC_CODE_MAP[mdc_code]
        alarm.alarm_text_zh = info["name_zh"]
        alarm.alarm_text_en = info["name_en"]
        alarm.parameter_key = info["parameter"]
        alarm.unit = info["unit"] or alarm.unit
        alarm.alarm_level = info["alarm_level"]
        alarm.alarm_category = info["category"]
    
    # 观测值 OBX-5
    if len(fields) > 5:
        alarm.observed_value = fields[5].strip()
    
    # 单位 OBX-6（优先使用 HL7 报文中的单位）
    if len(fields) > 6 and fields[6]:
        alarm.unit = fields[6]
    
    # 参考范围 OBX-7
    if len(fields) > 7:
        alarm.reference_range = fields[7].replace("^", " - ")
    
    # 异常标识 OBX-8
    if len(fields) > 8:
        alarm.abnormal_flag = fields[8].strip().upper()
    
    # 结果状态 OBX-11
    if len(fields) > 11:
        alarm.result_status = fields[11].strip().upper()
    
    # 观测时间 OBX-14
    if len(fields) > 14 and fields[14]:
        alarm.timestamp = _parse_timestamp(fields[14])
    
    # 计算越限类型
    alarm.violation_type = _determine_violation_type(
        alarm.abnormal_flag, alarm.observed_value, alarm.mdc_code
    )
    
    # 如果从映射表没找到级别，根据异常标识兜底
    if alarm.alarm_level == 0:
        if alarm.abnormal_flag in ["H", "L", "A"] or alarm.violation_type == "FAULT":
            alarm.alarm_level = 2
        elif alarm.violation_type in ["HIGH", "LOW"]:
            alarm.alarm_level = 2
        else:
            alarm.alarm_level = 3
    
    # 生成处理建议
    alarm.response_suggestion = _generate_response_suggestion(alarm)
    
    # 标记有效解析
    alarm.is_valid = bool(alarm.mdc_code or alarm.alarm_text_zh or alarm.observed_value)
    
    return alarm


def extract_alarm_from_al1(al1_segment: str, base_info: Optional[Dict] = None) -> Optional[ParsedAlarm]:
    """
    解析 AL1 段（过敏信息段，部分迈瑞老型号设备使用此段传递报警）
    
    AL1 字段顺序：
        [0] AL1             段标识符
        [1] 序号            1
        [2] 过敏类型        报警类型代码
        [3] 过敏原/描述     报警文字描述
        [4] 过敏严重程度    严重度
        [5] 过敏反应
        [6] 识别日期
    """
    if not al1_segment or not al1_segment.startswith("AL1"):
        return None
    
    fields = _split_hl7_fields(al1_segment)
    if len(fields) < 4:
        return None
    
    alarm = ParsedAlarm()
    alarm.raw_segment = al1_segment
    
    if base_info:
        alarm.device_sn = base_info.get("device_sn", "")
        alarm.timestamp = base_info.get("timestamp", "")
        alarm.patient_name = base_info.get("patient_name", "")
    
    # AL1-3: 报警描述
    description = fields[3] if len(fields) > 3 else ""
    
    # AL1-2: 可能包含编码
    code_candidate = fields[2] if len(fields) > 2 else ""
    
    # 尝试从描述文本反查 MDC 代码
    mdc_code = _normalize_mdc_code(code_candidate, description) or lookup_code_by_text(description)
    alarm.mdc_code = mdc_code if mdc_code else ""
    alarm.alarm_text_zh = description
    
    if mdc_code and mdc_code in MDC_CODE_MAP:
        info = MDC_CODE_MAP[mdc_code]
        alarm.alarm_text_zh = info["name_zh"]
        alarm.alarm_text_en = info["name_en"]
        alarm.parameter_key = info["parameter"]
        alarm.unit = info["unit"]
        alarm.alarm_level = info["alarm_level"]
        alarm.alarm_category = info["category"]
    else:
        # 兜底逻辑
        alarm.alarm_level = 2
        alarm.alarm_category = "physiological"
    
    # 严重程度
    if len(fields) > 4 and fields[4]:
        severity = fields[4].upper()
        if "SEVERE" in severity or "严重" in severity:
            alarm.alarm_level = 1
    
    alarm.violation_type = _determine_violation_type("", description, alarm.mdc_code)
    alarm.response_suggestion = _generate_response_suggestion(alarm)
    alarm.is_valid = True
    
    return alarm


# =========================================================================
# 评估与分类辅助函数
# =========================================================================

def evaluate_limit_violation(param_key: str, value: float,
                             custom_low: Optional[float] = None,
                             custom_high: Optional[float] = None) -> Dict[str, Any]:
    """
    评估数值参数是否越限
    
    Args:
        param_key: 参数键名（如 "HR", "SpO2"）
        value: 当前测量值
        custom_low: 自定义下限（覆盖默认值）
        custom_high: 自定义上限（覆盖默认值）
    
    Returns:
        评估结果字典，包含:
        - is_violation: 是否越限
        - violation_type: "HIGH"/"LOW"/"NORMAL"
        - normal_low: 下限
        - normal_high: 上限
        - deviation: 偏差百分比
    """
    range_info = get_normal_range(param_key)
    if range_info:
        low, high, unit = range_info
    else:
        low, high, unit = 0.0, 0.0, ""
    
    # 应用自定义值
    if custom_low is not None:
        low = custom_low
    if custom_high is not None:
        high = custom_high
    
    result = {
        "parameter": param_key,
        "value": value,
        "unit": unit,
        "normal_low": low,
        "normal_high": high,
        "is_violation": False,
        "violation_type": "NORMAL",
        "deviation": 0.0,
    }
    
    if high > low:
        if value > high:
            result["is_violation"] = True
            result["violation_type"] = "HIGH"
            result["deviation"] = round((value - high) / high * 100, 1)
        elif value < low:
            result["is_violation"] = True
            result["violation_type"] = "LOW"
            result["deviation"] = round((low - value) / low * 100, 1)
    
    return result


def classify_alarm(alarm: ParsedAlarm) -> Dict[str, str]:
    """对报警进行分类，返回分类摘要"""
    return {
        "category": alarm.alarm_category,
        "category_zh": {
            "physiological": "生理报警（参数越限）",
            "technical": "技术报警（设备故障）",
            "arrhythmia": "心律失常报警",
        }.get(alarm.alarm_category, "未知类型"),
        "level": str(alarm.alarm_level),
        "level_text": alarm.alarm_level_text,
        "violation": alarm.violation_type,
    }


# =========================================================================
# 消息级解析
# =========================================================================

def parse_hl7_alarm_message(raw_message: str, device_ip: str = "") -> AlarmMessage:
    """
    解析完整的 HL7 报警消息
    
    Args:
        raw_message: 原始 HL7 消息文本（以 \r 或 \n 分隔段）
        device_ip: 设备 IP 地址（可选，用于标识设备）
    
    Returns:
        AlarmMessage 对象，包含解析后的全部报警信息
    
    使用示例:
        msg = "MSH|^~\\&|Mindray|DEV001||20240101120000||ORU^R01|...\rOBX|1|NM|196608^心率过高^ISO||125|bpm|60^100|H|||A"
        result = parse_hl7_alarm_message(msg, "192.168.1.100")
        print(f"发现 {len(result.alarms)} 条报警")
        for alarm in result.alarms:
            print(f"  - {alarm.summary}")
    """
    message = AlarmMessage(raw_message=raw_message)
    
    if not raw_message:
        return message
    
    # 归一化段分隔符（HL7 标准是 \r，实际环境可能是 \n 或 \r\n）
    segments = re.split(r"[\r\n]+", raw_message.strip())
    segments = [s for s in segments if s]
    
    # 基础信息
    base_info: Dict[str, str] = {"device_ip": device_ip}
    
    # 解析 MSH
    msh_seg = next((s for s in segments if s.startswith("MSH")), "")
    if msh_seg:
        msh_info = extract_device_info(msh_seg)
        message.device_sn = msh_info["device_sn"]
        message.message_id = msh_info["message_id"]
        message.message_type = msh_info["message_type"]
        message.hl7_version = msh_info["hl7_version"]
        message.timestamp = msh_info["timestamp"]
        base_info.update(msh_info)
        base_info["device_sn"] = msh_info["device_sn"] or f"DEV_{device_ip}"
    
    # 解析 PID
    pid_seg = next((s for s in segments if s.startswith("PID")), "")
    if pid_seg:
        pid_info = extract_patient_info(pid_seg)
        message.patient_name = pid_info["patient_name"]
        message.patient_id = pid_info["patient_id"]
        base_info["patient_name"] = pid_info["patient_name"]
        base_info["patient_id"] = pid_info["patient_id"]
    
    base_info["device_ip"] = device_ip
    
    # 解析所有 OBX 段（含报警标识的）
    for seg in segments:
        if seg.startswith("OBX"):
            # 检查是否包含报警信息（有异常标识或数值明显异常）
            alarm = extract_alarm_from_obx(seg, base_info)
            if alarm and alarm.is_valid:
                alarm.device_ip = device_ip
                message.alarms.append(alarm)
        
        # 解析 AL1 段（老设备兼容）
        elif seg.startswith("AL1"):
            alarm = extract_alarm_from_al1(seg, base_info)
            if alarm and alarm.is_valid:
                alarm.device_ip = device_ip
                message.alarms.append(alarm)
    
    return message


# =========================================================================
# 高级解析类
# =========================================================================

class MindrayAlarmParser:
    """
    迈瑞监护仪报警消息高级解析器
    
    提供面向对象的解析接口，支持:
        - 逐条消息解析
        - 批量消息处理
        - 报警级别过滤
        - 自定义报警阈值
    """
    
    def __init__(self):
        self.custom_limits: Dict[str, Tuple[float, float]] = {}
        self.message_history: List[AlarmMessage] = []
    
    def set_custom_limit(self, param_key: str, low: float, high: float) -> None:
        """设置自定义参数报警限"""
        self.custom_limits[param_key.upper()] = (low, high)
    
    def parse(self, raw_message: str, device_ip: str = "") -> AlarmMessage:
        """解析单条报警消息"""
        msg = parse_hl7_alarm_message(raw_message, device_ip)
        
        # 应用自定义报警限重新评估
        for alarm in msg.alarms:
            try:
                value = float(alarm.observed_value)
                limits = self.custom_limits.get(alarm.parameter_key.upper())
                if limits:
                    eval_result = evaluate_limit_violation(
                        alarm.parameter_key, value, limits[0], limits[1]
                    )
                    if eval_result["is_violation"]:
                        alarm.violation_type = eval_result["violation_type"]
            except (ValueError, TypeError):
                pass
        
        self.message_history.append(msg)
        return msg
    
    def parse_stream(self, messages: List[str], device_ip: str = "") -> List[AlarmMessage]:
        """批量解析多条消息"""
        return [self.parse(m, device_ip) for m in messages if m]
    
    def filter_by_level(self, alarms: List[ParsedAlarm], max_level: int) -> List[ParsedAlarm]:
        """按报警级别过滤（level <= max_level）"""
        return [a for a in alarms if a.alarm_level > 0 and a.alarm_level <= max_level]
    
    def get_high_priority_alarms(self, message: AlarmMessage) -> List[ParsedAlarm]:
        """获取红色高优先级报警"""
        return self.filter_by_level(message.alarms, 1)
    
    def get_statistics(self) -> Dict[str, int]:
        """获取解析统计"""
        stats = {"total_messages": len(self.message_history),
                 "total_alarms": 0, "level_1": 0, "level_2": 0, "level_3": 0,
                 "physiological": 0, "technical": 0, "arrhythmia": 0}
        for msg in self.message_history:
            stats["total_alarms"] += len(msg.alarms)
            for alarm in msg.alarms:
                if alarm.alarm_level == 1:
                    stats["level_1"] += 1
                elif alarm.alarm_level == 2:
                    stats["level_2"] += 1
                elif alarm.alarm_level == 3:
                    stats["level_3"] += 1
                if alarm.alarm_category == "physiological":
                    stats["physiological"] += 1
                elif alarm.alarm_category == "technical":
                    stats["technical"] += 1
                elif alarm.alarm_category == "arrhythmia":
                    stats["arrhythmia"] += 1
        return stats
    
    def clear_history(self) -> None:
        """清空历史记录"""
        self.message_history.clear()