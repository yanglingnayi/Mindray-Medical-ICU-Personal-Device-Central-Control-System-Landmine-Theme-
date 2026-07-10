import os
from dotenv import load_dotenv

load_dotenv()

# 服务配置
WEB_HOST = os.getenv("WEB_HOST", "0.0.0.0")
WEB_PORT = int(os.getenv("WEB_PORT", 8000))
MLLP_HOST = os.getenv("MLLP_HOST", "0.0.0.0")
MLLP_PORT = int(os.getenv("MLLP_PORT", 2575))

# 数据存储
DATA_ROOT = os.getenv("DATA_ROOT", "./data")
DATABASE = os.path.join(DATA_ROOT, "monitor.db")
LOG_ROOT = os.getenv("LOG_ROOT", "./logs")

# 多设备最大连接数
MAX_DEVICE_NUM = 10