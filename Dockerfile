FROM python:3.13-slim-bookworm@sha256:480c75f114c46f661eea2f337ef40672160f9989f7de0c385aa719e51c6e44da

LABEL org.opencontainers.image.title="Home Control" \
      org.opencontainers.image.description="Smart-home control plane with web UI, MCP, and device kill switches" \
      org.opencontainers.image.source="https://github.com/joshsgoldstein/tv-remote-mcp" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TV_REMOTE_CONFIG=/data/config.json \
    TV_REMOTE_STATE=/data/state \
    HOME=/home/homecontrol

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir --no-deps . \
    && groupadd --gid 10001 homecontrol \
    && useradd --uid 10001 --gid 10001 --create-home homecontrol \
    && mkdir -p /data \
    && chown 10001:10001 /data /home/homecontrol

USER 10001:10001
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/', timeout=3).close()"]
ENTRYPOINT ["home-control-web"]
CMD ["--host", "0.0.0.0", "--allow-host", "localhost", "--allow-host", "127.0.0.1"]
