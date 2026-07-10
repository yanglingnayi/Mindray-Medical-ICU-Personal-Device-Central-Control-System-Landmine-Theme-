# ✟ OpenMonitor Pro ♡ v4.2

> _超天酱地雷系高精度医疗级双栈实时采集核心后台_
>
> 🔞 OMG_KAWAII_ANGEL_MONITOR — 24h 实时守护 ♡

---

## ✟ 项目简介

OpenMonitor Pro 是一款面向迈瑞（Mindray）系列监护仪的实时数据采集与可视化系统。

**核心能力：**

- 📡 **双协议监听**：同时解析 2575 端口体征常态流 + 2576 端口报警流（HL7 over MLLP）
- 📊 **临床级可视化**：ECG/SpO₂/RR/NIBP 多通道点云波形 + 实时数值面板
- 🚨 **智能报警分级**：P0（致命）/P1（紧急）全屏弹窗 + 深度医学分析；P2/P3 右下角气泡静默提示；⚠️ **未分类报警原文直接列出**（便于查询监护仪手册）
- 🏥 **患者档案管理**：多设备适配 + 后台档案编辑（支持医院/科室/床位等字段）+ 删除患者档案/删除设备注册
- 💾 **SQLite 持久化**：全量体征/报警数据自动入库，支持近 24h 历史回填
- 🖥 **双栈网络**：IPv4 + IPv6 同时监听，支持局域网/公网直连；🌐 **TCP 端口连通性测试**（网络联通协议测试）
- 🔊 **后台音乐**：休眠模式（`no.mp3`）+ **后台自动播放**（`adimin.mp3`，进入管理台自动开始播放，通过 🎵 **唱片机按钮** 一键切换播放/停止）；💤 **手动休眠按钮**（临时离岗/测试时手动触发）

---

## ✟ 快速开始

### 环境要求

| 依赖 | 推荐版本 |
|------|---------|
| Python | 3.10+ |
| pip | 最新 |

### 安装依赖

```bash
cd OpenMonitor
pip install -r requirements.txt
```

`requirements.txt` 内容：
```
fastapi
uvicorn[standard]
sqlalchemy
aiosqlite
python-dotenv
hl7
python-multipart
websockets
pydantic>=2.0
```

### 启动服务

```bash
cd OpenMonitor
python start.py
```

启动后控制台输出：
```
🎀 OpenMonitor Pro 双栈医疗级服务器启动中...
🌍 局域网 IPv4 访问地址: http://localhost:8000/
🚀 公网 IPv6 访问地址: http://[自己的ipv6]:8000
✅ 成功解除 IPV6_V6ONLY 限制，网络引擎已进入双栈监听状态
```

### 访问页面

| 地址 | 用途 |
|------|------|
| `http://localhost:8000/` | **主监护界面**（十字架 LOGO、体征波形、报警、患者档案） |
| `http://localhost:8000/admin` | **患者档案管理后台**（编辑患者姓名/科室/床位等字段） |

---

## ✟ 项目结构

```
OpenMonitor/
├── start.py                    # 🔧 启动脚本（创建双栈 Socket 并拉起 uvicorn）
├── requirements.txt            # 📦 Python 依赖列表
├── monitor_data.db             # 💾 SQLite 实时数据库（首次启动自动创建）
├── docker-compose.yml          # 🐳 Docker 部署配置
├── Dockerfile                  # 🐳 容器构建脚本
│
├── img/                        # 🖼 静态图片资源
│   └── tu.jpg                  # ♡ 超天酱默认头像（患者档案预览）
│
└── app/                        # 🐍 FastAPI 应用根包
    ├── main.py                 # 🎯 应用入口 — 组装路由、WebSocket、启动 MLLP
    │
    ├── ui/                     # 🎨 前端界面模块
    │   ├── router.py           #    → 页面路由（/ 和 /admin，从文件读取 HTML）
    │   ├── index.html          #    → 主监护界面 HTML（超天酱地雷系风格 + 点云波形）
    │   └── admin.html          #    → 患者档案管理后台 HTML
    │
    ├── api/                    # 🔌 REST API
    │   ├── vital_api.py        #    → 体征/报警/患者档案 CRUD 接口
    │   └── device_api.py       #    → 设备列表查询接口
    │
    ├── models/                 # 🗄 数据模型（SQLAlchemy ORM）
    │   ├── vital.py            #    → Vital（体征记录：HR/SpO2/RR/NIBP/T）
    │   ├── alert.py            #    → Alert（报警记录：级别+原文，前端未分类时原文直接列出）
    │   ├── device.py           #    → Device（设备信息：SN/型号）
    │   └── patient.py          #    → Patient（患者档案：姓名/性别/年龄/医院/科室/床位等）
    │
    ├── database/               # 💽 数据库引擎
    │   └── database.py         #    → SQLite 连接池 + 表初始化
    │
    ├── hl7/                    # 🏥 HL7/MLLP 协议解析
    │   └── mllp_server.py      #    → 2575/2576 端口异步监听 + HL7 解析
    │
    ├── websocket/              # 🌐 WebSocket 实时推送
    │   └── manager.py          #    → 连接管理器，广播数据到前端
    │
    └── config/                 # ⚙️ 全局配置
        └── config.py           #    → 端口/路径/日志级别的统一配置
```

