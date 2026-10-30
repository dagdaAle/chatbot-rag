# Base pinned to the reviewed upstream release; override only after compatibility tests.
ARG OPENWEBUI_IMAGE=ghcr.io/open-webui/open-webui:v0.12.5@sha256:03443b8de6b617da9d900edd09b4bf1cb0ddbfdcba6afb42c548336a0b821ded
FROM ${OPENWEBUI_IMAGE}
USER root
COPY deploy/openwebui/brand.py /tmp/intecha-brand.py
COPY deploy/openwebui/NOTICE.md /app/INTECHA-NOTICE.md
COPY deploy/openwebui/UPSTREAM_LICENSE /app/OPEN-WEBUI-LICENSE
ARG INTECHA_REBRANDING_CONFIRMED
RUN INTECHA_REBRANDING_CONFIRMED=${INTECHA_REBRANDING_CONFIRMED} python /tmp/intecha-brand.py && rm /tmp/intecha-brand.py
ENV WEBUI_NAME=Intecha
# Upstream start.sh, CMD and HEALTHCHECK retained.
