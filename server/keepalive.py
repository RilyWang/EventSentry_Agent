"""
守护进程 —— 保障「本地服务 + Cloudflare 隧道」持续在线

核心设计（v2）：**健康判定只用本地信号**
  旧版的致命缺陷：用「从本机访问公网隧道地址」的结果来判断隧道死活。
  但本机网络对境外 TLS 存在探测阻断（github / npm / cloudflare.com 均为 000），
  导致健康的隧道每隔约 6 分钟被误判为「已挂」→ 杀掉重启 → 每次都换一个新的
  随机域名 → 已发布的链接全部失效。这是"地址不稳定"的真正原因。

  新版判定依据（全部是本机可 100% 可靠读取的）：
    1. 本地服务：GET http://localhost:PORT/api/ping
    2. 隧道连接数：读取 cloudflared 本地指标 http://127.0.0.1:20241/metrics
       中的 cloudflared_tunnel_ha_connections（>=1 即与 Cloudflare 边缘握手正常）
    3. 隧道日志：cloudflared 自报 "Registered tunnel connection"
  公网可达性探测仅作**参考记录**，绝不触发重启。

  结果：只要 cloudflared 进程活着，**域名就保持不变**；只有进程真的死了才重启。

用法：
    python keepalive.py            # 前台运行（看日志）
    nohup python keepalive.py &    # 后台运行

说明：这是「提高可用性」的措施。免费快速隧道的域名在**进程重启后**必然变化；
      要永久固定域名，需「具名隧道 + 自有域名」（见 docs/09-deploy/）。
"""
import os
import re
import subprocess
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ.setdefault("no_proxy", "*")
os.environ.setdefault("NO_PROXY", "*")

import requests

# ─── 配置（可用环境变量覆盖） ───
HERE = os.path.dirname(os.path.abspath(__file__))
SERVER_PORT = os.getenv("PORT", "3000")
SERVER_URL = f"http://localhost:{SERVER_PORT}"
CLOUDFLARED = os.getenv("CLOUDFLARED_BIN", r"D:\Zcode\tools\cloudflared.exe")
TUNNEL_LOG = os.getenv("TUNNEL_LOG", r"D:\Zcode\tools\tunnel.log")
URL_FILE = os.path.join(HERE, "tunnel_url.txt")
STATUS_FILE = os.path.join(HERE, "tunnel_status.log")
CHECK_INTERVAL = int(os.getenv("KEEPALIVE_INTERVAL", "30"))
METRICS_URL = os.getenv("CLOUDFLARED_METRICS", "http://127.0.0.1:20241/metrics")
HA_CONNECTIONS = int(os.getenv("TUNNEL_HA_CONNECTIONS", "4"))
PROXIES = {"http": None, "https": None}

# 隧道「零连接」容忍次数（每次 30s，默认 6 次 = 3 分钟）。
# cloudflared 自身有重连退避，给足时间避免误杀。
TUNNEL_IDLE_TOLERANCE = int(os.getenv("TUNNEL_IDLE_TOLERANCE", "6"))

TUNNEL_URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def status(msg):
    """写入状态日志（供测试报告 / 排查取证）"""
    try:
        with open(STATUS_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass
    log(msg)


# ─── ① 本地服务 ───
def server_alive() -> bool:
    try:
        r = requests.get(f"{SERVER_URL}/api/ping", timeout=8, proxies=PROXIES)
        return r.status_code == 200
    except Exception:
        return False


def start_server():
    log("本地服务不可用 → 重启中…")
    env = dict(os.environ, no_proxy="*", NO_PROXY="*")
    logfile = open(os.path.join(HERE, "server.log"), "a", encoding="utf-8")
    subprocess.Popen([sys.executable, "-u", "-X", "utf8", "main.py"],
                     cwd=HERE, env=env, stdout=logfile, stderr=logfile,
                     creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))


# ─── ② 隧道（本地信号） ───
def tunnel_ha_connections():
    """
    读取 cloudflared 本地指标，返回当前与 Cloudflare 边缘的活跃连接数。
    返回 None 表示指标端口不可达 —— 即 cloudflared 进程已死。
    这是**最可靠**的隧道健康信号：完全走本地回环，不受公网阻断影响。
    """
    try:
        r = requests.get(METRICS_URL, timeout=5, proxies=PROXIES)
        if r.status_code != 200:
            return None
        m = re.search(r"^cloudflared_tunnel_ha_connections\s+(\d+)", r.text, re.M)
        return int(m.group(1)) if m else 0
    except Exception:
        return None


def current_tunnel_url():
    """从隧道日志读取当前公网地址（日志是唯一权威来源）"""
    if not os.path.exists(TUNNEL_LOG):
        return None
    try:
        txt = open(TUNNEL_LOG, encoding="utf-8", errors="ignore").read()
        urls = [u for u in TUNNEL_URL_RE.findall(txt) if "api.trycloudflare.com" not in u]
        return urls[-1] if urls else None
    except Exception:
        return None


def registered_connection() -> bool:
    """cloudflared 是否自报已注册隧道连接"""
    try:
        txt = open(TUNNEL_LOG, encoding="utf-8", errors="ignore").read()
        return "Registered tunnel connection" in txt
    except Exception:
        return False


