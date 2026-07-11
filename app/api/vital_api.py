import os
import shutil
from datetime import datetime, timedelta
from io import StringIO
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from app.database.database import get_db
from app.models.vital import Vital
from app.models.alert import Alert
from app.models.patient import Patient
from app.config.config import DATA_ROOT

router = APIRouter(prefix="/vital", tags=["生命体征"])

BINGLI_ROOT = os.path.join(DATA_ROOT, "bingli")
os.makedirs(BINGLI_ROOT, exist_ok=True)


# ==============================
# Pydantic 请求体模型
# ==============================
class PatientUpdate(BaseModel):
    device_id: str
    patient_name: str = ""
    gender: str = ""
    age: Optional[int] = None
    department: str = ""
    hospital: str = ""
    id_card: str = ""
    phone: str = ""
    diagnosis: str = ""
    admission_time: str = ""
    doctor: str = ""
    note: str = ""
    photo: str = ""


class AvatarUpdate(BaseModel):
    device_id: str
    photo: str


# ==============================
# 工具：报警文本智能解析 & 分级
# ==============================
ALARM_RULES = [
    # (关键词列表, 分类, 级别, 简明提示)
    # 级别：P0 致命 / P1 紧急 / P2 关注 / P3 提示
    (["停搏", "asystole", "ASYS", "心脏停搏"], "心率异常", "P0", "⚠️ 心脏停搏！立即抢救"),
    (["室颤", "ventricular", "fibrillation", "VF"], "心率异常", "P0", "⚠️ 心室颤动，致命心律"),
    (["心动过速", "tachy", "TACHY", "HR HIGH", "心率高"], "心率异常", "P1", "心率过速（HR > 100）"),
    (["心动过缓", "brady", "BRADY", "HR LOW", "心率低"], "心率异常", "P1", "心率过缓（HR < 60）"),
    (["心律失常", "arrhythmia", "irregular"], "心率异常", "P2", "心律不规则，需关注"),

    (["spO2 LOW", "SPO2 LOW", "SpO2 低", "血氧低", "低氧", "hypoxia"], "血氧异常", "P1", "血氧过低（SpO2 < 90%）"),
    (["spO2 HIGH", "SPO2 HIGH", "血氧高"], "血氧异常", "P3", "血氧偏高，一般无危险"),

    (["SYS HIGH", "sys high", "收缩压高", "血压高", "hypertension"], "血压异常", "P1", "收缩压过高（SYS > 160）"),
    (["SYS LOW", "sys low", "收缩压低", "血压低", "hypotension"], "血压异常", "P1", "收缩压过低（SYS < 90）"),
    (["DIA HIGH", "dia high", "舒张压高"], "血压异常", "P2", "舒张压偏高"),
    (["DIA LOW", "dia low", "舒张压低"], "血压异常", "P2", "舒张压偏低"),

    (["RESP HIGH", "resp high", "RR HIGH", "呼吸高", "呼吸急促", "tachypnea"], "呼吸异常", "P1", "呼吸过速（RR > 25）"),
    (["RESP LOW", "resp low", "RR LOW", "呼吸低", "呼吸过缓", "bradypnea"], "呼吸异常", "P1", "呼吸过缓（RR < 10）"),
    (["窒息", "apnea", "APNEA"], "呼吸异常", "P0", "⚠️ 呼吸暂停/窒息！"),

    (["TEMP HIGH", "temp high", "体温高", "发热", "fever"], "体温异常", "P2", "体温过高（T > 38.5℃）"),
    (["TEMP LOW", "temp low", "体温低", "hypothermia"], "体温异常", "P2", "体温过低（T < 36℃）"),

    (["探头脱落", "探头移除", "LEAD OFF", "lead off", "电极脱落", "电极移除", "脱落"], "设备连接", "P2", "电极/探头脱落，检查导联"),
    (["信号丢失", "no signal", "SIGNAL", "信号弱"], "设备连接", "P3", "信号异常，检查设备连接"),
    (["电量低", "battery low", "BATTERY"], "设备连接", "P3", "监护仪电量不足"),
    (["NIBP 失败", "nibp failed", "血压测量失败"], "设备连接", "P3", "无创血压测量失败"),
]

SEVERITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
SEVERITY_LABEL = {"P0": "🚨 致命", "P1": "🔥 紧急", "P2": "⚠️ 关注", "P3": "ℹ️ 提示"}
SEVERITY_COLOR = {"P0": "#ff0055", "P1": "#ff8800", "P2": "#ffcc00", "P3": "#00ccff"}


