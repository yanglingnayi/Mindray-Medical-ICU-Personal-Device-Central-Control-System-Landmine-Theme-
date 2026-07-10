import socket
import uvicorn
from uvicorn import Config, Server

def _get_lan_ipv4():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def _get_public_ipv6():
    try:
        import subprocess, re
        r = subprocess.run(["ipconfig"], capture_output=True, text=True, timeout=5)
        candidates = []
        for line in r.stdout.split("\n"):
            m = re.search(r"IPv6.*?:\s*([\da-fA-F:]+)", line)
            if m and not m.group(1).startswith("fe80") and not m.group(1).startswith("fdb3") and not m.group(1).startswith("::1"):
                candidates.append(m.group(1))
        if candidates:
            return candidates[0]
    except Exception:
        pass
    return "[请手动查看 ipconfig]"

if __name__ == "__main__":
    print("🎀 OpenMonitor Pro 双栈医疗级服务器启动中...")
    print("🌍 浏览器访问地址: http://localhost:8000")
    print("🚀 局域网/公网其他设备: http://[本机IP]:8000")

    sockets = []

    # === IPv6 双栈套接字 ===
    try:
        sock6 = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        sock6.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock6.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
            print("✅ 成功解除 IPV6_V6ONLY 限制，网络引擎已进入双栈监听状态")
        except Exception as e:
            print("⚠️ 双栈策略配置提示: " + str(e))
        sock6.bind(("::", 8000))
        sock6.listen(5)
        sockets.append(sock6)
    except Exception as e:
        print("❌ IPv6 套接字绑定失败（8000）: " + str(e))

    # === IPv4 独立套接字兜底 ===
    try:
        sock4 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock4.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock4.bind(("0.0.0.0", 8000))
            sock4.listen(5)
            sockets.append(sock4)
            print("✅ IPv4 兜底套接字也已就绪 (0.0.0.0:8000)")
        except Exception as e2:
            print("ℹ️ IPv4 8000 已被双栈占用，跳过独立套接字")
    except Exception as e:
        print("ℹ️ IPv4 套接字创建提示: " + str(e))

    if not sockets:
        print("❌ 没有任何套接字可以监听，退出")
        import sys
        sys.exit(1)

    config = Config("app.main:app", host="::", port=8000, reload=False, forwarded_allow_ips="*")
    server = Server(config)
    server.run(sockets=sockets)