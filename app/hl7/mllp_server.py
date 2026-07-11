import asyncio
from datetime import datetime
from app.database.database import SessionLocal
from app.models.vital import Vital
from app.models.alert import Alert
from app.models.device import Device
from app.websocket.manager import ws_manager

HOST = "0.0.0.0"
DATA_PORT = 2575
ALARM_PORT = 2576
START_BLOCK = b"\x0b"
END_BLOCK = b"\x1c"
CARRIAGE_RETURN = b"\x0d"

MDC_DICT = {
    "149530": "hr", "150456": "spo2", "151578": "rr", "150364": "temp",
    "150288": "sys", "150290": "dia", "150292": "map"
}


class MLLPMessageHandler:
    def __init__(self):
        self.client_buffer = {}

    async def full_parse_message(self, full_msg: str, client_ip: str):
        db = SessionLocal()
        try:
            current_vital = {
                "hr": 0, "spo2": 0, "rr": 0, "temp": 0.0,
                "sys": 0, "dia": 0, "map": 0,
                "device_id": "", "patient_name": "末音",
            }
            dev_sn = f"DEV_{client_ip}"
            segments = full_msg.replace('\r\n', '\n').replace('\r', '\n').split('\n')

            for seg in segments:
                fields = seg.strip().split('|')
                if not fields or not fields[0]:
                    continue

                if fields[0] == "MSH" and len(fields) >= 4 and fields[3]:
                    dev_sn = fields[3]

                elif fields[0] == "OBX" and len(fields) >= 6:
                    obx_3_raw = fields[3].upper() if len(fields) > 3 else ""
                    obx_3_code = obx_3_raw.split('^')[0]
                    obx_3_text = obx_3_raw.split('^')[1] if '^' in obx_3_raw else ""
                    obx_5_value = fields[5].strip() if len(fields) > 5 else ""

                    target_key = None
                    if obx_3_code in MDC_DICT:
                        target_key = MDC_DICT[obx_3_code]
                    elif any(kw in obx_3_code or kw in obx_3_text
                             for kw in ["HR", "PULSE", "HEART"]):
                        target_key = "hr"
                    elif any(kw in obx_3_code or kw in obx_3_text
                             for kw in ["SPO2", "O2SAT", "SATURATION"]):
                        target_key = "spo2"
                    elif any(kw in obx_3_code or kw in obx_3_text
                             for kw in ["RESP", "RR", "BREATH"]):
                        target_key = "rr"
                    elif "SYS" in obx_3_code or "SYS" in obx_3_text or "NIBP_S" in obx_3_code:
                        target_key = "sys"
                    elif "DIA" in obx_3_code or "DIA" in obx_3_text or "NIBP_D" in obx_3_code:
                        target_key = "dia"
                    elif "MAP" in obx_3_code or "MAP" in obx_3_text or "NIBP_M" in obx_3_code:
                        target_key = "map"
                    elif "TEMP" in obx_3_code or "TEMP" in obx_3_text:
                        target_key = "temp"

                    if target_key and obx_5_value:
                        try:
                            val = float(obx_5_value) if '.' in obx_5_value else int(obx_5_value)
                            current_vital[target_key] = val
                        except (ValueError, TypeError):
                            pass

            current_vital["device_id"] = dev_sn

            dev = db.query(Device).filter(Device.sn == dev_sn).first()
            if not dev:
                dev = Device(sn=dev_sn, ip_addr=client_ip, online=True,
                             last_active=datetime.now())
                db.add(dev)
            else:
                dev.online = True
                dev.last_active = datetime.now()

            db.add(Vital(**current_vital))
            db.commit()

            push_data = {
                "type": "data_stream",
                "sn": dev_sn,
                "patient_name": current_vital["patient_name"],
                "time": datetime.now().strftime("%H:%M:%S"),
                **current_vital,
            }
            await ws_manager.broadcast(push_data)
        except Exception as e:
            print(f"[MLLP] full_parse_message error: {e}")
            db.rollback()
        finally:
            db.close()

    async def parse_alarm_message(self, full_msg: str, client_ip: str):
        try:
            # 调用专业解析器
            from app.mindray_alarm.parser import parse_hl7_alarm_message
            parsed = parse_hl7_alarm_message(full_msg, client_ip)
            dev_sn = parsed.device_sn or f"DEV_{client_ip}"
            alarms = parsed.alarms

            db = SessionLocal()
            try:
                if not alarms:
                    fallback_text = full_msg[:200] or "监护仪核心生理指标越界！"
                    db.add(Alert(device_id=dev_sn, alarm_text=fallback_text))
                else:
                    for alarm in alarms:
                        db.add(Alert(
                            device_id=dev_sn,
                            alarm_text=alarm.alarm_text_zh or alarm.alarm_text_en or full_msg[:200],
                        ))
                db.commit()
            except Exception:
                db.rollback()
            finally:
                db.close()

            # 主报警：选择级别最严重的（数字越小越严重）
            if alarms:
                alarms_sorted = sorted(alarms, key=lambda a: a.alarm_level if a.alarm_level else 99)
                primary = alarms_sorted[0]
            else:
                primary = None

            alarms_payload = []
            for alarm in alarms:
                alarms_payload.append({
                    "mdc_code": alarm.mdc_code,
                    "parameter_key": alarm.parameter_key,
                    "alarm_text_zh": alarm.alarm_text_zh,
                    "alarm_text_en": alarm.alarm_text_en,
                    "observed_value": alarm.observed_value,
                    "unit": alarm.unit,
                    "reference_range": alarm.reference_range,
                    "abnormal_flag": alarm.abnormal_flag,
                    "alarm_level": alarm.alarm_level,
                    "alarm_category": alarm.alarm_category,
                    "violation_type": alarm.violation_type,
                    "response_suggestion": alarm.response_suggestion,
                    "timestamp": alarm.timestamp,
                    "raw_segment": alarm.raw_segment,
                    "is_valid": alarm.is_valid,
                })

            # ============== 级别重新映射（关键修复） ==============
            # level=1  → P0 致命   → 大弹窗（仅真正的8种致命事件）
            # level=2  → P2 注意   → 右下角小弹窗（常规）
            # level=3  → P3 提示   → 右下角小弹窗
            # level=0/None → P3 提示
            def _map_severity(lev):
                if lev == 1: return "P0"
                if lev == 2: return "P2"
                if lev == 3: return "P3"
                return "P3"

            primary_level = primary.alarm_level if primary else 3
            primary_severity = _map_severity(primary_level)

            # ============== 构造明确的诊断文本 ==============
            value_display = "—"
            range_text = "参考设备设定阈值"
            cause_text = ""
            category = ""
            suggestion_text = ""

            if primary:
                metric_name = primary.alarm_text_zh or primary.parameter_key or primary.alarm_text_en or "未知指标"
                if primary.observed_value:
                    value_display = str(primary.observed_value) + (" " + primary.unit if primary.unit else "")
                diagnostic_title = metric_name
                if primary.violation_type:
                    vtype_map = {"HIGH": "过高", "LOW": "过低", "FAULT": "故障",
                                 "NORMAL": "正常", "INFO": "提示"}
                    diagnostic_title += " (" + vtype_map.get(primary.violation_type,
                                                   primary.violation_type) + ")"
                diagnostic_title += " " + value_display

                range_text = primary.reference_range or "参考设备设定阈值"

                category = primary.alarm_category or ""
                if category == "physiological":
                    cause_text = "生理参数越界: " + (primary.alarm_text_zh or primary.alarm_text_en or primary.parameter_key or "")
                elif category == "technical":
                    cause_text = "设备/技术报警: " + (primary.alarm_text_zh or primary.alarm_text_en or primary.parameter_key or "")
                elif category == "arrhythmia":
                    cause_text = "心律异常事件: " + (primary.alarm_text_zh or primary.alarm_text_en or primary.parameter_key or "")
                else:
                    cause_text = primary.alarm_text_zh or primary.alarm_text_en or full_msg[:50]

                suggestion_text = primary.response_suggestion or ""
            else:
                diagnostic_title = full_msg[:60] or "监护仪核心生理指标越界"
                value_display = "—"
                range_text = "—"
                cause_text = "未识别的报警报文"
                suggestion_text = "记录报警、观察患者状态；若反复出现请联系维护团队"

            push_alarm = {
                "type": "alarm_stream",
                "sn": dev_sn,
                "time": datetime.now().strftime("%H:%M:%S"),
                "patient_name": (parsed.patient_name or "末音"),
                "alarm_text": diagnostic_title,
                "alarm_count": len(alarms_payload),
                "level": primary_level if primary else 3,
                "severity": primary_severity,
                "category": category if primary else "physiological",
                "metric": (primary.parameter_key or primary.alarm_text_zh) if primary else "未知",
                "value": primary.observed_value if primary else "",
                "unit": primary.unit if primary else "",
                "range": range_text,
                "violation": primary.violation_type if primary else "",
                "suggestion": suggestion_text,
                "cause": cause_text,
                "alarms": alarms_payload,
                "raw_message": full_msg[:400],
            }
            await ws_manager.broadcast(push_alarm)
        except Exception as e:
            print(f"[MLLP] parse_alarm_message error: {e}")

    async def client_loop(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, is_alarm_port=False):
        peer_ip = writer.get_extra_info("peername")[0]
        self.client_buffer[f"{peer_ip}_{is_alarm_port}"] = b""

        while True:
            try:
                chunk = await reader.read(4096)
                if not chunk:
                    break
                buf_key = f"{peer_ip}_{is_alarm_port}"
                self.client_buffer[buf_key] += chunk
                buf = self.client_buffer[buf_key]

                while START_BLOCK in buf and END_BLOCK in buf:
                    start_pos = buf.index(START_BLOCK)
                    end_pos = buf.index(END_BLOCK)
                    raw_msg_bytes = buf[start_pos + 1: end_pos]
                    buf = buf[end_pos + len(END_BLOCK):]
                    self.client_buffer[buf_key] = buf

                    full_text = raw_msg_bytes.decode("utf-8", errors="ignore")
                    if is_alarm_port:
                        await self.parse_alarm_message(full_text, peer_ip)
                    else:
                        await self.full_parse_message(full_text, peer_ip)

                    msg_id = "1"
                    for line in full_text.split("\r"):
                        if line.startswith("MSH"):
                            fields = line.split("|")
                            if len(fields) >= 10:
                                msg_id = fields[9]
                            break
                    ack_text = f"MSH|^~\\&|||||ACK||P|2.3\rMSA|AA|{msg_id}\r"
                    writer.write(START_BLOCK + ack_text.encode("utf-8") + END_BLOCK + CARRIAGE_RETURN)
                    await writer.drain()
            except Exception:
                break
        writer.close()

    async def start_server(self):
        data_server = await asyncio.start_server(
            lambda r, w: self.client_loop(r, w, False), HOST, DATA_PORT
        )
        alarm_server = await asyncio.start_server(
            lambda r, w: self.client_loop(r, w, True), HOST, ALARM_PORT
        )
        async with data_server, alarm_server:
            await asyncio.gather(data_server.serve_forever(), alarm_server.serve_forever())


MLLP_SERVER = MLLPMessageHandler()