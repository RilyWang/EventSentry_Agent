# 部署文档

> EventSentry V2.0 部署指南

---

## 部署方式速查

| 方式 | 适用场景 | 复杂度 | 成本 |
|------|----------|--------|------|
| **Docker Compose** | 本地开发 / 私有服务器 | 低 | 低 |
| **Vercel + PlanetScale** | 快速上线 / 无服务器 | 中 | 免费额度内 |
| **GitHub Pages + 独立后端** | 前端静态 / 后端分离 | 中 | 低 |
| **阿里云 ECS + RDS** | 生产环境 / 国内访问 | 中 | 中 |

---

## 方式一：Docker Compose（推荐本地/测试）

### 前提条件

- Docker >= 24.0
- Docker Compose >= 2.0

### 部署步骤

```bash
# 1. 克隆仓库
git clone https://github.com/your-org/eventsentry.git
cd eventsentry

# 2. 创建环境变量文件
cp code/.env.example .env
# 编辑 .env，填入：
# APP_ID=your_kimi_app_id
# APP_SECRET=your_kimi_app_secret
# DATABASE_URL=mysql://eventsentry:eventsentry@db:3306/eventsentry
# KIMI_AUTH_URL=https://auth.kimi.com
# KIMI_OPEN_URL=https://open.kimi.com
# IFIND_API_KEY=your_ifind_key
# FUYAO_API_KEY=your_fuyao_key

# 3. 启动服务
docker-compose up -d

# 4. 执行数据库迁移
docker-compose exec api npx drizzle-kit migrate

# 5. 种子数据
docker-compose exec api npx tsx db/seed.ts

# 6. 验证
open http://localhost:3000
```

### 查看日志

```bash
docker-compose logs -f api       # 后端日志
docker-compose logs -f collector # 采集 Agent 日志
docker-compose logs -f analyst   # 分析 Agent 日志
```

### 停止服务

```bash
docker-compose down -v  # -v 会删除数据卷，谨慎使用
```

---

## 方式二：Vercel + PlanetScale（推荐快速上线）

### 前端部署（Vercel）

1. 在 [Vercel](https://vercel.com) 导入 GitHub 仓库
2. 设置 Root Directory 为 `code`
3. 设置 Build Command：`npm run build:web`
4. 设置 Output Directory：`dist/public`
5. 添加环境变量：
   - `VITE_KIMI_AUTH_URL`
   - `VITE_APP_ID`

### 后端部署（Vercel Serverless）

1. 在 Vercel 项目设置中，添加 Serverless Function
2. `api/index.ts` 即为入口（Hono handler）
3. 添加环境变量：
   - `DATABASE_URL`（PlanetScale 连接串）
   - `APP_ID`, `APP_SECRET`
   - `KIMI_AUTH_URL`, `KIMI_OPEN_URL`

### 数据库（PlanetScale）

1. 在 [PlanetScale](https://planetscale.com) 创建数据库
2. 执行迁移：`npx drizzle-kit migrate`
3. 执行种子：`npx tsx db/seed.ts`

---

## 方式三：GitHub Pages + 独立后端

### 前端（GitHub Pages）

工作流已配置在 `.github/workflows/deploy.yml`：

```bash
# 每次 push 到 main 分支，GitHub Actions 会自动：
# 1. 构建前端 dist/public
# 2. 部署到 gh-pages 分支
# 3. 通过 GitHub Pages 访问
```

**配置 GitHub Pages：**
1. 仓库 Settings → Pages → Source → GitHub Actions
2. 或 Source → Deploy from a branch → gh-pages

### 后端（独立服务器）

```bash
# 1. 服务器安装 Node.js 20
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs

# 2. 克隆并构建
git clone https://github.com/your-org/eventsentry.git
cd eventsentry/code
npm ci
npm run build:api

# 3. 配置 systemd 服务
sudo cp deploy/eventsentry.service /etc/systemd/system/
sudo systemctl enable eventsentry
sudo systemctl start eventsentry
```

---

## 环境变量清单

| 变量 | 必填 | 说明 |
|------|------|------|
| `DATABASE_URL` | ✅ | MySQL 连接串 |
| `APP_ID` | ✅ | Kimi OAuth App ID |
| `APP_SECRET` | ✅ | Kimi OAuth App Secret |
| `KIMI_AUTH_URL` | ✅ | Kimi 认证服务器 |
| `KIMI_OPEN_URL` | ✅ | Kimi Open Platform |
| `OWNER_UNION_ID` | ❌ | 管理员 Union ID |
| `IFIND_API_KEY` | ❌ | iFinD API Key（无则跳过采集） |
| `IFIND_BASE_URL` | ❌ | iFinD 自定义地址 |
| `FUYAO_API_KEY` | ❌ | 扶摇 API Key |
| `FUYAO_BASE_URL` | ❌ | 扶摇自定义地址 |
| `VITE_KIMI_AUTH_URL` | ✅（前端） | 前端暴露的 Kimi 认证地址 |
| `VITE_APP_ID` | ✅（前端） | 前端暴露的 App ID |

---

## 健康检查

```bash
# API 健康检查
curl http://localhost:3000/api/trpc/ping
# → {"ok":true,"ts":1234567890}

# 数据库连接检查
curl http://localhost:3000/api/trpc/event.list
# → 返回事件列表
```

---

## 故障排查

| 症状 | 可能原因 | 解决方案 |
|------|----------|----------|
| `db:push` 失败 | DATABASE_URL 格式错误 | 检查连接串格式 `mysql://user:pass@host:port/db` |
| 前端 404 | Vite base 路径未配置 | 设置 `base: '/repo-name/'` |
| OAuth 登录失败 | 回调地址不匹配 | 确保 Kimi 后台配置的 redirect_uri 一致 |
| iFinD 采集失败 | Python 环境缺失 | `pip install iFinDApi mysql-connector-python` |
| 时区不一致 | Docker 容器时区 | `docker-compose exec api date` 检查时区 |

---

## 生产检查清单

- [ ] 数据库已迁移并种子化
- [ ] 环境变量已正确配置
- [ ] Kimi OAuth 回调地址已配置
- [ ] iFinD / 扶摇 API Key 已配置（或确认使用 Mock 模式）
- [ ] HTTPS 已启用（OAuth 要求）
- [ ] 数据库已设置定期备份
- [ ] 日志已配置轮转（logrotate）
- [ ] 防火墙已开放必要端口（3000, 3306）
- [ ] Agent 定时任务已启动（cron/systemd）

---

*版本：V2.0 | 更新日期：2026-10-09*
