#!/bin/bash
# EventSentry 一键安装脚本
# 适用于 Ubuntu 20.04+ / Debian 11+

set -e

REPO_URL="https://github.com/your-org/eventsentry.git"
INSTALL_DIR="/opt/eventsentry"
SERVICE_NAME="eventsentry"

echo "=== EventSentry V2.0 安装脚本 ==="

# 1. 检查 root
if [ "$EUID" -ne 0 ]; then
  echo "请使用 sudo 运行"
  exit 1
fi

# 2. 安装依赖
echo "[1/8] 安装系统依赖..."
apt-get update
apt-get install -y curl git mysql-server nginx python3 python3-pip

# 3. 安装 Node.js 20
echo "[2/8] 安装 Node.js 20..."
if ! command -v node &> /dev/null || [ "$(node -v | cut -d'v' -f2 | cut -d'.' -f1)" != "20" ]; then
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  apt-get install -y nodejs
fi

# 4. 克隆仓库
echo "[3/8] 克隆仓库..."
if [ -d "$INSTALL_DIR" ]; then
  echo "目录已存在，执行更新..."
  cd "$INSTALL_DIR" && git pull
else
  git clone "$REPO_URL" "$INSTALL_DIR"
fi

cd "$INSTALL_DIR/code"

# 5. 安装 Node 依赖
echo "[4/8] 安装 Node 依赖..."
npm ci

# 6. 构建
echo "[5/8] 构建..."
npm run build

# 7. 配置环境变量
echo "[6/8] 配置环境变量..."
if [ ! -f "$INSTALL_DIR/.env" ]; then
  echo "请编辑 $INSTALL_DIR/.env 填入配置"
  cp "$INSTALL_DIR/code/.env.example" "$INSTALL_DIR/.env"
fi

# 8. 配置 systemd
echo "[7/8] 配置 systemd 服务..."
cp "$INSTALL_DIR/code/deploy/eventsentry.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable eventsentry

# 9. 启动
echo "[8/8] 启动服务..."
systemctl start eventsentry

echo ""
echo "=== 安装完成 ==="
echo "服务状态: systemctl status eventsentry"
echo "查看日志: journalctl -u eventsentry -f"
echo "API 地址: http://localhost:3000"
