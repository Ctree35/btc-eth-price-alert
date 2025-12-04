# 使用官方最小化镜像
FROM python:3.12-slim

# 少装一点包能节省空间
RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY btc_eth_bark_notifier.py .

# 创建数据目录用于持久化SQLite数据库
RUN mkdir -p /app/data

# 默认轮询 30 s；可在部署平台用环境变量覆盖
ENV INTERVAL=30 \
    BTC_STEP=1000 \
    ETH_STEP=100 \
    RATIO_STEP=0.5 \
    DB_PATH=/app/data/price_history.db

CMD ["python", "btc_eth_bark_notifier.py"]

