FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies including OPUS codec support and libsndfile for soundfile library
RUN apt-get update && apt-get install -y --no-install-recommends \
    tcpdump \
    libopus-dev \
    libsndfile1 \
    gcc \
    g++ \
    python3-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and configuration
COPY src/ /app/src/
COPY cfg/ /app/cfg/


# Environment variables (can be overridden at runtime)
ENV CONFIG_FILE=/app/cfg/opensips-ai-voice-connector.ini
ENV PYTHONPATH=/app
# Set default Vosk WebSocket URL - can be overridden when running the container
# Use the container name when containers are on the same Docker network
ENV VOSK_WS_URL=ws://vosk-server:2700
# Use a different SIP port to avoid conflict with OpenSIPS
ENV SIP_PORT=8088

# Expose ports for SIP and RTP
EXPOSE 8088/udp
EXPOSE 35000-35100/udp

# Run the application
CMD ["python", "src/main.py"] 
