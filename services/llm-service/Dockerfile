FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    g++ \
    cmake \
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

# Create model and cache directories
RUN mkdir -p /app/model /app/rag_model

# Set environment variables for offline mode
ENV TRANSFORMERS_OFFLINE=1
ENV HF_HUB_OFFLINE=1
ENV HF_HUB_DISABLE_TELEMETRY=1
ENV SENTENCE_TRANSFORMERS_HOME=/app/rag_model
ENV HF_HOME=/app/rag_model
ENV TORCH_HOME=/app/rag_model

# Set Python path
ENV PYTHONPATH=/app:/app/src:/app/common

# Expose gRPC port
EXPOSE 50052

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD grpc-health-probe -addr=localhost:50052 -service=LLMService

# Run the service
CMD ["python", "/app/src/enhanced_llm_server.py"]