def analyze_alarm(alarm_text: str):
    """解析一条报警文本，返回 (级别, 分类, 简明提示)"""
    text = (alarm_text or "").upper()
    match = None
    for keywords, category, severity, hint in ALARM_RULES:
        if any(k.upper() in text for k in keywords):
            match = (category, severity, hint)
            if severity == "P0":
                break  # 致命级别直接命中
    if not match:
        match = ("其他报警", "P3", "未分类报警：" + (alarm_text or "—"))
    return match


# ==============================
# 工具：行 -> dict
# ==============================
def _vital_to_dict(v: Vital):
    return {
        "time": v.created.strftime("%H:%M:%S"),
        "fulltime": v.created.strftime("%Y-%m-%d %H:%M:%S"),
        "device_id": v.device_id,
        "patient_name": v.patient_name,
        "hr": v.hr, "spo2": v.spo2, "rr": v.rr,
        "temp": v.temp, "sys": v.sys, "dia": v.dia, "map": v.map,
    }


def _alert_to_dict(a: Alert):
    category, severity, hint = analyze_alarm(a.alarm_text)
    return {
        "id": a.id,
        "time": a.created.strftime("%H:%M:%S"),
        "fulltime": a.created.strftime("%Y-%m-%d %H:%M:%S"),
        "device_id": a.device_id,
        "alarm_text": a.alarm_text,
        "severity": severity,
        "severity_label": SEVERITY_LABEL.get(severity, severity),
        "severity_color": SEVERITY_COLOR.get(severity, "#fff"),
        "category": category,
        "hint": hint,
        "_order": SEVERITY_ORDER.get(severity, 9),
    }


def _patient_to_dict(p: Patient):
    return {
        "device_id": p.device_id,
        "patient_name": p.patient_name,
        "gender": p.gender,
        "age": p.age,
        "department": p.department,
        "hospital": p.hospital,
        "bed_id": p.bed_id,
        "id_card": p.id_card,
        "phone": p.phone,
        "diagnosis": p.diagnosis,
        "admission_time": p.admission_time,
        "doctor": p.doctor,
        "note": p.note,
        "photo": p.photo or "",
        "created": p.created.strftime("%Y-%m-%d %H:%M:%S") if p.created else "",
        "updated": p.updated.strftime("%Y-%m-%d %H:%M:%S") if p.updated else "",
    }


# ==============================
# 体征与报警查询
# ==============================
@router.get("/history")
def get_history(
    device_id: str = Query(None),
    hours: int = Query(24),
    limit: int = Query(1000),
    db: Session = Depends(get_db),
):
    end = datetime.now()
    start = end - timedelta(hours=hours)
    q = db.query(Vital).filter(Vital.created >= start)
    if device_id:
        q = q.filter(Vital.device_id == device_id)
    records = q.order_by(Vital.created).limit(limit).all()
    return [_vital_to_dict(r) for r in records]


@router.get("/latest")
def get_latest(device_id: str = Query(None), db: Session = Depends(get_db)):
    if device_id:
        r = db.query(Vital).filter(Vital.device_id == device_id)\
            .order_by(Vital.created.desc()).first()
        return [_vital_to_dict(r)] if r else []
    device_ids = [d[0] for d in db.query(Vital.device_id).distinct().all()]
    result = []
    for did in device_ids:
        r = db.query(Vital).filter(Vital.device_id == did)\
            .order_by(Vital.created.desc()).first()
        if r:
            result.append(_vital_to_dict(r))
    return result


@router.get("/alerts")
def get_alerts(
    device_id: str = Query(None),
    hours: int = Query(24),
    db: Session = Depends(get_db),
):
    end = datetime.now()
    start = end - timedelta(hours=hours)
    q = db.query(Alert).filter(Alert.created >= start)
    if device_id:
        q = q.filter(Alert.device_id == device_id)
    records = q.order_by(Alert.created).all()
    parsed = [_alert_to_dict(r) for r in records]
    parsed.sort(key=lambda x: (x["_order"], x["fulltime"]))
    return parsed


# ==============================
# 患者档案 CRUD
# ==============================
@router.get("/patient")
def get_patient(device_id: str = Query(...), db: Session = Depends(get_db)):
    p = db.query(Patient).filter(Patient.device_id == device_id).first()
    if not p:
        # 尝试从最近一条体征中取患者姓名作为默认
        v = db.query(Vital).filter(Vital.device_id == device_id)\
            .order_by(Vital.created.desc()).first()
        return {
            "device_id": device_id,
            "patient_name": v.patient_name if v and v.patient_name else "",
            "gender": "", "age": None, "department": "", "hospital": "", "bed_id": "",
            "id_card": "", "phone": "", "diagnosis": "",
            "admission_time": "", "doctor": "", "note": "", "photo": "",
            "created": "", "updated": "",
        }
    return _patient_to_dict(p)


