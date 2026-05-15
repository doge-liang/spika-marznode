# spika-marznode: xray-only marznode image, sqlite-backed by default.
# Hysteria2 / sing-box are *not* compiled in — add them back via a sidecar
# if needed. This image is what voyra nodes pull from GHCR.

FROM python:3.12-alpine

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MARZNODE_STORAGE_TYPE=sqlite \
    MARZNODE_DB_PATH=/var/lib/marznode/marznode.db \
    XRAY_EXECUTABLE_PATH=/usr/local/bin/xray \
    XRAY_ASSETS_PATH=/usr/local/lib/xray

WORKDIR /app

RUN apk add --no-cache curl unzip ca-certificates

ARG XRAY_VERSION=v25.1.30
RUN curl -fL -o /tmp/xray.zip \
        "https://github.com/XTLS/Xray-core/releases/download/${XRAY_VERSION}/Xray-linux-64.zip" \
    && unzip /tmp/xray.zip -d /usr/local/bin xray \
    && chmod +x /usr/local/bin/xray \
    && rm /tmp/xray.zip \
    && mkdir -p /usr/local/lib/xray \
    && curl -fL -o /usr/local/lib/xray/geosite.dat \
        "https://github.com/v2fly/domain-list-community/releases/latest/download/dlc.dat" \
    && curl -fL -o /usr/local/lib/xray/geoip.dat \
        "https://github.com/v2fly/geoip/releases/latest/download/geoip.dat" \
    && xray version | head -2

COPY requirements.txt .
RUN apk add --no-cache alpine-sdk libffi-dev \
    && pip install -r requirements.txt \
    && apk del -r alpine-sdk libffi-dev

COPY . .

RUN mkdir -p /var/lib/marznode

CMD ["python3", "marznode.py"]
