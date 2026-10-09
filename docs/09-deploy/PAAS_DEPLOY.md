# 免费 PaaS 部署指引（无需域名，地址固定）

> 目标：拿到一个**固定不变**的公网地址，且**不依赖本机开机**
> 适用：没有域名、没有 Cloudflare 付费能力的情况
> 更新日期：2026-10-09

---

## 为什么推荐这条路

| 方案 | 地址固定 | 免注册 | 浏览器可直开 | 依赖本机开机 |
|------|:---:|:---:|:---:|:---:|
| Cloudflare 快速隧道 | ❌ 重启即变 | ✅ | ✅ | **是** |
| localtunnel 固定子域 | ✅ | ✅ | ❌ **有 HTTP 511 拦截页** | 是 |
| serveo 固定子域 | ✅ | ❌ 需注册 SSH 密钥 | ✅ | 是 |
| ngrok 免费静态域 | ✅ | ❌ 需注册 | ✅ | 是 |
| **PaaS 部署（本方案）** | ✅ | ❌ 需注册 | ✅ | **否** ← 关键优势 |

**PaaS 部署的最大好处**：应用跑在云上，**你电脑关机、隧道断了都不影响**。评委随时能打开。

---

## 零、账号注册（必读）

### 方案一：Render（推荐，免费、**不需要信用卡**）

1. 打开 https://render.com
2. 点右上角 **Get Started** → 选 **GitHub** 登录（授权后会读你的仓库）
3. 登录后在控制台点 **New +** → **Blueprint**
4. 选择仓库 **EventSentry_Agent** → Render 会自动识别根目录的 `render.yaml` → 点 **Apply**
5. 部署时在 **Environment** 里补两个密钥（见下方「环境变量清单」）
6. 等待 3-5 分钟 → 得到固定地址 `https://eventsentry.onrender.com`

> ⚠️ Render 免费实例**闲置 15 分钟会休眠**，再次访问需等 30-60 秒冷启动。
> 免费套餐**没有持久磁盘**，但本项目已支持「从仓库内置数据库自动初始化」，
> 所以部署后**开箱就有 121 个真实事件**。

### 方案二：Fly.io（需绑定信用卡验证，有免费额度）

1. 打开 https://fly.io
2. 点 **Sign Up** → 选 **GitHub** 登录
3. 按提示**绑定信用卡**（仅身份验证，免费额度内不扣费；不绑卡无法开通）
4. 安装 flyctl（本项目已下载到 `D:\Zcode	oolslylyctl.exe`）
5. 本地执行一键部署脚本：
   ```powershell
   cd D:/Zcode/Agent_投资事件追踪
   powershell -ExecutionPolicy Bypass -File deploy_fly.ps1
   ```
6. 脚本会引导你输入密钥并完成创建应用 → 建卷 → 部署 → 健康检查
7. 得到固定地址 `https://eventsentry.fly.dev`

### 方案三：Railway

1. 打开 https://railway.app → **Login with GitHub**
2. **New Project → Deploy from GitHub repo** → 选 **EventSentry_Agent**
3. Railway 自动读取根目录 `railway.json`（Dockerfile 构建）
4. **Variables** 里填密钥 → **Settings → Networking → Generate Domain**

---

## 一、Fly.io 部署细节

### 前提
- 注册 https://fly.io （可用 GitHub 登录）
- 本地安装 `flyctl`：
  ```bash
  # Windows PowerShell
  iwr https://fly.io/install.ps1 -useb | iex
  ```

### 部署步骤

```bash
cd D:/Zcode/Agent_投资事件追踪

# 1. 登录
fly auth login

# 2. 创建应用（本项目已有 fly.toml，直接用它）
fly launch --no-deploy --copy-config

# 3. 创建持久卷（SQLite 数据存这里，1GB 免费额度够用）
fly volumes create eventsentry_data --size 1 --region hkg

# 4. 注入密钥（不写进代码）
fly secrets set \
  LLM_API_KEY=<你的智谱Key> \
  LLM_BASE_URL=https://open.bigmodel.cn/api/anthropic \
  LLM_MODEL=glm-4.6 \
  SERPER_API_KEY=<你的SerperKey>

# 5. 部署
fly deploy

# 6. 打开
fly open
```

**得到固定地址**：`https://eventsentry.fly.dev`（重启、重新部署都不变）

### 首次部署后导入数据

数据库在持久卷上是空的，用内置脚本灌入真实数据：

