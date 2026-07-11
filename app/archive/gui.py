"""
监护仪历史档案管理器 - GUI 版本
===================================

基于 Python tkinter 的跨平台图形界面，无需额外安装依赖。
功能涵盖：
    - 设备列表与状态监控
    - 生命体征数据查询（含患者信息/科室/诊断）
    - 危险数值红色标星标记
    - 报警记录智能解析（迈瑞 MDC 编码 → 中文）
    - 双击任意行打开详情对话框，可打印
    - 删除按钮：人工清理不合理数据
    - 统计分析与越限评估
    - CSV / JSON 数据导出
    - 趋势图与报警统计图（需 matplotlib）
    - 修复 FigureCanvasTkAgg 的 destroy 属性问题

运行方式：
    python -m app.archive.gui
    或
    python start_archive.py   (项目根目录启动脚本)
"""

import os
import sys
import json
import csv
import threading
import tempfile
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

# 尝试导入项目模块
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(_current_dir))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

try:
    from app.archive.history_manager import (
        HistoryArchiveManager, VitalRecord, AlarmRecord,
        DeviceRecord, StatisticsReport, VITAL_NORMALS, check_abnormal,
    )
    _MODULE_OK = True
except Exception as e:
    _MODULE_OK = False
    _MODULE_ERROR = str(e)

# matplotlib 可选
try:
    import matplotlib
    matplotlib.use("TkAgg")
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib import rcParams
    rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    rcParams["axes.unicode_minus"] = False
    _MPL_AVAILABLE = True
except Exception:
    _MPL_AVAILABLE = False

# 参数中文映射
_PARAM_LABELS = {
    "hr": "心率", "spo2": "血氧", "rr": "呼吸", "temp": "体温",
    "sys": "收缩压", "dia": "舒张压", "map": "平均压",
}
_PARAM_UNIT = {
    "hr": "bpm", "spo2": "%", "rr": "rpm", "temp": "℃",
    "sys": "mmHg", "dia": "mmHg", "map": "mmHg",
}


def _fmt_value(param: str, v: float, ab: str) -> str:
    if v <= 0:
        return "-"
    suffix = " ★" if ab else ""
    if param == "temp":
        return f"{v:.1f}{suffix}"
    return f"{v:.0f}{suffix}"


def _category_cn(cat: str) -> str:
    m = {"physiological": "生理", "technical": "技术",
         "arrhythmia": "心律失常", "other": "其他"}
    return m.get(cat or "", cat or "-")


