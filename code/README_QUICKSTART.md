# 快速启动指南

## 环境要求

- Node.js >= 20
- MySQL >= 8.0（或使用 Docker）

## 第一步：安装依赖

```bash
cd code
npm install
```

## 第二步：配置环境变量

```bash
# 方法1：使用开发默认配置（快速体验）
cp .env.local .env

# 方法2：手动配置（生产环境）
cp .env.example .env
# 编辑 .env 填入真实值
```

## 第三步：启动 MySQL（如果没有）

### 方式A：Docker（推荐）
```bash
docker run -d \
  --name eventsentry-db \
  -e MYSQL_ROOT_PASSWORD=root \
  -e MYSQL_DATABASE=eventsentry \
  -p 3306:3306 \
  mysql:8.0
```

### 方式B：本地 MySQL
确保 MySQL 服务已启动，且已创建数据库 `eventsentry`。

## 第四步：数据库迁移 + 种子

```bash
# 生成迁移文件
npm run db:generate

# 执行迁移
npm run db:migrate

# 插入种子数据（6个Demo事件）
npm run db:seed
```

## 第五步：启动开发服务器

```bash
npm run dev
```

浏览器访问 `http://localhost:3000/`

## 第六步：登录

1. 访问 `http://localhost:3000/login`
2. 点击"使用 Kimi 账号登录"
3. 如果 Kimi OAuth 未配置，可以直接访问 `http://localhost:3000/` 使用游客模式

---

## 常见问题

### 1. 端口 3000 被占用
```bash
# Windows
netstat -ano | findstr :3000
taskkill /PID <PID> /F

# Mac/Linux
lsof -i :3000
kill -9 <PID>
```

### 2. 数据库连接失败
- 检查 MySQL 是否启动
- 检查 `.env` 中 `DATABASE_URL` 是否正确
- 默认：`mysql://root:root@localhost:3306/eventsentry`

### 3. node_modules 安装失败
```bash
# 清除缓存重试
rm -rf node_modules package-lock.json
npm cache clean --force
npm install
```

### 4. OAuth 登录跳转失败
- 在 Kimi 开放平台注册应用
- 配置回调地址：`http://localhost:3000/api/oauth/callback`
- 将 `APP_ID` 和 `APP_SECRET` 填入 `.env`

---

## 生产部署

```bash
npm run build
npm run start
```

详见 `../docs/09-deploy/DEPLOY.md`
