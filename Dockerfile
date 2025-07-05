FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies - Enhanced for dynamic config processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    tcpdump \
    libopus-dev \
    libsndfile1 \
    gcc \
    g++ \
    python3-dev \
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
COPY scripts/ /app/scripts/

# Create log directories
RUN mkdir -p /app/logs /app/logs/opensips /app/logs/event-monitor

# Make startup script executable
RUN chmod +x /app/scripts/startup.sh

# Environment variables - Unified configuration support
ENV PYTHONPATH=/app

# 🆕 UNIFIED CONFIG: Use OAVC_ prefix for all configuration
# Configuration file location
ENV OAVC_CONFIG_FILE=/app/cfg/opensips-ai-voice-connector.ini

# Service URLs (Docker service discovery) - OAVC_ prefix
ENV OAVC_STT__URL=ws://vosk-server:2700
ENV OAVC_LLM__URL=ws://llm-turkish-server:8765
ENV OAVC_TTS__URL=ws://piper-tts-server:8000/tts

# Service-specific settings
ENV OAVC_STT__MODEL=vosk-model-tr
ENV OAVC_LLM__MODEL=llama3.2:3b-instruct-turkish
ENV OAVC_LLM__TEMPERATURE=0.2
ENV OAVC_LLM__MAX_TOKENS=80
ENV OAVC_TTS__VOICE=tr_TR-dfki-medium

# Network configuration
ENV OAVC_NETWORK__BIND_IP=0.0.0.0
ENV OAVC_NETWORK__MIN_PORT=35000
ENV OAVC_NETWORK__MAX_PORT=35100

# Voice processing configuration  
ENV OAVC_VOICE__SAMPLE_RATE=16000
ENV OAVC_VOICE__VAD_CONFIDENCE=0.15
ENV OAVC_VOICE__ENABLE_INTERRUPTION=true

# Logging and debugging
ENV OAVC_DEBUG=false
ENV OAVC_LOG_LEVEL=INFO

# Legacy environment variables for backward compatibility
ENV OPENSIPS_HOST=opensips
ENV OPENSIPS_MI_PORT=8087
ENV OPENSIPS_EVENT_PORT=8090
ENV OAVC_SIP_PORT=8089

# Runtime configuration
ENV TEST_MODE=false
ENV WAIT_FOR_DEPS=true

# Expose ports - Updated for dynamic configuration
# OAVC SIP Interface
EXPOSE 8089/udp 8089/tcp
# RTP Media ports - Aligned with unified config
EXPOSE 35000-35100/udp

# Health check - Updated to use unified config
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import socket; s=socket.socket(); s.connect(('localhost', ${OAVC_SIP_PORT:-8089})); s.close()" || exit 1

# Entry point - Dynamic startup script
ENTRYPOINT ["/app/scripts/startup.sh"]
CMD ["oavc"] 
