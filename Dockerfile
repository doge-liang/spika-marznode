# spika-marznode: xray + sing-box marznode image, sqlite-backed by default.
# Both core binaries ship in the image. xray is enabled by default;
# sing-box is opt-in per node (set SING_BOX_ENABLED=True) so an image bump
# never disturbs an xray-only deployment. Hysteria2 standalone is still not
# compiled in. This image is what voyra nodes pull from GHCR.

# --- sing-box builder -------------------------------------------------------
# We compile sing-box from source instead of using a release tarball because:
#  - the official `-musl` (alpine-compatible) build does NOT include
#    `with_v2ray_api`, and marznode injects an experimental.v2ray_api block
#    for per-user traffic stats (billing) -> sing-box fatals without it;
#  - the glibc release has it but won't run on the alpine runtime stage;
#  - sing-box 1.13 dropped v2ray_api from its default tag set entirely,
#    so even building the defaults is insufficient.
# So: explicit `with_v2ray_api` + the official 1.13 default tag set. The
# `badlinkname,tfogo_checklinkname0` tags are mandatory to compile under
# Go 1.24 (go.mod requires 1.24.7). CGO off -> static musl binary.
FROM golang:1.24-alpine AS sb-build
ARG SING_BOX_VERSION=v1.13.12
ENV CGO_ENABLED=0
RUN apk add --no-cache git \
    && SB_VER="${SING_BOX_VERSION#v}" \
    && go install -v -trimpath \
        -ldflags "-s -w -X github.com/sagernet/sing-box/constant.Version=${SB_VER}" \
        -tags "with_gvisor,with_quic,with_dhcp,with_wireguard,with_utls,with_acme,with_clash_api,with_tailscale,with_ccm,with_ocm,with_v2ray_api,badlinkname,tfogo_checklinkname0" \
        github.com/sagernet/sing-box/cmd/sing-box@${SING_BOX_VERSION} \
    && /go/bin/sing-box version

# --- runtime ----------------------------------------------------------------
FROM python:3.12-alpine

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MARZNODE_STORAGE_TYPE=sqlite \
    MARZNODE_DB_PATH=/var/lib/marznode/marznode.db \
    XRAY_EXECUTABLE_PATH=/usr/local/bin/xray \
    XRAY_ASSETS_PATH=/usr/local/lib/xray \
    SING_BOX_EXECUTABLE_PATH=/usr/local/bin/sing-box \
    SING_BOX_CONFIG_PATH=/var/lib/marznode/sing-box_config.json

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

# sing-box: statically-built (musl, CGO off) in the sb-build stage above,
# with with_v2ray_api so marznode's per-user stats work.
COPY --from=sb-build /go/bin/sing-box /usr/local/bin/sing-box
RUN chmod +x /usr/local/bin/sing-box && sing-box version

COPY requirements.txt .
RUN apk add --no-cache alpine-sdk libffi-dev \
    && pip install -r requirements.txt \
    && apk del -r alpine-sdk libffi-dev

COPY . .

RUN mkdir -p /var/lib/marznode

CMD ["python3", "marznode.py"]
