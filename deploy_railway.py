"""
Railway 一键部署 —— 免费、无需信用卡、不依赖本机开机

前置：已执行 railway login 并在浏览器完成授权
用法：python deploy_railway.py
"""
import os
import re
import shutil
import subprocess
import sys
import time

os.environ.setdefault("no_proxy", "*")
os.environ.setdefault("NO_PROXY", "*")

import requests

ROOT = os.path.dirname(os.path.abspath(__file__))
S = {"http": None, "https": None}
PROJECT = "eventsentry"
SERVICE = "eventsentry"


def resolve_railway():
    """定位 railway 可执行文件（Windows 下 npm 的 .cmd 包装无法被 subprocess 直接调用）"""
    appdata = os.environ.get("APPDATA", "")
    candidates = [
        os.path.join(appdata, "npm", "node_modules", "@railway", "cli", "bin", "railway.exe"),
        os.path.join(appdata, "npm", "railway.cmd"),
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return shutil.which("railway") or "railway"


RAILWAY = resolve_railway()


def sh(args, timeout=600, quiet=False):
    """执行命令并回显输出"""
    if not quiet:
        label = os.path.basename(str(args[0]))
        print("  $ " + label + " " + " ".join(str(a) for a in args[1:]), flush=True)
    use_shell = str(args[0]).lower().endswith(".cmd")
    try:
        p = subprocess.run(args, cwd=ROOT, capture_output=True, text=True,
                           timeout=timeout, shell=use_shell,
                           encoding="utf-8", errors="ignore")
    except Exception as e:
        return 1, type(e).__name__ + ": " + str(e)
    out = (p.stdout or "") + (p.stderr or "")
    if not quiet:
        for line in out.splitlines():
            if line.strip():
                print("    " + line[:170], flush=True)
    return p.returncode, out


def load_env():
    """从 server/.env 读取密钥"""
    p = os.path.join(ROOT, "server", ".env")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def main():
    load_env()
    print("=" * 62)
    print(" EventSentry -> Railway 部署")
    print("=" * 62)
    print(" railway: " + RAILWAY)

    print("\n[1/6] 检查登录状态...")
    code, out = sh([RAILWAY, "whoami"])
    if "Unauthorized" in out or code != 0:
        print("\n[!] 未登录。请打开 https://railway.com/activate 完成授权后重试")
        return 1
    print("  [OK] 已登录")

    print("\n[2/6] 关联项目...")
    sh([RAILWAY, "link", "--project", PROJECT, "--service", SERVICE])

    print("\n[3/6] 配置环境变量...")
    envs = {
        "PORT": "3000",
        "ENABLE_SCHEDULER": "1",
        "SCHEDULER_RUN_ON_START": "0",
        "LLM_BASE_URL": os.getenv("LLM_BASE_URL", "https://open.bigmodel.cn/api/anthropic"),
        "LLM_MODEL": os.getenv("LLM_MODEL", "glm-4.6"),
    }
    if os.getenv("LLM_API_KEY"):
        envs["LLM_API_KEY"] = os.getenv("LLM_API_KEY")
    if os.getenv("SERPER_API_KEY"):
        envs["SERPER_API_KEY"] = os.getenv("SERPER_API_KEY")

    args = [RAILWAY, "variables", "--service", SERVICE]
    for k, v in envs.items():
        args += ["--set", k + "=" + v]
    sh(args)

    print("\n[4/6] 开始部署（首次约 3-6 分钟）...")
    sh([RAILWAY, "up", "--detach", "--service", SERVICE], timeout=900)

    print("\n[5/6] 生成公网域名...")
    code, out = sh([RAILWAY, "domain", "--service", SERVICE])
    m = re.search(r"https://[A-Za-z0-9.-]+\.up\.railway\.app", out)
    url = m.group(0) if m else None
    if not url:
        print("  [i] 若未拿到域名，请到 Railway 控制台 -> Settings -> Networking -> Generate Domain")

    print("\n[6/6] 健康检查...")
    if not url:
        return 0
    for i in range(14):
        time.sleep(15)
        try:
            r = requests.get(url + "/api/ping", timeout=30, proxies=S)
            if r.status_code == 200:
                n = "?"
                try:
                    n = requests.get(url + "/api/events?limit=1", timeout=30, proxies=S).json().get("total")
                except Exception:
                    pass
                print("\n" + "=" * 62)
                print(" 部署成功！固定地址: " + url)
                print(" 事件数: " + str(n))
                print("=" * 62)
                print("\n下一步（绑自定义域名，在阿里云 DNS 加 CNAME）:")
                print("  主机记录: eventsentry")
                print("  记录值  : " + url.replace("https://", ""))
                return 0
        except Exception:
            pass
        print("  ...等待服务就绪 (" + str(i + 1) + "/14)")
    print("  [!] 暂未响应，稍后自行访问: " + url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