---

## ✟ 数据流转

```
┌───────────────────────────────────────────────────────────────┐
│ 迈瑞监护仪（串口/网络）                                        │
│  - 常态流 → 2575 端口                                          │
│  - 报警流 → 2576 端口                                          │
└───────────────────────────────────────────────────────────────┘
                               ↓ TCP/MLLP
┌───────────────────────────────────────────────────────────────┐
│ MLLP Server (mllp_server.py)                                    │
│  - 异步监听 2575 / 2576 端口                                    │
│  - 解析 HL7 报文 → 结构化 JSON (HR/SpO2/RR/SYS/DIA/MAP/T)       │
│  - 写入 SQLite                                                  │
│  - 通过 WebSocket Manager 广播给前端                            │
└───────────────────────────────────────────────────────────────┘
                               ↓ WebSocket (/ws)
┌───────────────────────────────────────────────────────────────┐
│ 浏览器 (index.html)                                             │
│  - 实时绘制 ECG/SpO2/RR 点云波形                                │
│  - 更新数值面板（绿/蓝/白/黄临床标准配色）                       │
│  - 报警分级 → P0/P1 全屏弹窗 + 蜂鸣 + 深度医学分析              │
│  - 报警分级 → P2/P3 右下角气泡静默提示                          │
│  - 患者档案自动回填 + 一键复制/CSV 导出                         │
└───────────────────────────────────────────────────────────────┘
```

---

## ✟ 报警级别与策略

| 级别 | 标签 | 典型场景 | UI 响应 |
|------|------|---------|--------|
| **P0** | 🚨 致命 | 停搏 / 室颤 / 窒息 | 全屏红色弹窗 + 持续蜂鸣 + 深度分析 |
| **P1** | 🔥 紧急 | HR>100 或 <60 / SpO2<90 / BP>160 或 <90 | 全屏粉色弹窗 + 蜂鸣 + 临床建议 |
| **P2** | ⚠️ 关注 | 体温异常 / 电极脱落 / 心律失常 | 右下角气泡提示（不干扰流程） |
| **P3** | ℹ️ 提示 | 信号弱 / 电量低 | 右下角气泡提示（静默） |

> 深度分析功能：前端内置 15+ 条规则库，自动识别报警触发指标、当前数值、正常范围、可能病因，并给出临床操作建议。

---

## ✟ REST API 速查

### 体征 API (`/vital/*`)

| 方法 | 路径 | 用途 |
|------|------|------|
| POST | `/vital/submit` | 上报一条体征记录（JSON） |
| GET  | `/vital/history?hours=24&device_id=XXX` | 拉取近 N 小时体征历史 |
| GET  | `/vital/alerts?hours=24&device_id=XXX` | 拉取近 N 小时报警历史 |
| GET  | `/vital/devices` | 获取已接入设备列表 |
| GET  | `/vital/patient?device_id=XXX` | 获取指定设备关联的患者档案（含 hospital/科室字段） |
| POST | `/vital/patient` | 更新/创建患者档案（JSON 提交，支持 hospital 字段） |
| DELETE | `/vital/patient?device_id=XXX` | 删除指定设备的患者档案 |
| POST | `/vital/ping` | 测试 TCP 端口可达性（JSON 提交 `{host, port}`） |

### 设备 API (`/device/*`)

| 方法 | 路径 | 用途 |
|------|------|------|
| GET  | `/device/list` | 所有设备的完整信息 |
| POST | `/device/register` | 登记一台新设备（SN + IP） |
| DELETE | `/device/delete?sn=XXX` | 从设备注册表中移除（不影响体征数据） |

