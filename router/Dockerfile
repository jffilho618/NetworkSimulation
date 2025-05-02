FROM python:3.9-slim

RUN apt-get update && apt-get install -y \
    iproute2 \
    iputils-ping \
    net-tools \
    && rm -rf /var/lib/apt/lists/*

RUN pip install netifaces

WORKDIR /app

COPY router/router.py formater.py dycastra.py /app/

CMD ["python", "router.py"]