# ── Stage 1: builder — compile Python extensions and Node deps ────────────────
FROM debian:13.4 AS builder

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential gcc g++ python3 python3-pip python3-dev \
        libffi-dev nodejs npm ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /opt/hermes
COPY . .

# Compile Python packages — gateway-relevant extras only
# Drops from [all]: modal (cloud exec), daytona (cloud dev env),
#   dev (pytest/hypothesis), cli (interactive menu), voice (mic input)
RUN pip install --no-cache-dir \
    ".[messaging,cron,slack,pty,honcho,mcp,homeassistant,sms,acp,tts-premium,dingtalk,feishu,keychain,monitoring,scale]" \
    --break-system-packages

# Install Node deps — production only (omit devDependencies)
RUN npm install --prefer-offline --no-audit --omit=dev && \
    cd scripts/whatsapp-bridge && \
    npm install --prefer-offline --no-audit --omit=dev && \
    npm cache clean --force


# ── Stage 2: runtime — no compiler toolchain ─────────────────────────────────
FROM debian:13.4 AS runtime

# Runtime-only system packages — no build-essential, gcc, or dev headers
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        python3 nodejs npm ripgrep ffmpeg ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Copy compiled Python packages and CLI entry points from builder
COPY --from=builder /usr/local/lib /usr/local/lib
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy source code and Node deps
COPY --from=builder /opt/hermes /opt/hermes

# Install Playwright Chromium + its system deps (apt-only, no build tools needed)
RUN npx playwright install --with-deps chromium --only-shell && \
    npm cache clean --force

WORKDIR /opt/hermes
RUN chmod +x /opt/hermes/docker/entrypoint.sh

ENV HERMES_HOME=/opt/data
VOLUME ["/opt/data"]
ENTRYPOINT ["/opt/hermes/docker/entrypoint.sh"]