### 前端资源 (`/audio/*`)

| 方法 | 路径 | 用途 |
|------|------|------|
| GET  | `/audio/no.mp3` | 无信号 / 休眠模式背景音乐 |
| GET  | `/audio/admin.mp3` | 值班后台舒缓背景音乐（对应磁盘文件 `E:\OpenMonitor\audio\adimin.mp3`） |

---

## ✟ 前端界面亮点

### 主监护界面 (`/`)

- 🎀 **超天酱地雷系视觉**：深紫背景 + 粉白蓝渐变 + 心形/十字架装饰符号
- ✝ **顶部控制栏**：十字架 SVG LOGO + 设备选择器（多设备切换）+ 💤 手动休眠按钮 + ⚙️ 管理台跳转
- 📊 **三栏布局**：
  - 左：患者档案（只读，显示 **医院/科室/床位** 等字段）+ 一键复制/CSV 导出/归档
  - 中：实时体征数值卡片（HR 绿、SpO2 蓝、RR 黄、BP 白）+ 三点云波形图（含正常范围参考线）
  - 右：历史时间轴 + 报警记录（⚠️ P3 未分类报警直接显示**原始报警原文**，便于查询设备手册）
- 🖥 底部：全量原始日志控制台（高密度等宽字体）
- 🔊 **休眠模式**：手动触发休眠，播放 `no.mp3` 背景音乐，点击画面即可恢复

### 档案管理后台 (`/admin`)

- 📋 完整患者字段：姓名、性别、年龄、**医院**、科室、床位、身份证号、电话、入院时间、主管医生、诊断、备注
- 🗑 **删除操作**：支持删除患者档案（不可恢复，需二次确认）+ 移除设备注册（不影响体征数据）
- 🌐 **网络测试标签**：TCP 端口连通性测试（支持 80/443/8000 常用端口快速扫描）
- 🎵 **后台音乐标签**：进入管理台自动播放 `adimin.mp3`，通过 🎵 **唱片机按钮** 一键切换播放/停止；值班期间可播放舒缓音乐缓解疲劳
- 🔒 按设备 ID 关联，多设备独立管理；保存后自动同步至主监护页面

---

## ✟ 配置说明

修改 `app/config/config.py` 可调整：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `MLLP_PORT_NORMAL` | 2575 | 常态流监听端口 |
| `MLLP_PORT_ALARM` | 2576 | 报警流监听端口 |
| `WEB_PORT` | 8000 | Web UI / API 端口 |
| `DB_PATH` | `monitor_data.db` | SQLite 数据库路径 |

---

## ✟ Docker 部署

```bash
# 构建镜像
docker build -t openmonitor .

# 启动容器（双栈网络 + 数据卷挂载）
docker-compose up -d
```

---

## ✟ 常见问题

### Q1: 服务启动后浏览器访问超时？
> 检查 Windows 防火墙是否允许 `python.exe` 的 8000 端口入站连接；
> 或使用 `netsh advfirewall firewall add rule name="OpenMonitor" dir=in action=allow protocol=TCP localport=8000`

### Q2: 监护仪数据不来？
> 确认监护仪与服务器之间网络可达，MLLP 端口 2575/2576 未被占用；
> 查看 `/ws` 控制台面板是否有 `[HL7]` 原始报文输出。

### Q3: 患者档案字段在主页面显示为空？
> 先访问 `/admin` 页面填写并保存档案，主页面会在下次拉取历史数据时自动回填。

### Q4: 想修改页面样式？
> 直接编辑 `app/ui/index.html`（CSS/HTML/JS 全部内联），无需重启服务——刷新浏览器即可。

---

## ✟ 技术栈

| 层级 | 技术 |
|------|------|
| Web 框架 | **FastAPI** (ASGI, Pydantic v2) |
| Web 服务器 | **uvicorn** (Cython 加速) |
| 实时推送 | **WebSocket** (FastAPI 原生) |
| 数据库 | **SQLite** + **SQLAlchemy** + **aiosqlite** (异步) |
| 协议解析 | **hl7** (Python-hl7) |
| 前端 | 原生 HTML + CSS + Canvas 2D + 原生 JavaScript（零依赖） |

---

<div align="center">
<h3>✟ ♡ Made with love — Angel-chan 永远守护患者 ♡ ✟</h3>
</div>