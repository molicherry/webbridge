FROM debian:bookworm-slim

# ── System dependencies + Chrome ───────────────────────────────────────

RUN apt-get update && apt-get install -y --no-install-recommends \
    wget gnupg ca-certificates curl unzip procps python3 python3-pip xvfb chromium chromium-sandbox \
    fonts-liberation fonts-roboto \
    libasound2 libatk-bridge2.0-0 libatk1.0-0 libcups2 libdbus-1-3 \
    libdrm2 libgbm1 libgtk-3-0 libnspr4 libnss3 libu2f-udev libvulkan1 \
    libxcomposite1 libxdamage1 libxfixes3 libxkbcommon0 libxrandr2 \
     xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# ── Install kimi-webbridge daemon ──────────────────────────────────────

RUN for i in 1 2 3; do \
        curl -fsSL --retry 3 --retry-delay 5 --max-time 120 https://cdn.kimi.com/webbridge/install.sh | bash -s -- --no-start --no-skill && break; \
        echo "Attempt $i failed, retrying in 10s..." && sleep 10; \
    done

# ── Download kimi-webbridge extension ──────────────────────────────────

RUN mkdir -p /home/chrome/extensions/kimi-webbridge \
    && for i in 1 2 3; do \
         curl -fsSL --retry 3 --retry-delay 5 --max-time 60 -o /tmp/ext.zip \
           "https://kimi-web-img.moonshot.cn/webbridge/latest/extension/kimi-webbridge-extension.zip" && break; \
         echo "Attempt $i failed, retrying in 10s..." && sleep 10; \
       done \
    && unzip -qo /tmp/ext.zip -d /home/chrome/extensions/kimi-webbridge \
    && rm /tmp/ext.zip \
    && echo "Extension files:" && ls /home/chrome/extensions/kimi-webbridge/

# ── Create non-root user ───────────────────────────────────────────────

RUN groupadd -r chrome && useradd -r -g chrome -G audio,video chrome \
    && mkdir -p /home/chrome/data /home/chrome/extensions \
    && mkdir -p /app \
    && mv /root/.kimi-webbridge /home/chrome/.kimi-webbridge \
    && chown -R chrome:chrome /home/chrome /app

# ── Install Python dependencies ────────────────────────────────────────

COPY requirements.txt /app/
RUN pip3 install --break-system-packages --no-cache-dir -r /app/requirements.txt

# ── Copy application ───────────────────────────────────────────────────

COPY src/ /app/src/
COPY entrypoint.sh /app/
RUN chmod +x /app/entrypoint.sh

# ── Container config ───────────────────────────────────────────────────

USER chrome
WORKDIR /app

ENV CHROME_USER_DATA=/home/chrome/data \
    CHROME_EXTENSION=/home/chrome/extensions/kimi-webbridge \
    CDP_PORT=9222 \
    DAEMON_PORT=10086 \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8000 \
    PYTHONPATH=/app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -sf http://127.0.0.1:8000/health || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
