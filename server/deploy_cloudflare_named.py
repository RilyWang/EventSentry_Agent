"""
Cloudflare 具名隧道一键部署 —— 拿到**永久固定**的公网地址

前置（需要用户提供）：
  1. 一个已接入 Cloudflare 的域名（Zone）
  2. 有效的 Cloudflare API Token，权限：
       Account → Cloudflare Tunnel → Edit
       Zone    → DNS               → Edit
       Zone    → Zone              → Read

用法：
  在项目根目录执行
      python server/deploy_cloudflare_named.py <域名> [子域名]

  例如：
      python server/deploy_cloudflare_named.py example.com eventsentry
      → 最终地址 https://eventsentry.example.com

凭据从 server/.env 读取：
      CLOUDFLARE_API_TOKEN=...
      CLOUDFLARE_ACCOUNT_ID=...   （可留空，脚本会自动查）
"""
import json
import os
import re
import subprocess
import sys
import time

os.environ.setdefault("no_proxy", "*")
os.environ.setdefault("NO_PROXY", "*")

import requests

API = "https://api.cloudflare.com/client/v4"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CLOUDFLARED = os.getenv("CLOUDFLARED_BIN", r"D:\Zcode\tools\cloudflared.exe")
CF_DIR = os.path.expanduser("~/.cloudflared")


