FROM python:3.11-slim
RUN apt-get update && apt-get install -y \
    net-tools \
    iproute2 \
    iputils-ping
COPY . /app
WORKDIR /app
CMD ["python", "main.py"]
