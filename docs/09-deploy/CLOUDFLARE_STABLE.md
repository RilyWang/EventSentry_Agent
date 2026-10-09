# Cloudflare 稳定部署指引

> 目标：把本地运行的 EventSentry 映射为**固定不变**的公网地址
> 更新日期：2026-10-09

---

## 一、当前状态（临时隧道）

| 项 | 值 |
|----|-----|
| 方式 | Cloudflare **无账号快速隧道**（`cloudflared tunnel --url`） |
| 地址 | 见根目录 `提交表格清单.md` 的「Web 产品 URL」 |
| 协议 | `http2`（本网络 QUIC/UDP 受限，必须指定 http2） |
| 守护 | `server/keepalive.py` 每 30 秒探测，服务/隧道挂掉自动重启 |
| ⚠️ 限制 | **每次隧道重启都会更换地址**，无可用性保证 |

**为什么不用快速隧道的默认协议（QUIC）？**
本网络实测 `region1.v2.argotunnel.com:443` 超时、UDP 7844 失败，
QUIC 无法建连（表现为公网返回 **HTTP 530**）；改用 `--protocol http2` 后正常。

**守护进程用法：**
```bash
cd server
python keepalive.py            # 前台（可看日志）
# 或后台： nohup python -u keepalive.py > keepalive.log 2>&1 &
```
- 当前地址写入 `server/tunnel_url.txt`
- 本地服务挂掉 → 自动重启
- 隧道挂掉 → 自动重启并输出**新地址**（日志有 `⚠️ 公网地址已变更` 标记）

---

## 二、要「固定地址」需要什么（具名隧道）

固定地址 = **具名隧道（Named Tunnel）+ 自有域名**。前置条件两项：

### ① 有效的 Cloudflare API Token
在 Cloudflare 后台创建：**我的个人资料 → API 令牌 → 创建令牌 → 自定义令牌**

所需权限：

| 权限 | 作用 |
|------|------|
| `Account` → `Cloudflare Tunnel` → **Edit** | 创建/管理隧道 |
| `Zone` → `DNS` → **Edit** | 为隧道添加 DNS 记录 |
| `Zone` → `Zone` → **Read** | 列出可用域名 |

> ⚠️ 令牌只在创建时显示一次，请立即复制保存。
> ⚠️ **不要**把令牌提交到 Git 仓库——本项目已把 `server/.env` 加入 `.gitignore`。

### ② 账号下已接入一个域名（Zone）
域名需已 **添加到 Cloudflare** 并处于 Active 状态（NS 已生效）。
没有域名时**无法**给具名隧道绑定固定主机名。

---

## 三、拿到 Token 后的部署步骤

### 方式 A：用脚本一键部署（推荐）

```bash
cd server
# 把凭证写入 .env（该文件已被 gitignore）
cat >> .env <<'EOF'
CLOUDFLARE_API_TOKEN=<你的令牌>
CLOUDFLARE_ACCOUNT_ID=<你的账号ID>
CLOUDFLARE_ZONE=<你的域名，如 example.com>
CLOUDFLARE_HOST=<期望域名，如 eventsentry.example.com>
EOF

python deploy_cloudflare.py    # 脚本将：
                               # 1) 校验 Token 与权限
                               # 2) 创建具名隧道
                               # 3) 添加 DNS CNAME 指向隧道
                               # 4) 输出 cloudflared 运行命令
```

### 方式 B：手动命令

```bash
export CLOUDFLARE_API_TOKEN=<你的令牌>

# 1. 登录（会生成证书）
cloudflared tunnel login

# 2. 创建具名隧道
cloudflared tunnel create eventsentry

# 3. 路由到自有域名
cloudflared tunnel route dns eventsentry eventsentry.example.com

# 4. 用配置文件运行（固定地址）
cat > ~/.cloudflared/config.yml <<'EOF'
tunnel: eventsentry
credentials-file: ~/.cloudflared/<隧道ID>.json
ingress:
  - hostname: eventsentry.example.com
    service: http://localhost:3000
  - service: http_status:404
EOF

cloudflared tunnel run eventsentry
```

完成后地址固定为 `https://eventsentry.example.com`，**重启不变**。

---

## 四、备选方案（Cloudflare 之外）

如果拿不到令牌或没有域名，可考虑把 Python 后端部署到原生支持 Python 的平台：

| 平台 | 说明 | 需要 |
|------|------|------|
| Railway / Render / Fly.io | 原生支持 Python，含免费额度 | 平台账号 |
| 阿里云 / 腾讯云 ECS | 完全可控 | 服务器 + 域名 + 备案 |
| PythonAnywhere | 纯 Python 托管 | 账号 |

> ❌ **Cloudflare Workers / Pages 不可用**：Workers 只支持 JS/WASM，
> 无法运行本项目的 Python FastAPI + SQLite 后端。

---

## 五、安全注意事项

1. **不要把 API Token / 密钥写进代码或提交仓库**
   - `server/.env` 已在 `.gitignore` 中
   - 本项目的 LLM / Serper 密钥同样从 `.env` 读取
2. **令牌泄露应立即在 Cloudflare 后台撤销并重建**
3. **提交材料中不要包含任何 Token**
4. 生产环境建议为 `.env` 设置文件权限（仅本人可读）

---

## 六、常见问题

| 现象 | 原因 | 解决 |
|------|------|------|
| 公网 HTTP **530** | 隧道 QUIC 建连失败 | 加 `--protocol http2` 重启隧道 |
| 地址突然失效 | 快速隧道进程重启 | 查 `server/tunnel_url.txt` 或用守护进程自动更新 |
| `Invalid API Token` | 令牌错误/已撤销/权限不足 | 重新创建令牌，核对权限 |
| 无法 `route dns` | 账号下没有该域名 | 先把域名接入 Cloudflare |
| 隧道反复重启 | 健康探测过于严格 | 调整 `keepalive.py` 的 `CHECK_INTERVAL` / 失败阈值 |
