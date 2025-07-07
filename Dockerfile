FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies - Enhanced for dynamic config processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    tcpdump \
    bash \
    libopus-dev \
    libsndfile1 \
    gcc \
    g++ \
    python3-dev \
    dos2unix \
    netcat-openbsd \
    curl \
    iproute2 \
    net-tools \
    procps \
    iputils-ping \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy and install local Pipecat
COPY pipecat/ /app/pipecat/
RUN cd /app/pipecat && pip install -e .

# Copy source code and configuration - Enhanced with templates
COPY src/ /app/src/
COPY cfg/ /app/cfg/
COPY pipecat/ /app/pipecat/
COPY scripts/ /app/scripts/
COPY test_audio/ /app/test_audio/

# Create log directories
RUN mkdir -p /app/logs /app/logs/opensips /app/logs/event-monitor

# Make startup script executable
RUN chmod +x /app/scripts/startup.sh
RUN dos2unix /app/scripts/startup.sh

# Environment variables - Dynamic configuration support
ENV CONFIG_FILE=/app/cfg/opensips-ai-voice-connector.ini
ENV PYTHONPATH=/app

# Default service URLs (Docker service discovery)
ENV VOSK_SERVER_URL=ws://vosk-server:2700
ENV PIPER_TTS_URL=ws://piper-tts-server:8000/tts
ENV LLAMA_SERVER_URL=ws://llm-turkish-server:8765

# OpenSIPS Integration defaults
ENV OPENSIPS_HOST=opensips
ENV OPENSIPS_MI_PORT=8087
ENV OPENSIPS_EVENT_PORT=8090
ENV OAVC_SIP_PORT=8089

# Runtime configuration
ENV TEST_MODE=false
ENV LOG_LEVEL=INFO
ENV DEBUG_MODE=false
ENV WAIT_FOR_DEPS=true

# Expose ports - Updated for dynamic configuration
# OAVC SIP Interface
EXPOSE 8089/udp 8089/tcp
# RTP Media ports
EXPOSE 35000-35003/udp
EXPOSE 35010/udp 35011/udp

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import socket; s=socket.socket(); s.connect(('localhost', ${OAVC_SIP_PORT:-8089})); s.close()" || exit 1

# Entry point - Dynamic startup script
ENTRYPOINT ["/app/scripts/startup.sh"]
CMD ["oavc"] 
