# EventSentry —— 供 Railway / Render 等「以仓库根为构建上下文」的平台使用
# 应用代码在 server/ 子目录，故此处从 server/ 复制。
FROM python:3.12-slim

ENV TZ=Asia/Shanghai \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=3000

WORKDIR /app

# 依赖层（利用 Docker 缓存）
COPY server/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 应用代码
COPY server/ ./

RUN mkdir -p /app/db_data

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,os;urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','3000')+'/api/ping')" || exit 1

CMD ["python", "-u", "main.py"]