@router.post("/patient")
def upsert_patient(payload: PatientUpdate, db: Session = Depends(get_db)):
    p = db.query(Patient).filter(Patient.device_id == payload.device_id).first()
    if not p:
        p = Patient(device_id=payload.device_id)
        db.add(p)
    p.patient_name = payload.patient_name
    p.gender = payload.gender
    p.age = payload.age
    p.department = payload.department
    p.hospital = payload.hospital
    p.bed_id = payload.bed_id
    p.id_card = payload.id_card
    p.phone = payload.phone
    p.diagnosis = payload.diagnosis
    p.admission_time = payload.admission_time
    p.doctor = payload.doctor
    p.note = payload.note
    if payload.photo and str(payload.photo).strip().startswith("data:image"):
        p.photo = payload.photo
    p.updated = datetime.now()
    db.commit()
    return {"ok": True, "msg": "患者档案已保存"}


@router.post("/patient/avatar")
def update_patient_avatar(payload: AvatarUpdate, db: Session = Depends(get_db)):
    """仅更新患者头像（前端裁剪后直接传 base64 Data URI）"""
    photo_str = (payload.photo or "").strip()
    if not photo_str:
        return {"ok": False, "msg": "头像数据为空"}
    if not photo_str.startswith("data:image"):
        return {"ok": False, "msg": "头像格式不支持，请使用图片文件"}
    # 限制大小：约 2MB (base64 后约 2.7M)
    if len(photo_str) > 3000000:
        return {"ok": False, "msg": "图片过大，请选择小一点的图片"}

    p = db.query(Patient).filter(Patient.device_id == payload.device_id).first()
    if not p:
        p = Patient(device_id=payload.device_id)
        db.add(p)
    p.photo = photo_str
    p.updated = datetime.now()
    db.commit()
    return {"ok": True, "msg": "头像已更新", "photo": photo_str}


@router.delete("/patient")
def delete_patient(device_id: str = Query(...), db: Session = Depends(get_db)):
    p = db.query(Patient).filter(Patient.device_id == device_id).first()
    if not p:
        return {"ok": False, "msg": "未找到对应设备的患者档案"}
    db.delete(p)
    db.commit()
    return {"ok": True, "msg": "患者档案已删除"}


