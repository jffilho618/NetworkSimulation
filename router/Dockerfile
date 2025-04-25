FROM python:3.9-slim

WORKDIR /app

RUN apt-get update && apt-get install -y iproute2 iputils-ping

COPY . .

CMD ["python", "router.py"]
# CMD ["python", "router.py", "--config", "config.json"]