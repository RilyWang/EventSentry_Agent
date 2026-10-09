# ─── Stage 1: Build ───
FROM node:20-alpine AS builder

WORKDIR /app

# 安装依赖
COPY package*.json ./
RUN npm ci

# 复制源代码
COPY . .

# 构建前端 + 后端
RUN npm run build

# ─── Stage 2: Production ───
FROM node:20-alpine AS runner

WORKDIR /app

# 只复制生产需要的文件
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/package*.json ./
COPY --from=builder /app/db ./db
COPY --from=builder /app/scripts ./scripts
COPY --from=builder /app/task-runner ./task-runner

# 安装生产依赖
RUN npm ci --production

# 安装 Python（用于 iFinD 采集脚本）
RUN apk add --no-cache python3 py3-pip

# 暴露端口
EXPOSE 3000

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD wget --quiet --tries=1 --spider http://localhost:3000/api/trpc/ping || exit 1

# 启动命令
CMD ["node", "dist/boot.js"]
