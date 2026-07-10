import asyncio
from datetime import datetime
from app.database.database import SessionLocal
from app.models.vital import Vital
from app.models.device import Device
from app.websocket.manager import ws_manager

HOST = "0.0.0.0"
DATA_PORT = 2575
ALARM_PORT = 2576  # 🌟 注入：迈瑞硬件独立报警专用物理端口
START_BLOCK = b"\x0b"
END_BLOCK = b"\x1c"
CARRIAGE_RETURN = b"\x0d"

MDC_DICT = {
    "149530": "hr", "150456": "spo2", "151578": "rr", "150364": "temp",
    "150288": "sys", "150290": "dia", "150292": "map"
}

last_cache = {"hr": 0, "spo2": 0, "rr": 0, "temp": 0.0, "sys": 0, "dia": 0, "map": 0}

class MLLPMessageHandler:
    def __init__(self):
        self.client_buffer = {}

    # ========================================================
    # 核心一：解析 2575 端口的物理生命体征流（含血压全标示通杀）
    # ========================================================
    async def full_parse_message(self, full_msg: str, client_ip: str):
        global last_cache
        db = SessionLocal()
        try:
            current_vital = last_cache.copy()
            dev_sn = f"DEV_{client_ip}"
            current_vital["patient_name"] = "末音"

            segments = full_msg.replace('\r\n', '\n').replace('\r', '\n').split('\n')
            for seg in segments:
                fields = seg.strip().split('|')
                if not fields or not fields[0]: continue
                if fields[0] == "MSH" and len(fields) >= 4 and fields[3]:
                    dev_sn = fields[3]
                elif fields[0] == "OBX" and len(fields) >= 6:
                    obx_3_raw = fields[3].upper()
                    obx_3_code = obx_3_raw.split('^')[0]
                    obx_3_text = obx_3_raw.split('^')[1] if '^' in obx_3_raw else ""
                    obx_5_value = fields[5].strip()

                    target_key = None
                    if obx_3_code in MDC_DICT: target_key = MDC_DICT[obx_3_code]
                    elif "SYS" in obx_3_code or "SYS" in obx_3_text or "NIBP_S" in obx_3_code: target_key = "sys"
                    elif "DIA" in obx_3_code or "DIA" in obx_3_text or "NIBP_D" in obx_3_code: target_key = "dia"
                    elif "MAP" in obx_3_code or "MAP" in obx_3_text or "NIBP_M" in obx_3_code: target_key = "map"
                    elif "HR" in obx_3_code or "PULSE" in obx_3_text: target_key = "hr"
                    elif "SPO2" in obx_3_code or "SPO2" in obx_3_text: target_key = "spo2"
                    elif "RESP" in obx_3_code or "RR" in obx_3_text: target_key = "rr"

                    if target_key:
                        try:
                            val = float(obx_5_value) if '.' in obx_5_value else int(obx_5_value)
                            current_vital[target_key] = val
                        except ValueError: pass

            current_vital["device_id"] = dev_sn
            for k in last_cache.keys():
                if k in current_vital: last_cache[k] = current_vital[k]

            dev = db.query(Device).filter(Device.sn == dev_sn).first()
            if not dev:
                dev = Device(sn=dev_sn, ip_addr=client_ip, online=True, last_active=datetime.now())
                db.add(dev)
            else:
                dev.online = True; dev.last_active = datetime.now()
            
            db.add(Vital(**current_vital))
            db.commit()

            push_data = {
                "type": "data_stream", "sn": dev_sn, "patient_name": current_vital["patient_name"],
                "time": datetime.now().strftime("%H:%M:%S"),
                "raw_log": f"🧬 【2575 体征流】血压状态捕获: {current_vital['sys']}/{current_vital['dia']}",
                **current_vital
            }
            await ws_manager.broadcast(push_data)
        except Exception: db.rollback()
        finally: db.close()

    # ========================================================
    # 核心二：解析 2576 端口突发的硬件级别报警流（如心律失常、探头脱落）
    # ========================================================
    async def parse_alarm_message(self, full_msg: str, client_ip: str):
        try:
            from app.models.alert import Alert as _Alert
            from app.database.database import SessionLocal as _SessionLocal

            segments = full_msg.replace('\r\n', '\n').replace('\r', '\n').split('\n')
            alarm_text = "未定义核心系统越界"
            dev_sn = f"DEV_{client_ip}"
            
            for seg in segments:
                fields = seg.strip().split('|')
                if not fields or not fields[0]: continue
                if fields[0] == "MSH" and len(fields) >= 4 and fields[3]:
                    dev_sn = fields[3]
                elif fields[0] in ["OBX", "AL1"] and len(fields) >= 6:
                    # 强行抽取迈瑞 HL7 报文中的报警文本项或警告内容
                    obx_3_text = fields[3].split('^')[1] if '^' in fields[3] else ""
                    obx_5_val = fields[5]
                    alarm_text = f"{obx_3_text} {obx_5_val}".strip()
                    break

            # 持久化到数据库（页面关闭后仍可回溯）
            _db = _SessionLocal()
            try:
                _db.add(_Alert(device_id=dev_sn, alarm_text=alarm_text))
                _db.commit()
            except Exception:
                _db.rollback()
            finally:
                _db.close()

            # 组装报警包，打向前端 WebSocket 触发物理高频啸叫
            push_alarm = {
                "type": "alarm_stream",
                "sn": dev_sn,
                "time": datetime.now().strftime("%H:%M:%S"),
                "alarm_text": alarm_text if alarm_text else "监护仪核心生理指标越界！",
                "raw_log": f"⚠️ 【† 2576 报警流突发 †】状态: {alarm_text}"
            }
            await ws_manager.broadcast(push_alarm)
        except Exception: pass

    # ========================================================
    # 双核数据包心跳轮询调度引擎
    # ========================================================
    async def client_loop(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, is_alarm_port=False):
        peer_ip = writer.get_extra_info("peername")[0]
        self.client_buffer[f"{peer_ip}_{is_alarm_port}"] = b""
        
        while True:
            try:
                chunk = await reader.read(4096)
                if not chunk: break
                buf_key = f"{peer_ip}_{is_alarm_port}"
                self.client_buffer[buf_key] += chunk
                buf = self.client_buffer[buf_key]
                
                while START_BLOCK in buf and END_BLOCK in buf:
                    start_pos = buf.index(START_BLOCK)
                    end_pos = buf.index(END_BLOCK)
                    raw_msg_bytes = buf[start_pos + 1 : end_pos]
                    buf = buf[end_pos + len(END_BLOCK) :]
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
                            if len(fields) >= 10: msg_id = fields[9]
                            break
                    ack_text = f"MSH|^~\\&|||||ACK||P|2.3\rMSA|AA|{msg_id}\r"
                    writer.write(START_BLOCK + ack_text.encode("utf-8") + END_BLOCK + CARRIAGE_RETURN)
                    await writer.drain()
            except: break
        writer.close()

    async def start_server(self):
        # 利用 asyncio.gather 同时拉起 2575 与 2576 双端口，完全不阻塞主进程
        data_server = await asyncio.start_server(lambda r, w: self.client_loop(r, w, False), HOST, DATA_PORT)
        alarm_server = await asyncio.start_server(lambda r, w: self.client_loop(r, w, True), HOST, ALARM_PORT)
        async with data_server, alarm_server:
            await asyncio.gather(data_server.serve_forever(), alarm_server.serve_forever())

MLLP_SERVER = MLLPMessageHandler()