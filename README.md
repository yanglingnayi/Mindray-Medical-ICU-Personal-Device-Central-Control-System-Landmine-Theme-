# ♡ Mindray-Medical-ICU-Personal-Device-Central-Control-System-Landmine-Theme- 🖤🎀

> 🖤 **不用买迈瑞中央站，不用插网线，就能把好几台监护仪都收到电脑里实时看！**
> 🎀 *You can remotely record and access data without buying a central station or connecting multiple devices via network cables.*
>
> 💕 超天酱病娇地雷系风格 · 粉青紫蒸汽波配色 · 天使酱会为你的患者报警而生气（和担心）💕
>
> *— 说实话啦，你真的以为医院花几十万买的那个中央站有什么了不起的技术吗？其实就是个 TCP 抓包 + SQLite 嘛～
> 既然这样，本小姐自己写一个不就好了？反正代码都给你了，还免费呢哼 💅*
>
> *— 另外啦，页面底部那些粉色小字真的只是装饰哦……**绝对不是什么入口**哦 🌸*

---

## ✨ 本小姐的得意功能一览 💕

| 功能 | 说明 |
|------|------|
| 🏥 **患者档案管理** | 姓名/性别/年龄/床号/科室/**医院** — 全部字段后台可编辑可删除 |
| 💗 **实时生命体征** | HR · SpO₂ · SYS/DIA · TEMP · RR — 毫秒级刷新（WebSocket 推流） |
| 🔔 **智能分级报警** | 🚨P0 致命 / 🔥P1 紧急 / ⚠️P2 关注 / ℹ️P3 提示 — 报警原文完整保留（方便查手册） |
| 📡 **MLLP/HL7 原生接入** | 直接对接迈瑞 BeneView 系列 2575 端口原生协议，**无需额外硬件** |
| 🌐 **TCP 端口连通检测** | 内嵌网络测试工具（不依赖系统 ping），一键判断监护仪是否在线 |
| 🖥️ **IPv4 + IPv6 双栈** | 医院内网/外网公网都能跑，部署零配置 |
| 📟 **设备注册管理** | 自由添加/删除监护设备 SN，设备列表独立管理 |
| 📊 **历史 CSV 导出** | 所有体征历史一键导出 CSV，Excel 直开 |
| 📁 **病例归档系统** | 按患者独立归档病例资料，下载一键打包 |
| 🎵 **氛围音乐播放** | 进入页面自动播放 · 右下角迷你唱片机随时播放/暂停 |
| 🌙 **无信号休眠模式** | 手动一键休眠 · 无数据自动休眠 · 休眠时专属音乐 |
| 🧱 **无中央站·无网线** | **你只需要让监护仪连到同一局域网就行，其他的交给本小姐就好啦** 💕 |

---

## 🧩 项目结构 · 本小姐写的代码可是很整齐的哦 🖤

```
Mindray-ICU-Landmine/
├── start.py                     # ✨ 双栈网络启动入口（IPv4:8000 + IPv6:[::]:8000）
├── start_hl7.py                 # 📡 可选：MLLP 原生协议接收引擎
│
├── app/
│   ├── main.py                  # 🎀 FastAPI 主入口（挂载全部路由 & WebSocket）
│   ├── config/config.py         # ⚙️ 配置（端口 / 数据库路径 / 数据存储根目录）
│   ├── database/database.py     # 💾 SQLAlchemy 引擎 · 启动时自动建表 & 自动加字段
│   │
│   ├── models/                  # 📋 数据模型（4 张表）
│   │   ├── patient.py           #    患者档案表（含 hospital 字段）
│   │   ├── vital.py             #    生命体征流水表
│   │   ├── alert.py             #    报警日志表
│   │   └── device.py            #    监护设备注册表
│   │
│   ├── api/                     # 🔌 REST API
│   │   ├── vital_api.py         #    生命体征 / 患者档案 / 报警 / 网络测试 / CSV / 归档
│   │   └── device_api.py        #    设备注册 / 删除 / 列表查询
│   │
│   ├── ui/                      # 🎨 地雷系前端（纯 HTML + CSS + JS · 无需编译）
│   │   ├── index.html           #    主监护界面（实时数据 · 天使酱语音）
│   │   ├── admin.html           #    档案管理台（录入/编辑/删除 · 设备管理 · 网络测试 · 音乐控制）
│   │   └── router.py            #    前端路由映射（含音频文件服务）
│   │
│   ├── websocket/               # 📡 WebSocket 推送管理器
│   │   └── manager.py           #    多客户端连接管理 · 广播体征数据
│   │
│   └── hl7/                     # 🏥 MLLP 协议解析（迈瑞 2575 端口原生 HL7 报文）
│       └── mllp_server.py       #    ASCII 帧头(0x0B)/帧尾(0x1C 0x0D) 解析
│
├── audio/                       # 🎵 背景音乐（会提交到 GitHub 哦）
│   ├── no.mp3                   #    无信号 / 休眠模式
│   ├── adimin.mp3               #    主界面 / 后台管理
│   └── end.mp3                  #    ……（某个不推荐访问的页面）
│
├── img/                         # 🖼️ 站点图标 & 图片资源
│   ├── logo.png                 #    浏览器 favicon
│   └── tu.jpg                   #    界面装饰图
│
├── requirements.txt             # 📦 Python 依赖（FastAPI / SQLAlchemy / uvicorn / websockets 等）
├── docker-compose.yml           # 🐳 Docker 一键部署
├── dockerfile                   # 📦 Docker 构建文件
├── .gitignore                   # 🔒 仅屏蔽数据库 *.db · 绝不包含患者隐私数据
├── LICENSE                      # 📜 授权协议
└── README.md                    # 💖 你现在看到的这份文件
```

---

## 🚀 启动流程 · 本小姐亲自教你好啦 💕

### 方式一：本地直接跑（最推荐 · 调试最方便）

```bash
# 1. 装依赖（本小姐已经帮你列好 requirements.txt 了哦）
pip install -r requirements.txt

# 2. 启动（双栈网络自动开 · IPv4 + IPv6 一起跑）
python start.py

# 3. 浏览器打开这几个 ↓
#    🏠 主监护界面：  http://localhost:8000
#    ⚙️ 后台管理台：  http://localhost:8000/admin
#    📘 Swagger 文档： http://localhost:8000/docs
#    📕 ReDoc 文档：   http://localhost:8000/redoc
```

启动后终端会打印：

```
🎀 OpenMonitor Pro 双栈医疗级服务器启动中...
🌍 浏览器访问地址: http://localhost:8000
🚀 局域网/公网其他设备: http://[本机IP]:8000
```

> 💡 **小提示**：首次启动时 `app/database/database.py` 会自动在根目录创建 `.db` 文件，**这个文件不会上传到 GitHub**（已在 `.gitignore` 屏蔽），你可以放心大胆地在本机跑，患者数据绝对不会泄露出去啦 🖤

### 方式二：Docker 部署（医院服务器推荐）

```bash
docker-compose up -d --build
```

然后一样访问 `http://localhost:8000`。

---

## 🖥️ 三个页面的用途 · 别搞错了哦 🌸

| 路径 | 页面 | 你该在什么时候打开它 |
|------|------|---------------------|
| `/` | **主监护界面**（index.html） | 值班时一直开着 · 有报警会直接弹窗喊你 |
| `/admin` | **档案管理台**（admin.html） | 新患者入院 / 患者出院 / 需要改资料 / 网络排查 |
| `/easter` | ——— | **不推荐你访问的页面**（真的别去，真的别去哦 🌸） |

> 🖤 *主界面和管理台底部都有一行小小的粉色字……绝对不是什么链接哦～你才不会好奇去点呢对吧对吧？* 💕

---

## 📡 全部 API 接口 · 全在这里了哦 · 本小姐可是很认真整理的 🎀

### 📌 统一说明

- 所有接口基地址：**`http://localhost:8000`**
- 可视化 API 调试页面：**`http://localhost:8000/docs`**（Swagger UI · 强烈推荐）
- 优雅版文档：**`http://localhost:8000/redoc`**
- 实时 WebSocket 推送：**`ws://localhost:8000/ws`**
- 数据格式：**JSON**
- 数据库：**SQLite**（根目录首次启动自动创建）

---

### 💕 第一组：患者档案 API（`/vital` 前缀）

| HTTP 方法 | 路径 | 作用 | 关键参数 |
|-----------|------|------|---------|
| `GET` | **`/vital/patient`** | 查询指定设备的患者档案 | `?device_id=监护仪SN` |
| `POST` | **`/vital/patient`** | 创建或更新患者档案 | JSON 提交 `{device_id, patient_name, gender, age, department, hospital, bed_id, diagnosis, ...}` |
| `DELETE` | **`/vital/patient`** | 删除某设备的患者档案 | `?device_id=监护仪SN` |

**POST /vital/patient 的完整字段（全部可选，缺省留空字符串）：**

```json
{
  "device_id": "MINDRAY-ICU-001",
  "patient_name": "佐藤某某",
  "gender": "男/女",
  "age": 65,
  "department": "ICU",
  "hospital": "XX人民医院",
  "bed_id": "ICU-03",
  "id_card": "",
  "phone": "",
  "diagnosis": "急性心肌梗死后监护",
  "admission_time": "2025-07-10 08:30",
  "doctor": "主治医",
  "note": ""
}
```

> 🖤 **hospital 字段**是本小姐特意加的哦 · 你想区分不同医院的设备就用它 💕

---

### 💗 第二组：生命体征 API（`/vital` 前缀）

| HTTP 方法 | 路径 | 作用 | 关键参数 |
|-----------|------|------|---------|
| `GET` | **`/vital/latest`** | 取某设备最新一组体征 | `?device_id=监护仪SN` |
| `GET` | **`/vital/history`** | 查历史体征数据（默认 24 小时） | `?device_id=XXX&hours=24&limit=1000` |
| `POST` | **`/vital/batch`** | 批量写入体征数据（设备端推送用） | JSON 数组，每条含 timestamp + 各指标 |
| `GET` | **`/vital/export.csv`** | 导出历史数据为 CSV 直接下载 | `?device_id=XXX&hours=24` |

**GET /vital/latest 返回示例：**

```json
{
  "ok": true,
  "data": {
    "device_id": "MINDRAY-ICU-001",
    "hr": 78,
    "spo2": 98,
    "sys": 126,
    "dia": 82,
    "temp": 36.5,
    "rr": 16,
    "created": "2025-07-10 14:32:18"
  }
}
```

---

### 🔔 第三组：报警 API（`/vital` 前缀）

| HTTP 方法 | 路径 | 作用 | 关键参数 |
|-----------|------|------|---------|
| `GET` | **`/vital/alerts`** | 查询报警记录列表 | `?device_id=XXX&hours=24&limit=200` |

> 💡 **很重要的一点**：本小姐保留了所有报警的**原始文本**！如果解析出来是"其他报警(P3)"分类，前端会直接把报警原文贴出来，方便你查迈瑞操作手册。毕竟医院里那些莫名其妙的报警代码真的超讨厌对吧 🖤

---

### 🌐 第四组：网络 & 健康测试 API（`/vital` 前缀）

| HTTP 方法 | 路径 | 作用 | 提交内容 |
|-----------|------|------|---------|
| `POST` | **`/vital/ping`** | TCP 端口可达性检测 | `{"host": "192.168.1.100", "port": 2575}` |
| `GET` | **`/vital/health`** | 后端健康检查（可用于监控） | ——— |
| `GET` | **`/vital/devices`** | 列出所有已知设备（含最后活跃时间） | ——— |

**POST /vital/ping 返回示例：**

```json
{
  "ok": true,
  "host": "192.168.1.100",
  "port": 2575,
  "latency_ms": 2,
  "msg": "TCP 端口可达"
}
```

> 🖤 **这个 ping 不是系统 ping 哦** · 是直接走 TCP socket 的，不用权限，也不依赖 ICMP · 医院防火墙拦不住它 💕

---

### 📁 第五组：病例归档 API（`/vital` 前缀）

| HTTP 方法 | 路径 | 作用 | 关键参数 |
|-----------|------|------|---------|
| `POST` | **`/vital/archive`** | 为指定患者生成并保存病例文件（Markdown/文本） | `?device_id=XXX` + 可选附件 |
| `GET` | **`/vital/archive/list`** | 列出所有已归档病例文件 | ——— |
| `GET` | **`/vital/archive/download`** | 下载指定病例文件（支持打包） | `?filename=XXX` |

---

### 🖥️ 第六组：设备管理 API（`/device` 前缀）

| HTTP 方法 | 路径 | 作用 | 提交内容 |
|-----------|------|------|---------|
| `GET` | **`/device/list`** | 列出全部已注册设备 | ——— |
| `POST` | **`/device/register`** | 注册/更新一台设备 | `{"sn": "监护仪SN", "ip_addr": "192.168.1.100"}` |
| `DELETE` | **`/device/delete`** | 移除设备注册 | `?sn=监护仪SN` |

---

### 📡 第七组：WebSocket 实时推送（`/ws`）

```
连接地址：  ws://localhost:8000/ws
协议：     纯文本 JSON
用途：     后端检测到新体征/新报警时，自动推给所有在线的前端页面
```

> 💡 你不需要手动发任何消息给它，只要连上它就会自动给你推数据。如果只是用网页界面的话，前端代码已经帮你处理好了，**完全不需要你操心** 💕

---

### 🎨 第八组：UI / 静态资源路由（`/`）

| 路径 | 返回内容 |
|------|---------|
| `/` | **主监护界面 HTML** |
| `/admin` | **后台管理台 HTML** |
| `/img/logo.png` | 站点 favicon（logo.png） |
| `/img/tu.jpg` | 主界面顶部装饰图 |
| `/audio/no.mp3` | 无信号/休眠模式背景音乐 |
| `/audio/admin.mp3` | 主界面/后台氛围音乐 |
| `/docs` | **Swagger UI（可直接在线调用所有接口测试）** |
| `/redoc` | **ReDoc（优雅版 API 文档）** |
| `/openapi.json` | **原始 OpenAPI Schema（可导入 Postman）** |

> 🖤 对啦……还有一个路径本小姐没写在上面表格里，**你别去 `/easter` 哦，真的别去** 🌸

---

## 🎵 音频资源说明 · 本小姐已经替你放好了 💕

| 文件 | 触发场景 | 控制方式 |
|------|---------|---------|
| `audio/no.mp3` | 无信号 / 手动触发休眠模式 | 主界面右上角「💤 手动休眠」按钮 |
| `audio/adimin.mp3` | 主界面 & 后台管理的默认氛围音乐 | 进入页面自动播放，右下角唱片机随时开关 |
| `audio/end.mp3` | ……（某个不推荐访问的页面） | ——— |

> 🎶 右下角那个小小的唱片机图标在所有页面都有哦 · 点击它可以随时切换播放/暂停 🖤

---

## 🔒 关于数据隐私 · 本小姐可是很注意保护患者隐私的 💕

- **SQLite 数据库文件**在首次启动时自动创建，具体路径由 `app/config/config.py` 控制
- **`.gitignore` 只屏蔽以下内容**：`*.db`、`*.sqlite`、`*.sqlite3`、`data/` 目录
- **音频 / 图片 / 源代码都会被 Git 正常提交**（本项目就是要公开分享的啦 ✨）
- 如需清空本地数据：直接删除根目录下所有 `*.db` 文件，重启后数据库会自动重建为空
- 提醒一句：**如果你要把数据库文件发给别人，先确认里面没有真实患者信息哦** 🖤

---

## 📦 requirements.txt · 本小姐替你挑好的依赖 💕

```
fastapi
uvicorn[standard]
sqlalchemy
websockets
pydantic
python-dotenv
```

> 💡 如果在医院内网跑，这些库可能需要预先离线装进去（先在能上网的机器 `pip download` 到 U 盘里，再内网离线安装）。本小姐自己就是这么做的哦 💕

---

## 🧭 第一次使用完整流程 · 本小姐手把手教你 🎀

1. **装依赖**：`pip install -r requirements.txt`
2. **启动服务**：`python start.py`
3. **先去管理台**：浏览器打开 `http://localhost:8000/admin`
4. **注册一台设备**（比如 SN 写 `MINDRAY-ICU-001`，IP 写监护仪在医院内网的地址）
5. **填患者档案**（姓名 / 性别 / 年龄 / 床号 / 科室 / 医院 —— 别忘了保存哦）
6. **推送测试数据**：
   - 方式一（自动）：启动 `start_hl7.py`，如果医院内网监护仪开了 2575 端口输出，会自动抓到数据
   - 方式二（手动测试）：打开 `http://localhost:8000/docs`，找到 `POST /vital/batch`，随便塞几条测试数据
7. **回到主界面**：打开 `http://localhost:8000` 看看实时监护效果 · 有报警的话天使酱会跳出来喊你的哦 💕
8. **最后一步**：把鼠标移到页面最底部，**假装什么都没看到**（别问，问就是装饰字 🌸）

---

## 💡 关于「不用买中央站」这件事 · 本小姐要多说两句 🖤

迈瑞监护仪背后其实自带了一个 **2575 端口**，会持续以 MLLP 帧封装的 HL7 报文向外广播实时体征和报警。
**官方的中央站说白了就是用这个端口抓数据，再套一层 UI**。

本小姐这个项目干的事情一模一样：

1. 用 `app/hl7/mllp_server.py` 监听 2575 端口（或者你把监护仪的输出指向本机任一空闲端口都行）
2. 解析 MLLP 帧头 `0x0B` / 帧尾 `0x1C 0x0D`，抽出 HL7 文本
3. 把 HR / SpO₂ / BP / TEMP / RR / 报警原文 提取出来，写进 SQLite
4. 通过 `/ws` WebSocket 广播给所有前端页面
5. 前端用 CSS 渲染成你看到的那个样子

**你需要的只是：让监护仪和运行本软件的电脑在同一个局域网里。**
**不需要额外的硬件，不需要从监护仪拉网线到专用中央站主机，也不需要花钱买任何 License。**

> *— 医院里的那些中央站销售顾问看到你拿这个项目跑起来了，估计要气到哭鼻子了呢 💔*

---

## 📜 License

详见根目录 `LICENSE` 文件。

---

> 🖤 *你能读到这里也算很有耐心了呢。既然如此——
> 既然你已经注意到了本 README 里反复提到的「页面底部有粉色小字」……
> 那你现在打开 `http://localhost:8000`，把鼠标移到最最最底部的那行粉色字上，
> **试试看**按一下左键 💕*
