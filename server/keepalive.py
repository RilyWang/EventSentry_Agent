"""
守护进程 —— 保障「本地服务 + Cloudflare 隧道」持续在线

能力：
  1. 每 30 秒探测本地服务；若挂掉则自动重启
  2. 每 30 秒探测隧道；若挂掉则自动重启并输出**新的公网地址**
  3. 地址变化时写入 tunnel_url.txt，便于外部读取

用法：
    python keepalive.py            # 前台运行（看日志）
    nohup python keepalive.py &    # 后台运行

注意：这是「提高可用性」的措施，**无法保证地址稳定**。
      要固定地址，需用「具名隧道 + 自有域名」，需要有效的 Cloudflare API Token
      与已接入 Cloudflare 的域名。
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
CHECK_INTERVAL = int(os.getenv("KEEPALIVE_INTERVAL", "30"))
PROXIES = {"http": None, "https": None}

TUNNEL_URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


# ─── 本地服务 ───
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


# ─── 隧道 ───
def tunnel_process_running() -> bool:
    """
    检查 cloudflared 进程。
    注：不使用 subprocess+tasklist（Windows 中文输出会触发解码错误），
    改用 ShellExecute 无关的轻量方式：读取 tunnel.log 的更新时间来间接判断。
    """
    try:
        if not os.path.exists(TUNNEL_LOG):
            return False
        # 日志在 5 分钟内有更新，视为进程存活
        return (time.time() - os.path.getmtime(TUNNEL_LOG)) < 300
    except Exception:
        return False


def current_tunnel_url():
    if not os.path.exists(TUNNEL_LOG):
        return None
    try:
        txt = open(TUNNEL_LOG, encoding="utf-8", errors="ignore").read()
        urls = TUNNEL_URL_RE.findall(txt)
        # 过滤掉 Cloudflare 自身的 API 域名
        urls = [u for u in urls if "api.trycloudflare.com" not in u]
        return urls[-1] if urls else None
    except Exception:
        return None


def tunnel_healthy(retries: int = 2) -> bool:
    """探活隧道（重试若干次，避免边缘抖动导致误判而触发重启）"""
    if not tunnel_process_running():
        return False
    url = current_tunnel_url()
    if not url:
        return False
    for i in range(retries):
        try:
            r = requests.get(f"{url}/api/ping", timeout=15, proxies=PROXIES)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        if i < retries - 1:
            time.sleep(5)
    return False


def kill_cloudflared():
    """重启前先杀掉已有 cloudflared，避免多进程抢地址"""
    try:
        subprocess.run(["taskkill", "/F", "/IM", "cloudflared.exe"],
                       capture_output=True, timeout=20)
    except Exception:
        pass
    time.sleep(4)


_last_tunnel_restart = 0.0
TUNNEL_RESTART_COOLDOWN = int(os.getenv("TUNNEL_RESTART_COOLDOWN", "300"))  # 默认 5 分钟


def start_tunnel():
    """
    重启隧道。
    注意：Cloudflare 对快速隧道创建有频率限制，过于频繁会卡在
    "Requesting new quick Tunnel..." 而建不起来 —— 故加冷却时间。
    """
    global _last_tunnel_restart
    now = time.time()
    if now - _last_tunnel_restart < TUNNEL_RESTART_COOLDOWN:
        left = int(TUNNEL_RESTART_COOLDOWN - (now - _last_tunnel_restart))
        log(f"距上次重启不足 {TUNNEL_RESTART_COOLDOWN}s，冷却中（还需 {left}s），本轮跳过")
        return None
    _last_tunnel_restart = now

    log("隧道不可用 → 重启中（先清理旧进程，再以 http2 协议启动）…")
    kill_cloudflared()

    logfile = open(TUNNEL_LOG, "w", encoding="utf-8")
    subprocess.Popen(
        [CLOUDFLARED, "tunnel", "--url", SERVER_URL,
         "--protocol", "http2", "--no-autoupdate"],
        stdout=logfile, stderr=logfile,
        creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))

    # 等待地址生成（最长 120s）
    for _ in range(40):
        time.sleep(3)
        url = current_tunnel_url()
        if url and "Registered tunnel connection" in _read_log():
            save_url(url)
            return url
    return None


def _read_log():
    try:
        return open(TUNNEL_LOG, encoding="utf-8", errors="ignore").read()
    except Exception:
        return ""


def save_url(url):
    try:
        with open(URL_FILE, "w", encoding="utf-8") as f:
            f.write(url + "\n")
    except Exception:
        pass


# ─── 主循环 ───
def main():
    log("=" * 58)
    log("EventSentry 守护进程已启动")
    log(f"  探测周期: {CHECK_INTERVAL}s | 本地: {SERVER_URL}")
    log("=" * 58)

    url = current_tunnel_url()
    if url:
        log(f"当前公网地址: {url}")
        save_url(url)

    fail_server = 0
    fail_tunnel = 0

    while True:
        try:
            # ① 本地服务
            if server_alive():
                if fail_server:
                    log("本地服务已恢复 ✅")
                fail_server = 0
            else:
                fail_server += 1
                if fail_server >= 2:      # 连续 2 次失败才重启，避免误判
                    start_server()
                    fail_server = 0
                    time.sleep(10)

            # ② 隧道（本地服务正常时才检查隧道）
            if server_alive():
                if tunnel_healthy():
                    if fail_tunnel:
                        log("隧道已恢复 ✅")
                    fail_tunnel = 0
                else:
                    fail_tunnel += 1
                    # 阈值放宽到 3 次（约 90s 连续不可用才重启），避免误判抖动
                    if fail_tunnel >= 3:
                        new_url = start_tunnel()
                        if new_url:
                            log(f"⚠️ 公网地址已变更 → {new_url}")
                        else:
                            log("隧道启动失败，稍后重试")
                        fail_tunnel = 0
        except KeyboardInterrupt:
            log("收到中断，退出")
            break
        except Exception as e:
            log(f"探测异常: {type(e).__name__}: {e}")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
