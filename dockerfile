FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 持久化数据卷
VOLUME ["/app/data", "/app/logs"]

# 网页端口3000，MLLP采集2575
EXPOSE 3000 2575

CMD ["python", "start.py"]