def save_url(url):
    try:
        old = open(URL_FILE, encoding="utf-8").read().strip() if os.path.exists(URL_FILE) else ""
    except Exception:
        old = ""
    try:
        with open(URL_FILE, "w", encoding="utf-8") as f:
            f.write(url + "\n")
    except Exception:
        pass
    if old != url:
        status(f"PUBLIC_URL={url}")


def remote_reachable(url) -> bool:
    """
    公网可达性探测 —— **仅供参考记录，绝不触发重启**。
    本机对境外 TLS 存在阻断，该探测在本机常为 False，但不代表外部用户不可达。
    """
    try:
        r = requests.get(f"{url}/api/ping", timeout=15, proxies=PROXIES)
        return r.status_code == 200
    except Exception:
        return False


_last_tunnel_restart = 0.0
TUNNEL_RESTART_COOLDOWN = int(os.getenv("TUNNEL_RESTART_COOLDOWN", "120"))


def kill_cloudflared():
    """重启前清理残留进程，避免多进程抢占隧道"""
    try:
        subprocess.run(["taskkill", "/F", "/IM", "cloudflared.exe"],
                       capture_output=True, timeout=20)
    except Exception:
        pass
    time.sleep(4)


def start_tunnel():
    """仅当 cloudflared 进程真的死了才调用。重启会更换域名（无账号快速隧道固有行为）。"""
    global _last_tunnel_restart
    now = time.time()
    if now - _last_tunnel_restart < TUNNEL_RESTART_COOLDOWN:
        left = int(TUNNEL_RESTART_COOLDOWN - (now - _last_tunnel_restart))
        log(f"距离上次重启不足 {TUNNEL_RESTART_COOLDOWN}s，冷却中（还需 {left}s），本轮跳过")
        return None
    _last_tunnel_restart = now

    status("隧道进程不可用 → 重启中（⚠️ 域名将变更）…")
    kill_cloudflared()

    logfile = open(TUNNEL_LOG, "w", encoding="utf-8")
    args = [CLOUDFLARED, "tunnel", "--url", SERVER_URL,
            "--protocol", "http2", "--no-autoupdate",
            "--ha-connections", str(HA_CONNECTIONS),
            "--metrics", "127.0.0.1:20241"]
    subprocess.Popen(args, stdout=logfile, stderr=logfile,
                     creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))

    # 等待地址生成（最长 120s）
    for _ in range(40):
        time.sleep(3)
        url = current_tunnel_url()
        if url and registered_connection():
            save_url(url)
            status(f"隧道已重建 → {url}")
            return url
    status("隧道启动失败，稍后重试")
    return None


# ─── 主循环 ───
def main():
    log("=" * 58)
    log("EventSentry 守护进程已启动（本地信号判定版）")
    log(f"  探测周期: {CHECK_INTERVAL}s | 本地: {SERVER_URL}")
    log(f"  隧道健康依据: cloudflared 本地指标 {METRICS_URL}")
    log("=" * 58)

    # 启动时：从日志恢复真实地址并发布（修正可能过期的 tunnel_url.txt）
    url0 = current_tunnel_url()
    if url0:
        save_url(url0)
        log(f"当前公网地址: {url0}")

    fail_server = 0
    idle_tunnel = 0
    last_remote_state = None

    while True:
        try:
            # ① 本地服务
            if server_alive():
                if fail_server:
                    log("本地服务已恢复 ✅")
                fail_server = 0
            else:
                fail_server += 1
                if fail_server >= 2:          # 连续 2 次失败才重启，避免误判
                    start_server()
                    fail_server = 0
                    time.sleep(10)

            if not server_alive():
                time.sleep(CHECK_INTERVAL)
                continue

            # ② 隧道：只看本地信号
            ha = tunnel_ha_connections()
            url = current_tunnel_url()

            if ha is None:
                # 指标端口不可达 = 进程已死
                idle_tunnel += 1
                log(f"cloudflared 指标端口不可达（{idle_tunnel}/2）")
                if idle_tunnel >= 2:
                    start_tunnel()
                    idle_tunnel = 0
            elif ha >= 1:
                if idle_tunnel:
                    log("隧道已恢复 ✅")
                idle_tunnel = 0
                if url:
                    save_url(url)
                # 参考记录：本机能否访问公网地址（不参与判定）
                ok = remote_reachable(url) if url else False
                if ok != last_remote_state:
                    note = "本机可达" if ok else "本机不可达（网络阻断，不影响外部用户）"
                    status(f"公网探测: {note} | {url}")
                    last_remote_state = ok
            else:
                # 进程活着但连接数为 0：cloudflared 正在自行重连，给足容忍时间
                idle_tunnel += 1
                log(f"隧道连接数 0（{idle_tunnel}/{TUNNEL_IDLE_TOLERANCE}），"
                    f"等待 cloudflared 自动重连…")
                if idle_tunnel >= TUNNEL_IDLE_TOLERANCE:
                    start_tunnel()
                    idle_tunnel = 0
        except KeyboardInterrupt:
            log("收到中断，退出")
            break
        except Exception as e:
            log(f"探测异常: {type(e).__name__}: {e}")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