class ArchiveApp(tk.Tk):
    """档案管理器主窗口"""

    def __init__(self):
        super().__init__()
        self.title("监护仪历史档案管理器")
        self.geometry("1440x900")
        self.minsize(1200, 700)
        self.configure(bg="#eef2f7")

        self.manager: Optional[HistoryArchiveManager] = None
        self._devices: List[DeviceRecord] = []
        self._vitals_cache: List[VitalRecord] = []
        self._alarms_cache: List[AlarmRecord] = []
        self._chart_canvas = None
        self._chart_figure = None
        self._chart_window_pos: Optional[str] = None

        self._build_ui()
        self.after(80, self._safe_init_manager)

    # ================================================================
    # UI 构建
    # ================================================================
    def _build_ui(self):
        # 顶部标题栏
        header = tk.Frame(self, bg="#1e3a5f", height=60)
        header.pack(fill="x", side="top")
        tk.Label(header, text="🩺 监护仪历史档案管理器",
                font=("Microsoft YaHei", 15, "bold"),
                bg="#1e3a5f", fg="white").pack(side="left", padx=16, pady=12)
        self.header_status = tk.Label(header, text="正在初始化...",
                                      font=("Microsoft YaHei", 9),
                                      bg="#1e3a5f", fg="#a8c5e8")
        self.header_status.pack(side="right", padx=16)

        # 总览卡片
        summary = tk.Frame(self, bg="#eef2f7")
        summary.pack(fill="x", padx=12, pady=(8, 0))
        self._summary_labels: Dict[str, tk.Label] = {}
        for key, title in [("db", "数据库"), ("vital", "生命体征"),
                           ("alarm", "报警记录"), ("dev", "接入设备")]:
            card = tk.Frame(summary, bg="white", highlightthickness=1,
                          highlightbackground="#cfd8dc")
            card.pack(side="left", expand=True, fill="x", padx=6)
            tk.Label(card, text=title, font=("Microsoft YaHei", 9),
                    bg="white", fg="#546e7a").pack(pady=(6, 0))
            lbl = tk.Label(card, text="-", font=("Microsoft YaHei", 14, "bold"),
                          bg="white", fg="#1e3a5f")
            lbl.pack(pady=(0, 6))
            self._summary_labels[key] = lbl

        # 设备选择栏
        devbar = tk.Frame(self, bg="white", highlightthickness=1,
                        highlightbackground="#cfd8dc")
        devbar.pack(fill="x", padx=12, pady=(8, 0))
        tk.Label(devbar, text="当前设备:", font=("Microsoft YaHei", 10, "bold"),
                bg="white", fg="#1e3a5f").pack(side="left", padx=12, pady=10)
        self.device_combo = ttk.Combobox(devbar, width=60, state="readonly",
                                        font=("Microsoft YaHei", 10))
        self.device_combo.pack(side="left", padx=4, pady=10)
        ttk.Button(devbar, text="🔄 刷新",
                  command=self._refresh_all).pack(side="left", padx=6)
        ttk.Button(devbar, text="⬇ 导出 CSV(生命体征)",
                  command=lambda: self._quick_export("vitals")
                  ).pack(side="left", padx=6)
        ttk.Button(devbar, text="⬇ 导出 CSV(报警)",
                  command=lambda: self._quick_export("alarms")
                  ).pack(side="left", padx=6)

        # 选项卡
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=12, pady=8)

        self._build_vitals_tab()
        self._build_alarms_tab()
        self._build_analysis_tab()
        self._build_chart_tab()
        self._build_export_tab()

        # 状态栏
        self.status_var = tk.StringVar(value="就绪")
        tk.Label(self, textvariable=self.status_var, bg="#cfd8dc",
                font=("Microsoft YaHei", 9), fg="#37474f", anchor="w",
                ).pack(fill="x", side="bottom", ipady=3)

    def _build_vitals_tab(self):
        frame = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(frame, text="  🩺 生命体征  ")

        q = tk.Frame(frame, bg="white", highlightthickness=1,
                    highlightbackground="#cfd8dc")
        q.pack(fill="x")

        self.v_start = tk.Entry(q, width=20, font=("Microsoft YaHei", 9))
        self.v_end = tk.Entry(q, width=20, font=("Microsoft YaHei", 9))
        self.v_patient = tk.Entry(q, width=14, font=("Microsoft YaHei", 9))
        self.v_limit = tk.Spinbox(q, from_=10, to=50000, width=7,
                                  font=("Microsoft YaHei", 9))
        self.v_limit.delete(0, "end")
        self.v_limit.insert(0, "500")

        def _grid_field(col, label, widget):
            tk.Label(q, text=label, font=("Microsoft YaHei", 9),
                    bg="white", fg="#37474f").grid(row=0, column=col * 2,
                    padx=(10, 4), pady=8, sticky="e")
            widget.grid(row=0, column=col * 2 + 1, padx=(0, 10), pady=8, sticky="w")

        _grid_field(0, "起始时间", self.v_start)
        _grid_field(1, "结束时间", self.v_end)
        _grid_field(2, "患者姓名", self.v_patient)
        _grid_field(3, "显示条数", self.v_limit)

        ttk.Button(q, text="🔍 查询", command=self._query_vitals
                  ).grid(row=0, column=8, padx=6)
        ttk.Button(q, text="⚠ 仅显示异常", command=self._filter_abnormal_vitals
                  ).grid(row=0, column=9, padx=6)
        ttk.Button(q, text="🗑 删除选中", command=self._delete_selected_vitals
                  ).grid(row=0, column=10, padx=6)

        tip = tk.Label(frame,
                 text="💡 红色行 = 有参数越上限；黄色行 = 有参数越下限；数字后的 ★ = 该单项越限。双击任意行可打开详情/打印。",
                 font=("Microsoft YaHei", 9), bg="#eef2f7", fg="#546e7a", anchor="w")
        tip.pack(fill="x", pady=(4, 0))

        table_wrap = tk.Frame(frame, bg="white", highlightthickness=1,
                             highlightbackground="#cfd8dc")
        table_wrap.pack(fill="both", expand=True, pady=(4, 0))

        columns = ("id", "timestamp", "device_id", "patient_name",
                   "department", "bed_id", "doctor",
                   "hr", "spo2", "rr", "temp", "sys", "dia", "map", "diagnosis")
        headers = ("ID", "时间", "设备", "患者", "科室", "床位", "医生",
                   "心率", "血氧", "呼吸", "体温", "收缩压", "舒张压", "平均压", "监护仪检测")
        widths = (55, 160, 140, 100, 80, 55, 80,
                  65, 65, 65, 70, 70, 70, 70, 280)

        self.vitals_tree = ttk.Treeview(table_wrap, columns=columns,
                                       show="headings", height=16, selectmode="extended")
        for c, h, w in zip(columns, headers, widths):
            self.vitals_tree.heading(c, text=h)
            self.vitals_tree.column(c, width=w, anchor="center")
        self.vitals_tree.tag_configure("red", background="#ffebee", foreground="#c62828")
        self.vitals_tree.tag_configure("yellow", background="#fff8dc", foreground="#ef6c00")
        self.vitals_tree.tag_configure("normal", background="white")

        vsb = ttk.Scrollbar(table_wrap, orient="vertical",
                           command=self.vitals_tree.yview)
        hsb = ttk.Scrollbar(table_wrap, orient="horizontal",
                           command=self.vitals_tree.xview)
        self.vitals_tree.configure(yscroll=vsb.set, xscroll=hsb.set)
        self.vitals_tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        self.vitals_tree.bind("<Double-1>",
                              lambda e: self._show_vital_detail(e))

        self.vitals_count_label = tk.Label(frame, text="共 0 条",
                                          font=("Microsoft YaHei", 9),
                                          fg="#37474f", anchor="w")
        self.vitals_count_label.pack(fill="x", pady=(4, 0))

    def _build_alarms_tab(self):
        frame = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(frame, text="  ⚠ 报警记录  ")

        q = tk.Frame(frame, bg="white", highlightthickness=1,
                    highlightbackground="#cfd8dc")
        q.pack(fill="x")

        self.a_start = tk.Entry(q, width=20, font=("Microsoft YaHei", 9))
        self.a_end = tk.Entry(q, width=20, font=("Microsoft YaHei", 9))
        self.a_keyword = tk.Entry(q, width=14, font=("Microsoft YaHei", 9))
        self.a_limit = tk.Spinbox(q, from_=10, to=50000, width=7,
                                  font=("Microsoft YaHei", 9))
        self.a_limit.delete(0, "end")
        self.a_limit.insert(0, "500")

        def _grid_field(col, label, widget):
            tk.Label(q, text=label, font=("Microsoft YaHei", 9),
                    bg="white", fg="#37474f").grid(row=0, column=col * 2,
                    padx=(10, 4), pady=8, sticky="e")
            widget.grid(row=0, column=col * 2 + 1, padx=(0, 10), pady=8, sticky="w")

        _grid_field(0, "起始时间", self.a_start)
        _grid_field(1, "结束时间", self.a_end)
        _grid_field(2, "关键词", self.a_keyword)
        _grid_field(3, "显示条数", self.a_limit)

        ttk.Button(q, text="🔍 查询", command=self._query_alarms
                  ).grid(row=0, column=8, padx=6)
        ttk.Button(q, text="🗑 删除选中", command=self._delete_selected_alarms
                  ).grid(row=0, column=9, padx=6)

        tip = tk.Label(frame,
                 text="💡 报警内容已从迈瑞 MDC 编码智能解析为中文。'级别'列颜色标识严重程度；'解析内容'是可读的中文描述。双击任意行可查看详情/打印。",
                 font=("Microsoft YaHei", 9), bg="#eef2f7", fg="#546e7a", anchor="w")
        tip.pack(fill="x", pady=(4, 0))

        table_wrap = tk.Frame(frame, bg="white", highlightthickness=1,
                             highlightbackground="#cfd8dc")
        table_wrap.pack(fill="both", expand=True, pady=(4, 0))

        columns = ("id", "timestamp", "device_id", "level", "category",
                  "parsed", "mdc_code", "param_name", "alarm_text")
        headers = ("ID", "时间", "设备", "级别", "分类", "解析内容",
                  "MDC编码", "参数", "原始内容")
        widths = (55, 160, 130, 110, 90, 420, 90, 120, 420)

        self.alarms_tree = ttk.Treeview(table_wrap, columns=columns,
                                       show="headings", height=16, selectmode="extended")
        for c, h, w in zip(columns, headers, widths):
            self.alarms_tree.heading(c, text=h)
            align = "w" if c in ("parsed", "alarm_text", "param_name") else "center"
            self.alarms_tree.column(c, width=w, anchor=align)

        self.alarms_tree.tag_configure("red", background="#ffebee", foreground="#c62828")
        self.alarms_tree.tag_configure("yellow", background="#fff8dc", foreground="#ef6c00")
        self.alarms_tree.tag_configure("tech", background="#e8f5e9")
        self.alarms_tree.tag_configure("arr", background="#fce4ec")
        self.alarms_tree.tag_configure("white", background="white")

        vsb = ttk.Scrollbar(table_wrap, orient="vertical",
                           command=self.alarms_tree.yview)
        hsb = ttk.Scrollbar(table_wrap, orient="horizontal",
                           command=self.alarms_tree.xview)
        self.alarms_tree.configure(yscroll=vsb.set, xscroll=hsb.set)
        self.alarms_tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")

        self.alarms_tree.bind("<Double-1>",
                             lambda e: self._show_alarm_detail(e))

        self.alarms_count_label = tk.Label(frame, text="共 0 条",
                                          font=("Microsoft YaHei", 9),
                                          fg="#37474f", anchor="w")
        self.alarms_count_label.pack(fill="x", pady=(4, 0))

    def _build_analysis_tab(self):
        frame = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(frame, text="  📊 统计分析  ")

        ctrl = tk.Frame(frame, bg="white", highlightthickness=1,
                       highlightbackground="#cfd8dc")
        ctrl.pack(fill="x")
        tk.Label(ctrl, text="范围:", font=("Microsoft YaHei", 10, "bold"),
                bg="white", fg="#1e3a5f").pack(side="left", padx=12, pady=10)
        self.an_start = tk.Entry(ctrl, width=20, font=("Microsoft YaHei", 9))
        self.an_start.pack(side="left", padx=4, pady=10)
        tk.Label(ctrl, text="~", bg="white").pack(side="left")
        self.an_end = tk.Entry(ctrl, width=20, font=("Microsoft YaHei", 9))
        self.an_end.pack(side="left", padx=4, pady=10)
        ttk.Button(ctrl, text="开始分析", command=self._run_analysis).pack(side="left", padx=12)

        table_wrap = tk.Frame(frame, bg="white", highlightthickness=1,
                             highlightbackground="#cfd8dc")
        table_wrap.pack(fill="both", expand=True, pady=(8, 0))

        columns = ("param", "count", "mean", "min", "max", "median",
                  "range", "low_cnt", "high_cnt", "rate")
        headers = ("参数", "样本", "均值", "最小", "最大", "中位数",
                  "正常范围", "越下限", "越上限", "越限率")
        widths = (100, 80, 100, 100, 100, 100, 120, 80, 80, 100)

        self.analysis_tree = ttk.Treeview(table_wrap, columns=columns,
                                         show="headings", height=10)
        for c, h, w in zip(columns, headers, widths):
            self.analysis_tree.heading(c, text=h)
            self.analysis_tree.column(c, width=w, anchor="center")
        self.analysis_tree.tag_configure("red", background="#ffebee")
        self.analysis_tree.tag_configure("yellow", background="#fff8dc")
        self.analysis_tree.tag_configure("green", background="#e8f5e9")
        self.analysis_tree.pack(side="left", fill="both", expand=True)

        sb = ttk.Scrollbar(table_wrap, orient="vertical",
                          command=self.analysis_tree.yview)
        self.analysis_tree.configure(yscroll=sb.set)
        sb.pack(side="right", fill="y")

        sum2 = tk.Frame(frame, bg="white", highlightthickness=1,
                       highlightbackground="#cfd8dc")
        sum2.pack(fill="x", pady=(8, 0))
        tk.Label(sum2, text="报警汇总:", font=("Microsoft YaHei", 11, "bold"),
                bg="white", fg="#1e3a5f").pack(side="left", padx=10, pady=10)
        self.alarm_sum_labels: Dict[str, tk.Label] = {}
        for key, title in [
            ("total", "总数"), ("red", "🔴高危"),
            ("yellow", "🟡中危"), ("white", "⚪提示"),
            ("physiological", "生理"), ("technical", "技术"),
            ("arrhythmia", "心律失常"),
        ]:
            lbl = tk.Label(sum2, text=f"{title}: 0",
                          font=("Microsoft YaHei", 10, "bold"),
                          bg="white", fg="#37474f")
            lbl.pack(side="left", padx=12, pady=10)
            self.alarm_sum_labels[key] = lbl

    def _build_chart_tab(self):
        frame = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(frame, text="  📈 可视化图表  ")

        if _MPL_AVAILABLE:
            ctrl = tk.Frame(frame, bg="white", highlightthickness=1,
                           highlightbackground="#cfd8dc")
            ctrl.pack(fill="x")
            tk.Label(ctrl, text="图表:", font=("Microsoft YaHei", 10, "bold"),
                    bg="white", fg="#1e3a5f").pack(side="left", padx=12, pady=10)
            self.chart_type = tk.StringVar(value="trend")
            ttk.Radiobutton(ctrl, text="生命体征趋势",
                           variable=self.chart_type,
                           value="trend").pack(side="left", padx=6, pady=10)
            ttk.Radiobutton(ctrl, text="报警统计柱图",
                           variable=self.chart_type,
                           value="alarm").pack(side="left", padx=6, pady=10)

            tk.Label(ctrl, text="小时数:", bg="white",
                    font=("Microsoft YaHei", 10)).pack(side="left", padx=14)
            self.chart_hours = tk.Spinbox(ctrl, from_=1, to=1000, width=6,
                                         font=("Microsoft YaHei", 10))
            self.chart_hours.delete(0, "end")
            self.chart_hours.insert(0, "48")
            self.chart_hours.pack(side="left", padx=6, pady=10)

            ttk.Button(ctrl, text="生成图表", command=self._gen_chart
                      ).pack(side="left", padx=12)
            ttk.Button(ctrl, text="保存PNG", command=self._save_chart
                      ).pack(side="left", padx=4)
            ttk.Button(ctrl, text="🖨 打印", command=self._print_chart
                      ).pack(side="left", padx=4)

            self.chart_holder = tk.Frame(frame, bg="white",
                                        highlightthickness=1,
                                        highlightbackground="#cfd8dc")
            self.chart_holder.pack(fill="both", expand=True, pady=(8, 0))

            hint = tk.Label(frame,
                     text="💡 提示：请先选择具体设备，再点击'生成图表'。趋势图显示心率/血氧/呼吸的小时平均值，异常点以红色标注。",
                     font=("Microsoft YaHei", 9), bg="#eef2f7", fg="#546e7a", anchor="w")
            hint.pack(fill="x", pady=(4, 0))
        else:
            tk.Label(frame,
                    text="⚠ 图表功能需要 matplotlib 库。\n\n请在命令行执行:\n\n  pip install matplotlib\n\n安装完成后重新启动程序。",
                    font=("Microsoft YaHei", 12), justify="left",
                    bg="#fff8e1", fg="#bf360c", pady=80).pack(fill="both", expand=True)

    def _build_export_tab(self):
        frame = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(frame, text="  💾 数据导出  ")

        opt = tk.Frame(frame, bg="white", highlightthickness=1,
                      highlightbackground="#cfd8dc")
        opt.pack(fill="x")

        tk.Label(opt, text="格式:", font=("Microsoft YaHei", 10, "bold"),
                bg="white", fg="#1e3a5f").pack(side="left", padx=12, pady=12)
        self.export_fmt = tk.StringVar(value="csv_vitals")
        ttk.Radiobutton(opt, text="生命体征 CSV", variable=self.export_fmt,
                       value="csv_vitals").pack(side="left", padx=6, pady=12)
        ttk.Radiobutton(opt, text="报警记录 CSV", variable=self.export_fmt,
                       value="csv_alarms").pack(side="left", padx=6, pady=12)
        ttk.Radiobutton(opt, text="完整 JSON 报告", variable=self.export_fmt,
                       value="json_full").pack(side="left", padx=6, pady=12)
        ttk.Button(opt, text="选择路径并导出",
                  command=self._export_data).pack(side="right", padx=14, pady=8)

        self.export_log = scrolledtext.ScrolledText(frame, height=24,
                                                   font=("Consolas", 10),
                                                   bg="#263238", fg="#eceff1",
                                                   insertbackground="white")
        self.export_log.pack(fill="both", expand=True, pady=(10, 0))

        self._log("导出日志已就绪，请选择格式后点击'选择路径并导出'。")

    # ================================================================
    # 管理器初始化
    # ================================================================
    def _safe_init_manager(self):
        if not _MODULE_OK:
            messagebox.showerror("模块加载失败",
                               f"无法加载 history_manager: {_MODULE_ERROR}")
            self.header_status.config(text="模块加载失败")
            return
        try:
            self.manager = HistoryArchiveManager()
            info = self.manager.get_database_info()
            self._summary_labels["db"].config(
                text=os.path.basename(info.get("db_path", ""))[:22])
            self._summary_labels["vital"].config(
                text=f"{info['tables'].get('vital', 0):,}")
            self._summary_labels["alarm"].config(
                text=f"{info['tables'].get('alert', 0):,}")
            self._summary_labels["dev"].config(
                text=f"{info['tables'].get('device', 0):,}")
            self._refresh_devices()
            self.header_status.config(
                text=f"✅ 数据库连接成功 | {info.get('db_path', '')[:50]}")
            self.status_var.set("就绪 - 选择设备后点击查询")
        except Exception as e:
            self.header_status.config(text="❌ 初始化失败")
            self.status_var.set(f"初始化失败: {e}")
            messagebox.showerror("错误", f"初始化失败: {e}")
            import traceback
            traceback.print_exc()

    def _refresh_devices(self):
        if not self.manager:
            return
        try:
            devices = self.manager.list_devices(True)
            self._devices = devices
            items = ["全部设备 (所有数据汇总)"]
            for d in devices:
                online = "🟢" if d.online else "⚪"
                items.append(
                    f"{online} {d.sn} | {d.ip_addr} "
                    f"| 生命体征 {d.vital_count:,} 条"
                )
            self.device_combo["values"] = items
            if len(items) > 1:
                self.device_combo.current(1)
            else:
                self.device_combo.current(0)
        except Exception as e:
            messagebox.showerror("错误", f"设备列表获取失败: {e}")

    def _selected_device(self) -> Optional[str]:
        text = self.device_combo.get()
        if not text or "全部设备" in text:
            return None
        # 提取设备 SN (格式: "🟢 SN | IP | ...")
        try:
            return text.split("|")[0].strip().lstrip("🟢").lstrip("⚪").strip()
        except Exception:
            return None

    def _refresh_all(self):
        self._safe_init_manager()
        self.status_var.set("已刷新")

    # ================================================================
    # 生命体征查询/显示
    # ================================================================
    def _query_vitals(self):
        if not self.manager:
            return
        self.status_var.set("正在查询生命体征...")
        self.update_idletasks()

        try:
            dev = self._selected_device()
            start = self.v_start.get().strip() or None
            end = self.v_end.get().strip() or None
            patient = self.v_patient.get().strip() or None
            try:
                limit = int(self.v_limit.get())
            except ValueError:
                limit = 500

            records = self.manager.query_vitals(
                device_id=dev, start_time=start, end_time=end,
                patient_name=patient, limit=limit)
            total = self.manager.get_vitals_count(dev, start, end)
            self._vitals_cache = records

            for item in self.vitals_tree.get_children():
                self.vitals_tree.delete(item)

            for rec in records:
                vals = {}
                for p in ("hr", "spo2", "rr", "temp", "sys", "dia", "map"):
                    v = getattr(rec, p)
                    ab = check_abnormal(p, v)
                    vals[p] = (v, ab)

                has_high = any(v[1] == "high" for v in vals.values())
                has_low = any(v[1] == "low" for v in vals.values())
                if has_high:
                    tags = ["red"]
                elif has_low:
                    tags = ["yellow"]
                else:
                    tags = ["normal"]

                self.vitals_tree.insert("", "end", values=(
                    rec.id, str(rec.timestamp)[:19], rec.device_id,
                    rec.patient_name or "-",
                    rec.department or "-",
                    rec.bed_id or "-",
                    rec.doctor or "-",
                    _fmt_value("hr", rec.hr, vals["hr"][1]),
                    _fmt_value("spo2", rec.spo2, vals["spo2"][1]),
                    _fmt_value("rr", rec.rr, vals["rr"][1]),
                    _fmt_value("temp", rec.temp, vals["temp"][1]),
                    _fmt_value("sys", rec.sys, vals["sys"][1]),
                    _fmt_value("dia", rec.dia, vals["dia"][1]),
                    _fmt_value("map", rec.map, vals["map"][1]),
                    rec.diagnosis or "-",
                ), tags=tags)

            self.vitals_count_label.config(
                text=f"共 {total:,} 条记录，当前显示 {len(records)} 条。"
                     f"  ★ = 越限（红色行=有越上限项，黄色行=有越下限项）"
            )
            self.status_var.set(f"✅ 生命体征查询完成，显示 {len(records)} 条")
        except Exception as e:
            self.status_var.set("❌ 查询失败")
            messagebox.showerror("错误", f"查询失败: {e}")
            import traceback
            traceback.print_exc()

    def _filter_abnormal_vitals(self):
        if not self._vitals_cache:
            messagebox.showinfo("提示", "请先查询数据")
            return
        for item in self.vitals_tree.get_children():
            self.vitals_tree.delete(item)
        shown = 0
        for rec in self._vitals_cache:
            val_map = {}
            any_ab = False
            for p in ("hr", "spo2", "rr", "temp", "sys", "dia", "map"):
                v = getattr(rec, p)
                ab = check_abnormal(p, v)
                val_map[p] = (v, ab)
                if ab:
                    any_ab = True
            if not any_ab:
                continue
            has_high = any(v[1] == "high" for v in val_map.values())
            tags = ["red" if has_high else "yellow"]
            shown += 1
            self.vitals_tree.insert("", "end", values=(
                rec.id, str(rec.timestamp)[:19], rec.device_id,
                rec.patient_name or "-", rec.department or "-",
                rec.bed_id or "-", rec.doctor or "-",
                _fmt_value("hr", rec.hr, val_map["hr"][1]),
                _fmt_value("spo2", rec.spo2, val_map["spo2"][1]),
                _fmt_value("rr", rec.rr, val_map["rr"][1]),
                _fmt_value("temp", rec.temp, val_map["temp"][1]),
                _fmt_value("sys", rec.sys, val_map["sys"][1]),
                _fmt_value("dia", rec.dia, val_map["dia"][1]),
                _fmt_value("map", rec.map, val_map["map"][1]),
                rec.diagnosis or "-",
            ), tags=tags)
        self.vitals_count_label.config(
            text=f"已筛选出 {shown} 条越限记录（共 {len(self._vitals_cache)} 条）"
        )

    def _delete_selected_vitals(self):
        sel = self.vitals_tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先选择要删除的行")
            return
        ids = []
        for item in sel:
            vals = self.vitals_tree.item(item, "values")
            try:
                ids.append(int(vals[0]))
            except (ValueError, IndexError):
                pass
        if not ids:
            return
        if not messagebox.askyesno("确认删除",
                f"确定要删除所选 {len(ids)} 条生命体征记录吗？\n此操作不可撤销。"):
            return
        n = self.manager.delete_vitals(ids)
        messagebox.showinfo("完成", f"已删除 {n} 条记录，请点击查询刷新。")
        self.status_var.set(f"已删除 {n} 条记录")

    # ================================================================
    # 报警查询/显示
    # ================================================================
    def _query_alarms(self):
        if not self.manager:
            return
        self.status_var.set("正在查询报警...")
        self.update_idletasks()

        try:
            dev = self._selected_device()
            start = self.a_start.get().strip() or None
            end = self.a_end.get().strip() or None
            kw = self.a_keyword.get().strip() or None
            try:
                limit = int(self.a_limit.get())
            except ValueError:
                limit = 500

            records = self.manager.query_alarms(
                device_id=dev, start_time=start, end_time=end,
                keyword=kw, limit=limit, classify=True)
            total = self.manager.get_alarms_count(dev, start, end, kw)
            self._alarms_cache = records

            for item in self.alarms_tree.get_children():
                self.alarms_tree.delete(item)

            for rec in records:
                tags = ["white"]
                lvl = (rec.alarm_level or "").lower()
                cat = (rec.alarm_category or "").lower()
                if "red" in lvl or "高危" in lvl:
                    tags = ["red"]
                elif "yellow" in lvl or "中危" in lvl:
                    if "tech" in cat:
                        tags = ["tech"]
                    elif "arr" in cat:
                        tags = ["arr"]
                    else:
                        tags = ["yellow"]

                self.alarms_tree.insert("", "end", values=(
                    rec.id, str(rec.timestamp)[:19], rec.device_id,
                    rec.alarm_level or "-",
                    _category_cn(rec.alarm_category),
                    rec.alarm_parsed or "-",
                    rec.mdc_code or "-",
                    rec.param_name or "-",
                    rec.alarm_text or "-",
                ), tags=tags)

            self.alarms_count_label.config(
                text=f"共 {total:,} 条报警，当前显示 {len(records)} 条"
            )
            self.status_var.set(f"✅ 报警查询完成，显示 {len(records)} 条")
        except Exception as e:
            self.status_var.set("❌ 查询失败")
            messagebox.showerror("错误", f"查询失败: {e}")
            import traceback
            traceback.print_exc()

    def _delete_selected_alarms(self):
        sel = self.alarms_tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先选择要删除的行")
            return
        ids = []
        for item in sel:
            vals = self.alarms_tree.item(item, "values")
            try:
                ids.append(int(vals[0]))
            except (ValueError, IndexError):
                pass
        if not ids:
            return
        if not messagebox.askyesno("确认删除",
                f"确定要删除所选 {len(ids)} 条报警记录吗？\n此操作不可撤销。"):
            return
        n = self.manager.delete_alarms(ids)
        messagebox.showinfo("完成", f"已删除 {n} 条报警，请点击查询刷新。")
        self.status_var.set(f"已删除 {n} 条记录")

    # ================================================================
    # 详情对话框（双击打开）
    # ================================================================
    def _show_vital_detail(self, event):
        sel = self.vitals_tree.selection()
        if not sel:
            return
        vals = self.vitals_tree.item(sel[0], "values")
        try:
            rid = int(vals[0])
        except (ValueError, IndexError):
            return
        rec = None
        for r in self._vitals_cache:
            if r.id == rid:
                rec = r
                break
        if not rec:
            return

        lines = [
            ("时间", str(rec.timestamp)),
            ("设备 SN", rec.device_id),
            ("患者姓名", rec.patient_name or "-"),
            ("科室", rec.department or "-"),
            ("床位", rec.bed_id or "-"),
            ("主治医生", rec.doctor or "-"),
            ("监护仪检测", rec.diagnosis or "（无报警）"),
            ("入院诊断", rec.admission_diagnosis or "-"),
            ("", ""),
            ("心率 (HR)", f"{rec.hr:.0f} bpm   正常: {VITAL_NORMALS['hr'][0]:.0f}-{VITAL_NORMALS['hr'][1]:.0f}"
             + ("  ⚠ 越上限" if check_abnormal("hr", rec.hr) == "high"
                else "  ⚠ 越下限" if check_abnormal("hr", rec.hr) == "low"
                else "  ✓ 正常")),
            ("血氧 (SpO₂)", f"{rec.spo2:.0f} %   正常: {VITAL_NORMALS['spo2'][0]:.0f}-{VITAL_NORMALS['spo2'][1]:.0f}"
             + ("  ⚠ 越下限" if check_abnormal("spo2", rec.spo2) == "low"
                else "  ⚠ 越上限" if check_abnormal("spo2", rec.spo2) == "high"
                else "  ✓ 正常")),
            ("呼吸 (RR)", f"{rec.rr:.0f} rpm   正常: {VITAL_NORMALS['rr'][0]:.0f}-{VITAL_NORMALS['rr'][1]:.0f}"
             + ("  ⚠ 越上限" if check_abnormal("rr", rec.rr) == "high"
                else "  ⚠ 越下限" if check_abnormal("rr", rec.rr) == "low"
                else "  ✓ 正常")),
            ("体温 (Temp)", f"{rec.temp:.1f} ℃   正常: {VITAL_NORMALS['temp'][0]:.1f}-{VITAL_NORMALS['temp'][1]:.1f}"
             + ("  ⚠ 越上限" if check_abnormal("temp", rec.temp) == "high"
                else "  ⚠ 越下限" if check_abnormal("temp", rec.temp) == "low"
                else "  ✓ 正常")),
            ("收缩压 (SYS)", f"{rec.sys:.0f} mmHg"
             + ("  ⚠ 越限" if check_abnormal("sys", rec.sys) else "  ✓ 正常")),
            ("舒张压 (DIA)", f"{rec.dia:.0f} mmHg"
             + ("  ⚠ 越限" if check_abnormal("dia", rec.dia) else "  ✓ 正常")),
            ("平均压 (MAP)", f"{rec.map:.0f} mmHg"
             + ("  ⚠ 越限" if check_abnormal("map", rec.map) else "  ✓ 正常")),
        ]
        self._open_detail_window(
            title=f"生命体征详情 | ID {rec.id}",
            lines=lines,
            record_data={"id": rec.id, "type": "vital"},
        )

    def _show_alarm_detail(self, event):
        sel = self.alarms_tree.selection()
        if not sel:
            return
        vals = self.alarms_tree.item(sel[0], "values")
        try:
            rid = int(vals[0])
        except (ValueError, IndexError):
            return
        rec = None
        for r in self._alarms_cache:
            if r.id == rid:
                rec = r
                break
        if not rec:
            return
        lines = [
            ("时间", str(rec.timestamp)),
            ("设备", rec.device_id),
            ("级别", rec.alarm_level or "-"),
            ("分类", _category_cn(rec.alarm_category)),
            ("MDC 编码", rec.mdc_code or "-"),
            ("相关参数", rec.param_name or "-"),
            ("=== 解析内容（中文）", rec.alarm_parsed or "-"),
            ("=== 原始 MDC 数据", rec.alarm_text or "-"),
        ]
        self._open_detail_window(
            title=f"报警详情 | ID {rec.id}",
            lines=lines,
            record_data={"id": rec.id, "type": "alarm"},
        )

    def _open_detail_window(self, title, lines, record_data):
        top = tk.Toplevel(self)
        top.title(title)
        top.geometry("720x600")
        top.configure(bg="#ffffff")
        top.transient(self)
        top.grab_set()

        header = tk.Frame(top, bg="#1e3a5f")
        header.pack(fill="x")
        tk.Label(header, text="🔎 " + title,
                font=("Microsoft YaHei", 13, "bold"),
                bg="#1e3a5f", fg="white").pack(padx=12, pady=10, anchor="w")

        body = tk.Frame(top, bg="white")
        body.pack(fill="both", expand=True, padx=14, pady=10)

        scroll_frame = tk.Frame(body, bg="white")
        scroll_frame.pack(fill="both", expand=True)

        canvas = tk.Canvas(scroll_frame, bg="white", highlightthickness=0)
        canvas.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(scroll_frame, orient="vertical", command=canvas.yview)
        sb.pack(side="right", fill="y")
        canvas.configure(yscrollcommand=sb.set)

        inner = tk.Frame(canvas, bg="white")
        canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_configure(_):
            canvas.configure(scrollregion=canvas.bbox("all"))
        inner.bind("<Configure>", _on_configure)

        for i, (k, v) in enumerate(lines):
            bg = "#f5f7fa" if i % 2 == 0 else "white"
            row = tk.Frame(inner, bg=bg)
            row.pack(fill="x", pady=1)
            label_text = str(k) + ("：" if k else "")
            tk.Label(row, text=label_text,
                    font=("Microsoft YaHei", 10, "bold"),
                    bg=bg, fg="#1e3a5f", anchor="w", width=20
                    ).pack(side="left", padx=8, pady=6)
            val_text = str(v) if v else "-"
            tk.Label(row, text=val_text, font=("Microsoft YaHei", 10),
                    bg=bg, fg="#263238", anchor="w", wraplength=480,
                    justify="left").pack(side="left", padx=8, pady=6,
                    fill="x", expand=True)

        # 按钮区
        btn_bar = tk.Frame(top, bg="#e0e6ed")
        btn_bar.pack(fill="x", side="bottom")

        def do_print():
            lines_out = [
                f"=== {title} ===",
                f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "",
            ]
            for k, v in lines:
                lines_out.append(f"{k}: {v}")
            text = "\n".join(lines_out)
            fname = os.path.join(
                tempfile.gettempdir(),
                f"report_{record_data.get('type', 'x')}_"
                f"{record_data.get('id', 0)}_{datetime.now().strftime('%H%M%S')}.txt"
            )
            with open(fname, "w", encoding="utf-8") as f:
                f.write(text)
            try:
                if sys.platform.startswith("win"):
                    os.startfile(fname, "print")  # type: ignore[attr-defined]
                elif sys.platform == "darwin":
                    os.system(f"open -a Preview {fname}")
                else:
                    os.system(f"xdg-open {fname}")
                messagebox.showinfo("打印", f"文档已发送到系统打印程序\n文件: {fname}")
            except Exception as e:
                messagebox.showerror("错误", f"打印失败: {e}\n已保存到: {fname}")

        def do_delete():
            rd = record_data
            if not messagebox.askyesno("确认", "是否删除此记录？"):
                return
            if rd.get("type") == "vital":
                if self.manager and self.manager.delete_vital(int(rd.get("id", 0))):
                    messagebox.showinfo("完成", "已删除，请刷新查询。")
                    top.destroy()
            elif rd.get("type") == "alarm":
                if self.manager and self.manager.delete_alarm(int(rd.get("id", 0))):
                    messagebox.showinfo("完成", "已删除，请刷新查询。")
                    top.destroy()

        ttk.Button(btn_bar, text="🖨 打印 / 保存", command=do_print
                  ).pack(side="right", padx=10, pady=10)
        ttk.Button(btn_bar, text="🗑 删除此记录", command=do_delete
                  ).pack(side="right", padx=10, pady=10)
        ttk.Button(btn_bar, text="关闭", command=top.destroy
                  ).pack(side="right", padx=10, pady=10)

    # ================================================================
    # 统计分析
    # ================================================================
    def _run_analysis(self):
        if not self.manager:
            return
        self.status_var.set("正在分析...")
        self.update_idletasks()

        try:
            dev = self._selected_device()
            start = self.an_start.get().strip() or None
            end = self.an_end.get().strip() or None
            report = self.manager.analyze_vitals(dev, start, end)

            for item in self.analysis_tree.get_children():
                self.analysis_tree.delete(item)

            for _, stats in report.parameter_stats.items():
                if stats["count"] == 0:
                    continue
                vr = stats["violation_rate"]
                tags = ["green"]
                if vr >= 50:
                    tags = ["red"]
                elif vr >= 15:
                    tags = ["yellow"]
                self.analysis_tree.insert("", "end", values=(
                    stats["name"], f"{stats['count']:,}",
                    f"{stats['mean']:.1f}", f"{stats['min']:.1f}",
                    f"{stats['max']:.1f}", f"{stats['median']:.1f}",
                    stats["normal_range"],
                    f"{stats['low_count']:,}",
                    f"{stats['high_count']:,}",
                    f"{vr:.1f}%",
                ), tags=tags)

            a = report.alarm_summary
            self.alarm_sum_labels["total"].config(text=f"总数: {a['total']}")
            self.alarm_sum_labels["red"].config(
                text=f"🔴高危: {a['red']}", fg="#c62828")
            self.alarm_sum_labels["yellow"].config(
                text=f"🟡中危: {a['yellow']}", fg="#ef6c00")
            self.alarm_sum_labels["white"].config(
                text=f"⚪提示: {a['white']}", fg="#2e7d32")
            self.alarm_sum_labels["physiological"].config(
                text=f"生理: {a['physiological']}")
            self.alarm_sum_labels["technical"].config(
                text=f"技术: {a['technical']}")
            self.alarm_sum_labels["arrhythmia"].config(
                text=f"心律失常: {a['arrhythmia']}", fg="#ad1457")

            self.status_var.set(
                f"✅ 分析完成 - 设备 {report.device_id} | {report.total_records} 条记录"
            )
        except Exception as e:
            self.status_var.set("❌ 分析失败")
            messagebox.showerror("错误", f"分析失败: {e}")
            import traceback
            traceback.print_exc()

    # ================================================================
    # 图表
    # ================================================================
    def _destroy_chart_canvas(self):
        """修复 FigureCanvasTkAgg 没有 destroy 方法的问题：
        使用 canvas.get_tk_widget().destroy() 替代，并额外销毁 holder 中残留控件。
        """
        if self._chart_canvas is not None:
            try:
                self._chart_canvas.get_tk_widget().destroy()
            except AttributeError:
                try:
                    self._chart_canvas.destroy()
                except Exception:
                    pass
            except Exception:
                pass
            self._chart_canvas = None
        if self._chart_figure is not None:
            try:
                import matplotlib.pyplot as plt2
                plt2.close(self._chart_figure)
            except Exception:
                pass
            self._chart_figure = None
        if hasattr(self, "chart_holder") and self.chart_holder is not None:
            for w in self.chart_holder.winfo_children():
                try:
                    w.destroy()
                except Exception:
                    pass

    def _gen_chart(self):
        if not self.manager or not _MPL_AVAILABLE:
            messagebox.showinfo("提示", "图表功能需要 matplotlib")
            return
        dev = self._selected_device()
        if not dev:
            messagebox.showinfo("提示", "请先选择具体设备（不要选'全部设备'）")
            return
        try:
            hours = int(self.chart_hours.get())
        except ValueError:
            hours = 48

        self.status_var.set("正在生成图表...")
        self.update_idletasks()

        try:
            self._destroy_chart_canvas()

            end_dt = datetime.now()
            start_dt = end_dt - timedelta(hours=hours)
            s_str = start_dt.strftime("%Y-%m-%d %H:%M:%S")
            e_str = end_dt.strftime("%Y-%m-%d %H:%M:%S")

            if self.chart_type.get() == "trend":
                fig = self._make_trend_fig(dev, s_str, e_str)
            else:
                fig = self._make_alarm_fig(dev, s_str, e_str)

            if fig is None:
                messagebox.showinfo("提示", "该时间范围内没有可用数据")
                self.status_var.set("⚠ 无数据")
                return

            self._chart_figure = fig
            canvas = FigureCanvasTkAgg(fig, master=self.chart_holder)
            canvas.draw()
            canvas.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=8)
            self._chart_canvas = canvas
            self.status_var.set("✅ 图表已生成")
        except Exception as e:
            self.status_var.set("❌ 图表生成失败")
            messagebox.showerror("错误", f"图表生成失败: {e}")
            import traceback
            traceback.print_exc()

    def _make_trend_fig(self, device_id, start_str, end_str):
        trends = self.manager.get_hourly_trend(device_id, start_str, end_str)
        if not trends or not any(trends.values()):
            return None
        params = [p for p, data in trends.items() if data]
        if not params:
            return None
        n = min(3, len(params))

        fig = Figure(figsize=(13, 3.2 * n + 1.0), dpi=100)
        fig.suptitle(f"设备 {device_id} 生命体征趋势\n"
                    f"{start_str[:16]} ~ {end_str[:16]}",
                    fontsize=12, fontweight="bold", color="#1e3a5f")

        for i in range(n):
            p = params[i]
            data = trends[p]
            times = [d["time"][5:13] for d in data]
            avg_vals = [d["avg"] for d in data]
            max_vals = [d["max"] for d in data]
            min_vals = [d["min"] for d in data]

            ax = fig.add_subplot(n, 1, i + 1)
            low, high = VITAL_NORMALS.get(p, (0.0, 10000.0))
            if low and high and low < high < 10000:
                ax.axhspan(low, high, alpha=0.12, color="green", label="正常范围")

            x = list(range(len(times)))
            ax.plot(x, avg_vals, "b-", linewidth=1.6, label="均值")
            ax.fill_between(x, min_vals, max_vals, alpha=0.2, color="blue")

            for j, v in enumerate(avg_vals):
                if 0 < low < high < 10000:
                    if v > high or v < low:
                        ax.plot(j, v, "ro", markersize=6)

            ax.set_title(
                f"{_PARAM_LABELS.get(p, p)} ({_PARAM_UNIT.get(p, '')})",
                fontsize=11, fontweight="bold", color="#1e3a5f"
            )
            ax.grid(True, alpha=0.3)
            ax.legend(loc="upper right", fontsize=8)

            step = max(1, len(times) // 12)
            tick_pos = x[::step]
            tick_labels = [times[i] for i in tick_pos]
            ax.set_xticks(tick_pos)
            ax.set_xticklabels(tick_labels, rotation=30, ha="right", fontsize=8)

        fig.tight_layout(rect=[0, 0.02, 1, 0.96])
        return fig

    def _make_alarm_fig(self, device_id, start_str, end_str):
        alarms = self.manager.query_alarms(
            device_id=device_id, start_time=start_str, end_time=end_str,
            classify=True)
        if not alarms:
            return None
        from collections import Counter
        level_counts = Counter()
        cat_counts = Counter()
        for a in alarms:
            lvl = (a.alarm_level or "").lower()
            if "red" in lvl or "高危" in lvl:
                level_counts["🔴高危"] += 1
            elif "yellow" in lvl or "中危" in lvl:
                level_counts["🟡中危"] += 1
            else:
                level_counts["⚪提示"] += 1
            cat_counts[a.alarm_category or "其他"] += 1

        fig = Figure(figsize=(13, 5.5), dpi=100)
        ax1 = fig.add_subplot(1, 2, 1)
        labels1 = list(level_counts.keys())
        values1 = list(level_counts.values())
        colors1 = ["#ef5350" if "🔴" in l
                   else "#ffb74d" if "🟡" in l
                   else "#81c784" for l in labels1]
        bars = ax1.bar(range(len(labels1)), values1,
                      color=colors1, edgecolor="#455a64")
        ax1.set_xticks(range(len(labels1)))
        ax1.set_xticklabels(labels1, fontsize=10, fontweight="bold")
        ax1.set_title(f"按级别 (共 {len(alarms)} 条)",
                     fontsize=12, fontweight="bold", color="#1e3a5f")
        ax1.set_ylabel("次数")
        ax1.grid(True, axis="y", alpha=0.3)
        for bar, v in zip(bars, values1):
            ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                    str(v), ha="center", va="bottom", fontweight="bold")

        ax2 = fig.add_subplot(1, 2, 2)
        labels2 = [_category_cn(x) for x in cat_counts.keys()]
        values2 = list(cat_counts.values())
        palette = ["#42a5f5", "#66bb6a", "#ec407a", "#bdbdbd",
                   "#ffca28", "#ab47bc"]
        colors2 = [palette[j % len(palette)] for j in range(len(labels2))]
        bars2 = ax2.bar(range(len(labels2)), values2,
                       color=colors2, edgecolor="#455a64")
        ax2.set_xticks(range(len(labels2)))
        ax2.set_xticklabels(labels2, fontsize=10, fontweight="bold")
        ax2.set_title("按类别", fontsize=12, fontweight="bold", color="#1e3a5f")
        ax2.set_ylabel("次数")
        ax2.grid(True, axis="y", alpha=0.3)
        for bar, v in zip(bars2, values2):
            ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                    str(v), ha="center", va="bottom", fontweight="bold")

        fig.suptitle(f"设备 {device_id} 报警统计",
                    fontsize=13, fontweight="bold", color="#1e3a5f", y=0.98)
        fig.tight_layout()
        return fig

    def _save_chart(self):
        if self._chart_figure is None:
            messagebox.showinfo("提示", "请先生成图表")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG图片", "*.png"), ("PDF文档", "*.pdf")],
            initialfile=f"chart_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
        if not path:
            return
        try:
            self._chart_figure.savefig(path, dpi=180, bbox_inches="tight")
            messagebox.showinfo("成功", f"图表已保存:\n{path}")
            self._log(f"📊 图表已保存: {path}")
        except Exception as e:
            messagebox.showerror("错误", f"保存失败: {e}")

    def _print_chart(self):
        if self._chart_figure is None:
            messagebox.showinfo("提示", "请先生成图表")
            return
        fname = os.path.join(
            tempfile.gettempdir(),
            f"chart_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        )
        try:
            self._chart_figure.savefig(fname, dpi=180, bbox_inches="tight")
            if sys.platform.startswith("win"):
                os.startfile(fname, "print")  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                os.system(f"open -a Preview {fname}")
            else:
                os.system(f"xdg-open {fname}")
            messagebox.showinfo("打印", f"图表已发送到系统打印程序\n临时文件: {fname}")
        except Exception as e:
            messagebox.showerror("错误", f"打印失败: {e}")

    # ================================================================
    # 导出
    # ================================================================
    def _log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        try:
            self.export_log.insert("end", f"[{ts}] {msg}\n")
            self.export_log.see("end")
        except Exception:
            pass

    def _quick_export(self, kind):
        if not self.manager:
            return
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dev = self._selected_device()
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV 文件", "*.csv")],
            initialfile=f"{kind}_{dev or 'ALL'}_{ts}.csv"
        )
        if not path:
            return
        try:
            if kind == "vitals":
                self.manager.export_to_csv(path, device_id=dev, data_type="vitals")
                total = self.manager.get_vitals_count(dev)
                self._log(f"✅ 已导出 {total:,} 条生命体征 → {path}")
            else:
                self.manager.export_to_csv(path, device_id=dev, data_type="alarms")
                total = self.manager.get_alarms_count(dev)
                self._log(f"✅ 已导出 {total:,} 条报警 → {path}")
            messagebox.showinfo("成功", f"已导出到:\n{path}")
            self.status_var.set("导出完成")
        except Exception as e:
            self._log(f"❌ 导出失败: {e}")
            messagebox.showerror("错误", f"导出失败: {e}")

    def _export_data(self):
        if not self.manager:
            return
        fmt = self.export_fmt.get()
        dev = self._selected_device()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        if fmt == "csv_vitals":
            path = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV 文件", "*.csv")],
                initialfile=f"vitals_{dev or 'ALL'}_{ts}.csv")
        elif fmt == "csv_alarms":
            path = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV 文件", "*.csv")],
                initialfile=f"alarms_{dev or 'ALL'}_{ts}.csv")
        else:
            path = filedialog.asksaveasfilename(
                defaultextension=".json",
                filetypes=[("JSON 文件", "*.json")],
                initialfile=f"report_{dev or 'ALL'}_{ts}.json")
        if not path:
            return
        self.status_var.set("正在导出...")
        self.update_idletasks()
        try:
            if fmt == "csv_vitals":
                self.manager.export_to_csv(path, device_id=dev, data_type="vitals")
                total = self.manager.get_vitals_count(dev)
                self._log(f"✅ 已导出 {total:,} 条生命体征 → {path}")
            elif fmt == "csv_alarms":
                self.manager.export_to_csv(path, device_id=dev, data_type="alarms")
                total = self.manager.get_alarms_count(dev)
                self._log(f"✅ 已导出 {total:,} 条报警 → {path}")
            else:
                self.manager.export_to_json(path, device_id=dev)
                self._log(f"✅ 已导出完整 JSON 报告 → {path}")
            messagebox.showinfo("成功", f"已导出到:\n{path}")
            self.status_var.set("导出完成")
        except Exception as e:
            self._log(f"❌ 导出失败: {e}")
            messagebox.showerror("错误", f"导出失败: {e}")


def main():
    app = ArchiveApp()
    app.mainloop()


if __name__ == "__main__":
    main()