FROM debian:bookworm-slim

# ── System dependencies + Chrome ───────────────────────────────────────

RUN apt-get update && apt-get install -y --no-install-recommends \
    wget gnupg ca-certificates curl unzip procps python3 python3-pip \
    && wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | \
       gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] \
       http://dl.google.com/linux/chrome/deb/ stable main" \
       > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update && apt-get install -y --no-install-recommends \
       google-chrome-stable \
       fonts-liberation fonts-roboto \
       libasound2 libatk-bridge2.0-0 libatk1.0-0 libcups2 libdbus-1-3 \
       libdrm2 libgbm1 libgtk-3-0 libnspr4 libnss3 libu2f-udev libvulkan1 \
       libxcomposite1 libxdamage1 libxfixes3 libxkbcommon0 libxrandr2 \
       xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# ── Install kimi-webbridge daemon ──────────────────────────────────────

RUN curl -fsSL https://cdn.kimi.com/webbridge/install.sh | bash -s -- --no-start --no-skill

# ── Download kimi-webbridge extension ──────────────────────────────────

RUN mkdir -p /home/chrome/extensions/kimi-webbridge \
    && curl -fsSL -o /tmp/ext.zip \
       "https://kimi-web-img.moonshot.cn/webbridge/latest/extension/kimi-webbridge-extension.zip" \
    && unzip -qo /tmp/ext.zip -d /home/chrome/extensions/kimi-webbridge \
    && rm /tmp/ext.zip \
    && echo "Extension files:" && ls /home/chrome/extensions/kimi-webbridge/

# ── Create non-root user ───────────────────────────────────────────────

RUN groupadd -r chrome && useradd -r -g chrome -G audio,video chrome \
    && mkdir -p /home/chrome/data /home/chrome/extensions \
    && mkdir -p /app \
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
