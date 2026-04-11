FROM python:3.12-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        tar \
        lbzip2 \
        bzip2 \
        gnupg \
        par2 \
        openssh-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x docker/entrypoint.py docker/healthcheck.sh

HEALTHCHECK --interval=60s --timeout=5s --start-period=300s --retries=1 \
    CMD ["/app/docker/healthcheck.sh"]

ENTRYPOINT ["python3", "/app/docker/entrypoint.py"]