# ==============================
# CSV 导出 / 病历归档
# ==============================
@router.get("/export.csv")
def export_csv(
    device_id: str = Query(None),
    hours: int = Query(24),
    db: Session = Depends(get_db),
):
    end = datetime.now()
    start = end - timedelta(hours=hours)
    q = db.query(Vital).filter(Vital.created >= start)
    if device_id:
        q = q.filter(Vital.device_id == device_id)
    records = q.order_by(Vital.created).all()

    buf = StringIO()
    buf.write("时间,设备编号,患者,心率,血氧,呼吸率,体温,收缩压,舒张压,平均压\n")
    for r in records:
        buf.write(",".join([
            r.created.strftime("%Y-%m-%d %H:%M:%S"),
            str(r.device_id or ""),
            str(r.patient_name or ""),
            str(r.hr or ""),
            str(r.spo2 or ""),
            str(r.rr or ""),
            str(r.temp or ""),
            str(r.sys or ""),
            str(r.dia or ""),
            str(r.map or ""),
        ]) + "\n")
    buf.seek(0)
    filename = f"vitals_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        buf,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def _build_bingli_report(device_id: str, hours: int, db: Session) -> str:
    """生成一份完整病历报告（纯文本）"""
    end = datetime.now()
    start = end - timedelta(hours=hours)

    # 患者档案
    patient = db.query(Patient).filter(Patient.device_id == device_id).first()
    # 体征
    vitals = db.query(Vital).filter(Vital.device_id == device_id)\
        .filter(Vital.created >= start).order_by(Vital.created).all()
    # 报警
    alerts = db.query(Alert).filter(Alert.device_id == device_id)\
        .filter(Alert.created >= start).order_by(Alert.created).all()

    # 统计摘要
    hr_list = [v.hr for v in vitals if v.hr and v.hr > 0]
    spo2_list = [v.spo2 for v in vitals if v.spo2 and v.spo2 > 0]
    rr_list = [v.rr for v in vitals if v.rr and v.rr > 0]
    sys_list = [v.sys for v in vitals if v.sys and v.sys > 0]
    dia_list = [v.dia for v in vitals if v.dia and v.dia > 0]
    temp_list = [v.temp for v in vitals if v.temp and v.temp > 0]

    def _stat(lst):
        if not lst:
            return "—"
        return f"min={min(lst)} / max={max(lst)} / avg={sum(lst)/len(lst):.1f} / 样本={len(lst)}"

    # 报警分级统计
    alert_by_level = {}
    for a in alerts:
        _, sev, _ = analyze_alarm(a.alarm_text)
        alert_by_level[sev] = alert_by_level.get(sev, 0) + 1

    lines = []
    lines.append("=" * 72)
    lines.append(f"  【病历档案 REPORT】 设备: {device_id}")
    lines.append(f"  生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"  统计范围: 近 {hours} 小时 ({start.strftime('%Y-%m-%d %H:%M')} ~ 今)")
    lines.append("=" * 72)

    lines.append("\n【1】患者信息")
    if patient:
        lines.append(f"  姓名      : {patient.patient_name or '—'}")
        lines.append(f"  性别/年龄 : {patient.gender or '—'} / {patient.age or '—'}")
        lines.append(f"  科室/床位 : {patient.department or '—'} / {patient.bed_id or '—'}")
        lines.append(f"  身份证号  : {patient.id_card or '—'}")
        lines.append(f"  联系电话  : {patient.phone or '—'}")
        lines.append(f"  入院时间  : {patient.admission_time or '—'}")
        lines.append(f"  主管医生  : {patient.doctor or '—'}")
        lines.append(f"  诊断/主诉 : {patient.diagnosis or '—'}")
        lines.append(f"  备注      : {patient.note or '—'}")
    else:
        lines.append("  （暂无患者档案，可在前端录入后再次归档）")

    lines.append("\n【2】实时体征（最新一条）")
    if vitals:
        latest = vitals[-1]
        lines.append(f"  测量时间 : {latest.created.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"  心率 HR  : {latest.hr or '—'} bpm")
        lines.append(f"  血氧 SpO2: {latest.spo2 or '—'} %")
        lines.append(f"  呼吸率 RR: {latest.rr or '—'} rpm")
        lines.append(f"  体温 Temp: {latest.temp or '—'} ℃")
        lines.append(f"  血压 NIBP: {latest.sys or '—'}/{latest.dia or '—'} mmHg  (MAP {latest.map or '—'})")
    else:
        lines.append("  （此时间范围内无体征数据）")

    lines.append("\n【3】体征统计摘要")
    lines.append(f"  心率 HR   : {_stat(hr_list)}")
    lines.append(f"  血氧 SpO2 : {_stat(spo2_list)}")
    lines.append(f"  呼吸率 RR : {_stat(rr_list)}")
    lines.append(f"  收缩压 SYS: {_stat(sys_list)}")
    lines.append(f"  舒张压 DIA: {_stat(dia_list)}")
    lines.append(f"  体温 TEMP : {_stat(temp_list)}")

    lines.append("\n【4】报警事件（共 " + str(len(alerts)) + " 条）")
    lines.append("  分级统计: " + ", ".join(f"{SEVERITY_LABEL.get(k,k)} {v}条" for k, v in sorted(alert_by_level.items())))
    lines.append("")
    if alerts:
        for a in alerts:
            cat, sev, hint = analyze_alarm(a.alarm_text)
            lines.append(f"  [{a.created.strftime('%Y-%m-%d %H:%M:%S')}] "
                         f"{SEVERITY_LABEL.get(sev, sev)} | {cat} | {hint}")
            lines.append(f"      原文: {a.alarm_text}")
    else:
        lines.append("  （无报警事件）")

    lines.append("\n【5】完整体征流（CSV 节选）")
    lines.append("时间,HR,SpO2,RR,Temp,SYS,DIA,MAP")
    for v in vitals:
        lines.append(f"{v.created.strftime('%Y-%m-%d %H:%M:%S')},"
                     f"{v.hr or ''},{v.spo2 or ''},{v.rr or ''},"
                     f"{v.temp or ''},{v.sys or ''},{v.dia or ''},{v.map or ''}")

    lines.append("\n" + "=" * 72)
    lines.append("  本报告由 OpenMonitor Pro 自动生成，仅供临床参考。")
    lines.append("=" * 72)
    return "\n".join(lines)


@router.post("/archive")
def archive_bingli(
    device_id: str = Query(...),
    hours: int = Query(24),
    db: Session = Depends(get_db),
):
    """将指定设备的病历归档到 data/bingli/ 文件夹"""
    report = _build_bingli_report(device_id, hours, db)
    date_str = datetime.now().strftime("%Y%m%d")
    # 以设备编号+日期命名子文件夹
    safe_dev = "".join(c if c.isalnum() or c in "-_" else "_" for c in (device_id or "unknown"))
    target_dir = os.path.join(BINGLI_ROOT, f"{date_str}_{safe_dev}")
    os.makedirs(target_dir, exist_ok=True)
    filename = f"bingli_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    filepath = os.path.join(target_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(report)

    # 同时写入 CSV 副本
    csv_name = f"vitals_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    csv_path = os.path.join(target_dir, csv_name)
    end = datetime.now()
    start = end - timedelta(hours=hours)
    vitals = db.query(Vital).filter(Vital.device_id == device_id)\
        .filter(Vital.created >= start).order_by(Vital.created).all()
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write("时间,设备,姓名,HR,SpO2,RR,Temp,SYS,DIA,MAP\n")
        for v in vitals:
            f.write(",".join([
                v.created.strftime("%Y-%m-%d %H:%M:%S"),
                str(v.device_id or ""),
                str(v.patient_name or ""),
                str(v.hr or ""), str(v.spo2 or ""), str(v.rr or ""),
                str(v.temp or ""), str(v.sys or ""), str(v.dia or ""), str(v.map or ""),
            ]) + "\n")

    return {
        "ok": True,
        "archive_dir": target_dir,
        "report_file": filepath,
        "csv_file": csv_path,
        "vital_count": len(vitals),
    }


@router.get("/archive/list")
def list_archives():
    """列出 data/bingli/ 下所有归档"""
    result = []
    if not os.path.exists(BINGLI_ROOT):
        return result
    for d in sorted(os.listdir(BINGLI_ROOT), reverse=True):
        full = os.path.join(BINGLI_ROOT, d)
        if not os.path.isdir(full):
            continue
        files = sorted(os.listdir(full))
        result.append({"folder": d, "files": files, "path": full})
    return result


@router.get("/archive/download")
def download_archive(folder: str = Query(...), filename: str = Query(...)):
    """下载指定归档文件"""
    target = os.path.join(BINGLI_ROOT, folder, filename)
    if not os.path.exists(target) or not os.path.isfile(target):
        raise HTTPException(status_code=404, detail="归档文件不存在")
    return FileResponse(target, filename=filename, media_type="text/plain; charset=utf-8")


@router.get("/devices")
def list_devices(hours: int = Query(48), db: Session = Depends(get_db)):
    """返回所有已知设备列表（带计数）"""
    end = datetime.now()
    start = end - timedelta(hours=hours)
    rows = db.query(
        Vital.device_id,
        Vital.patient_name,
    ).distinct().all()
    p_rows = db.query(
        Patient.device_id,
        Patient.patient_name,
    ).distinct().all()

    seen = {}
    for dev_id, p_name in rows:
        if not dev_id:
            continue
        seen[dev_id] = {"patient_name": p_name or ""}
    for dev_id, p_name in p_rows:
        if not dev_id:
            continue
        if dev_id not in seen:
            seen[dev_id] = {"patient_name": p_name or ""}
        elif p_name and not seen[dev_id].get("patient_name"):
            seen[dev_id]["patient_name"] = p_name

    devices = []
    for dev_id in sorted(seen.keys()):
        info = seen[dev_id]
        count = db.query(Vital).filter(Vital.device_id == dev_id).filter(Vital.created >= start).count()
        devices.append({
            "id": dev_id,
            "label": f"{dev_id} ({info.get('patient_name') or '未绑定'})",
            "patient_name": info.get("patient_name") or "",
            "count": count,
        })
    return {"devices": devices}


# ==============================
# 网络连通性测试
# ==============================
class NetworkTest(BaseModel):
    host: str = "127.0.0.1"
    port: int = 2575

@router.post("/ping")
def ping_device(payload: NetworkTest):
    """测试 TCP 端口可达性（不依赖系统 ping 命令）"""
    import socket
    start_ts = datetime.now()
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3.0)
        sock.connect((payload.host, payload.port))
        sock.close()
        latency_ms = int((datetime.now() - start_ts).total_seconds() * 1000)
        return {"ok": True, "host": payload.host, "port": payload.port,
                "latency_ms": latency_ms, "msg": "TCP 端口可达"}
    except Exception as e:
        return {"ok": False, "host": payload.host, "port": payload.port,
                "latency_ms": 0, "msg": "连接失败: " + str(e)}


@router.get("/health")
def health_check():
    """服务健康检查（前端可用于判断后台是否响应）"""
    return {"ok": True, "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "version": "4.2 Neon-Dream"}