FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    g++ \
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install grpc-health-probe for health checks
RUN wget -qO/bin/grpc-health-probe https://github.com/grpc-ecosystem/grpc-health-probe/releases/download/v0.4.19/grpc-health-probe-linux-amd64 && \
    chmod +x /bin/grpc-health-probe

# Create app directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy common services
COPY ../common /app/common

# Copy source code
COPY src/ /app/src/
COPY proto/ /app/proto/

# Create model directory
RUN mkdir -p /app/model

# Set Python path
ENV PYTHONPATH=/app:/app/src:/app/common

# Expose gRPC port
EXPOSE 50051

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD grpc-health-probe -addr=localhost:50051 -service=ASRService

# Run the service
CMD ["python", "/app/src/enhanced_asr_server.py"]