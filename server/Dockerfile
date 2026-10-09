# EventSentry —— Python FastAPI + SQLite
FROM python:3.12-slim

# 时区设为东八区（事件时间戳用）
ENV TZ=Asia/Shanghai \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=3000

WORKDIR /app

# 依赖层（利用缓存）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 应用代码
COPY . .

# 数据目录（如挂载持久卷，把 DB_PATH 指向卷内）
RUN mkdir -p /app/db_data

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,os;urllib.request.urlopen(f'http://127.0.0.1:{os.getenv(\"PORT\",\"3000\")}/api/ping')" || exit 1

CMD ["python", "-u", "main.py"]