```bash
# 方式 A：本地采集后上传数据库
cd server && python _run_pipeline.py
fly ssh sftp shell        # 进入 sftp 后 put db_data/eventsentry.db /data/eventsentry.db

# 方式 B：直接在云端跑一次采集（会调用 iFinD + Serper）
fly ssh console -C "python -u _run_pipeline.py"
```

---

## 二、Railway（更简单，图形化）

### 前提
- 注册 https://railway.app （GitHub 登录，每月 $5 免费额度）

### 部署步骤

1. Railway 控制台 → **New Project → Deploy from GitHub repo**
2. 选择仓库 `RilyWang/EventSentry_Agent`
3. Railway 会自动识别根目录的 `railway.json`（已配置好 Dockerfile 路径）
4. 在 **Variables** 里添加：
   ```
   LLM_API_KEY=...
   LLM_BASE_URL=https://open.bigmodel.cn/api/anthropic
   LLM_MODEL=glm-4.6
   SERPER_API_KEY=...
   DB_PATH=/data/eventsentry.db
   ```
5. 在 **Settings → Volumes** 添加一个卷，挂载到 `/data`（持久化 SQLite）
6. 部署完成 → **Settings → Networking → Generate Domain**

**得到固定地址**：`https://eventsentry-production-xxxx.up.railway.app`

---

## 三、Render（备选）

> ⚠️ 本机实测 `render.com:443` **连接超时**，可能无法从当前网络部署成功。

1. 注册 https://render.com
2. New → **Web Service** → 连接 GitHub 仓库
3. 配置：
   - **Root Directory**: `server`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python -u main.py`
4. 添加环境变量（同 Railway）
5. ❗ Render 免费套餐**不支持持久磁盘**，SQLite 数据会在重启后重置
   → 需每次重新灌数据，或用外部数据库

---

## 四、部署后必做

```bash
# 1. 验证健康检查
curl https://<你的地址>/api/ping
# → {"ok":true,...}

# 2. 验证事件数据
curl https://<你的地址>/api/events?limit=1
# → {"items":[...],"total":N}

# 3. 浏览器打开，检查三 Tab 与参谋对话
```

**环境变量清单**（务必只放在平台 Secrets / Variables，**不要写进代码或仓库**）：

| 变量 | 必填 | 说明 |
|------|:---:|------|
| `LLM_API_KEY` | ✅ | 智谱 GLM Key（参谋 Agent 必需） |
| `SERPER_API_KEY` | ✅ | 媒体/传闻采集（不填则该数据源不可用） |
| `LLM_BASE_URL` | ⬜ | 默认 `https://open.bigmodel.cn/api/anthropic` |
| `LLM_MODEL` | ⬜ | 默认 `glm-4.6` |
| `DB_PATH` | ⬜ | 挂载卷内路径，如 `/data/eventsentry.db` |
| `PORT` | ⬜ | 平台自动注入，应用已支持 |
| `ENABLE_SCHEDULER` | ⬜ | 默认 `1`（定时采集+反思） |
| `SCHEDULER_RUN_ON_START` | ⬜ | 默认 `0`（避免启动即跑重任务） |

---

## 五、已为本项目准备好的部署文件

| 文件 | 用途 |
|------|------|
| `server/Dockerfile` | 通用 Docker 镜像（Python 3.12-slim，含健康检查） |
| `server/requirements.txt` | Python 依赖 |
| `server/Procfile` | Heroku 系平台启动命令 |
| `fly.toml` | Fly.io 配置（含持久卷挂载、自动挂起省额度） |
| `railway.json` | Railway 配置（Dockerfile 构建 + 健康检查） |

---

## 六、常见问题

| 现象 | 原因 | 解决 |
|------|------|------|
| 部署后事件为空 | 数据库在云端是空的 | 执行「首次部署后导入数据」 |
| 参谋对话报错 | 未配置 `LLM_API_KEY` | 在平台 Variables 里补上 |
| 媒体/传闻证据缺失 | 未配置 `SERPER_API_KEY` | 补上该变量 |
| 数据重启后丢失 | 未挂载持久卷 | 检查 `DB_PATH` 与卷挂载点是否一致 |
| 地址能开但很慢 | 区域离得远 | 把 region 改到 `hkg`（香港）/ `sin`（新加坡） |

---

*相关：临时隧道方案见 [`CLOUDFLARE_STABLE.md`](./CLOUDFLARE_STABLE.md)*