def load_env():
    """从 server/.env 读取凭据"""
    env_path = os.path.join(HERE, ".env")
    if os.path.exists(env_path):
        for line in open(env_path, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def log(m):
    print(m, flush=True)


def api(method, path, token, **kw):
    r = requests.request(method, API + path,
                         headers={"Authorization": f"Bearer {token}",
                                  "Content-Type": "application/json"},
                         timeout=45, proxies={"http": None, "https": None}, **kw)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {"raw": r.text[:300]}


def main():
    load_env()
    token = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
    if not token:
        log("❌ 缺少 CLOUDFLARE_API_TOKEN（请写入 server/.env）")
        return 1

    if len(sys.argv) < 2:
        log("用法: python server/deploy_cloudflare_named.py <域名> [子域名]")
        return 1
    zone_name = sys.argv[1].strip().lower()
    sub = (sys.argv[2] if len(sys.argv) > 2 else "eventsentry").strip().lower()
    host = f"{sub}.{zone_name}"

    log("=" * 62)
    log(f"Cloudflare 具名隧道部署 → https://{host}")
    log("=" * 62)

    # ── 1. 校验 Token ──
    log("\n[1/6] 校验 API Token…")
    code, d = api("GET", "/user/tokens/verify", token)
    if not d.get("success"):
        log(f"  ❌ Token 无效 (HTTP {code}): {json.dumps(d.get('errors'), ensure_ascii=False)}")
        log("  → 请到 Cloudflare 后台「我的个人资料 → API 令牌」重新创建")
        return 1
    log(f"  ✅ Token 有效（状态 {d['result'].get('status')}）")

    # ── 2. 定位 Zone ──
    log(f"\n[2/6] 查找域名 {zone_name}…")
    code, d = api("GET", f"/zones?name={zone_name}", token)
    if not d.get("success") or not d["result"]:
        log("  ❌ 未找到该域名。可能原因：")
        log("     · 域名未接入 Cloudflare（需在后台 Add a site 并改 NS）")
        log("     · Token 缺少 Zone:Read 权限")
        return 1
    zone = d["result"][0]
    zone_id = zone["id"]
    account_id = zone["account"]["id"]
    log(f"  ✅ Zone: {zone['name']}（状态 {zone['status']}，account {account_id[:12]}…）")

    # ── 3. 创建或复用隧道 ──
    tunnel_name = sub
    log(f"\n[3/6] 创建具名隧道 {tunnel_name}…")
    code, d = api("POST", f"/accounts/{account_id}/cfd_tunnel", token,
                  json={"name": tunnel_name, "config_src": "local"})
    if d.get("success"):
        tunnel_id = d["result"]["id"]
        log(f"  ✅ 已创建，隧道 ID: {tunnel_id}")
    else:
        # 可能已存在，尝试查出来
        code2, d2 = api("GET", f"/accounts/{account_id}/cfd_tunnel?name={tunnel_name}&is_deleted=false", token)
        if d2.get("success") and d2["result"]:
            tunnel_id = d2["result"][0]["id"]
            log(f"  ℹ️ 已存在，复用隧道 ID: {tunnel_id}")
        else:
            log(f"  ❌ 创建失败: {json.dumps(d.get('errors'), ensure_ascii=False)}")
            return 1

    # ── 4. 写入 tunnel token 与配置文件 ──
    log("\n[4/6] 写入本地配置…")
    os.makedirs(CF_DIR, exist_ok=True)
    code, d = api("GET", f"/accounts/{account_id}/cfd_tunnel/{tunnel_id}/token", token)
    if not d.get("success"):
        log(f"  ❌ 获取隧道 token 失败: {json.dumps(d.get('errors'), ensure_ascii=False)}")
        return 1
    ttoken = d["result"]

    token_file = os.path.join(CF_DIR, f"{tunnel_name}.token")
    with open(token_file, "w", encoding="utf-8") as f:
        f.write(ttoken)

    cfg = f"""tunnel: {tunnel_id}
credentials-file: {token_file.replace(chr(92), '/')}
ingress:
  - hostname: {host}
    service: http://localhost:3000
  - service: http_status:404
"""
    cfg_file = os.path.join(CF_DIR, f"{tunnel_name}.yml")
    with open(cfg_file, "w", encoding="utf-8") as f:
        f.write(cfg)
    log(f"  ✅ 配置: {cfg_file}")

    # ── 5. 绑定 DNS（CNAME → 隧道） ──
    log(f"\n[5/6] 绑定 DNS: {host} → 隧道…")
    ok = False
    for attempt, body in enumerate([
        # 新版：直接指向隧道
        {"type": "CNAME", "name": sub, "content": f"{tunnel_id}.cfargotunnel.com", "proxied": True},
        # 兼容：指向 v2 域名
        {"type": "CNAME", "name": sub, "content": f"{tunnel_id}.cfargotunnel.com", "proxied": True, "ttl": 1},
    ]):
        code, d = api("POST", f"/zones/{zone_id}/dns_records", token, json=body)
        if d.get("success"):
            log(f"  ✅ DNS 记录已创建: {host}")
            ok = True
            break
        errs = d.get("errors") or []
        if any(e.get("code") == 81057 for e in errs):   # 记录已存在
            log("  ℹ️ DNS 记录已存在，跳过")
            ok = True
            break

    if not ok:
        log(f"  ⚠️ DNS 绑定失败: {json.dumps(d.get('errors'), ensure_ascii=False)}")
        log(f"  → 可手动执行: cloudflared tunnel route dns {tunnel_name} {host}")

    # ── 6. 启动隧道 ──
    log("\n[6/6] 启动隧道…")
    subprocess.run(["taskkill", "/F", "/IM", "cloudflared.exe"], capture_output=True)
    time.sleep(3)
    out_dir = r"D:\Zcode\tools"
    logfile = open(os.path.join(out_dir, f"tunnel_{tunnel_name}.log"), "w", encoding="utf-8")
    p = subprocess.Popen(
        [CLOUDFLARED, "tunnel", "--config", cfg_file, "run", tunnel_name],
        stdout=logfile, stderr=logfile,
        creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    log(f"  cloudflared PID: {p.pid}")
    time.sleep(15)

    # ── 验收 ──
    log("\n" + "=" * 62)
    url = f"https://{host}"
    try:
        r = requests.get(url + "/api/ping", timeout=40, proxies={"http": None, "https": None})
        log(f"✅ 固定地址已就绪: {url}  (HTTP {r.status_code})")
        r2 = requests.get(url + "/api/events?limit=1", timeout=40, proxies={"http": None, "https": None})
        log(f"   事件数: {r2.json().get('total')}")
    except Exception as e:
        log(f"⚠️ 暂时不可达（DNS 传播通常需 1-5 分钟）: {type(e).__name__}")
        log(f"   稍后可自行访问: {url}")
    log("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
