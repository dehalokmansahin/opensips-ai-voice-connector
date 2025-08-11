# syntax=docker/dockerfile:1.6
FROM python:3.13-slim

# Set working directory
WORKDIR /app

# Install system dependencies - minimal set
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    bash \
    libopus-dev \
    libsndfile1 \
    gcc \
    g++ \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /var/cache/apt/archives/*

# Copy cleaned requirements (without pipecat-ai since we'll use local)
COPY opensips-ai-voice-connector/requirements.txt .

# Install Python dependencies and clean up
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# Copy voice-ai-core source (our custom voice processing framework)
COPY voice_ai_core/ /app/voice_ai_core/

# Copy only essential application files
COPY opensips-ai-voice-connector/src/ /app/src/
COPY opensips-ai-voice-connector/cfg/ /app/cfg/

# Create minimal startup script
RUN echo '#!/bin/bash\ncd /app\npython src/main.py' > /app/startup.sh \
    && chmod +x /app/startup.sh

# Environment variables
ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    CONFIG_FILE=/app/cfg/opensips-ai-voice-connector.ini \
    VOSK_SERVER_URL=ws://vosk-server:2700 \
    PIPER_TTS_URL=ws://piper-tts-server:8000 \
    LLAMA_SERVER_URL=ws://llm-turkish-server:8765 \
    OPENSIPS_HOST=opensips \
    OPENSIPS_MI_PORT=8087 \
    OPENSIPS_EVENT_PORT=8090 \
    OAVC_SIP_PORT=8089 \
    LOG_LEVEL=INFO

# Expose only necessary ports
EXPOSE 8089/tcp 8089/udp

# Health check via socket connection test
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import socket; s=socket.socket(); s.connect(('localhost', 8089)); s.close()" || exit 1

# Use exec form for better signal handling
ENTRYPOINT ["./startup.sh"]