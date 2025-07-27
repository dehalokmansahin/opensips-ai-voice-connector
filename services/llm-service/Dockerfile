# Production Dockerfile for LLM Service
# Multi-stage build optimized for minimal size and fast startup

# Stage 1: Build dependencies and compile wheels
FROM python:3.10-slim as build-stage

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    g++ \
    cmake \
    wget \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create wheelhouse directory
WORKDIR /wheels

# Copy requirements files
COPY requirements.txt requirements_simple.txt ./

# Build wheels for CPU-only PyTorch and dependencies
# This significantly reduces final image size by using CPU-only builds
RUN pip wheel --wheel-dir /wheels \
    --find-links https://download.pytorch.org/whl/cpu/torch_stable.html \
    torch==2.1.0+cpu \
    sentence-transformers>=2.2.0 \
    chromadb>=0.4.0 \
    llama-cpp-python>=0.2.0 \
    grpcio>=1.60.0 \
    grpcio-tools>=1.60.0 \
    structlog>=23.0.0

# Stage 2: Production runtime (minimal)
FROM python:3.10-slim as production

# Install only essential runtime dependencies
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Install grpc-health-probe for health checks
RUN wget -qO/bin/grpc-health-probe https://github.com/grpc-ecosystem/grpc-health-probe/releases/download/v0.4.19/grpc-health-probe-linux-amd64 && \
    chmod +x /bin/grpc-health-probe

# Create app directory and user for security
WORKDIR /app
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Copy pre-built wheels and install packages
COPY --from=build-stage /wheels /wheels
RUN pip install --no-index --find-links /wheels \
    torch==2.1.0+cpu \
    sentence-transformers>=2.2.0 \
    chromadb>=0.4.0 \
    llama-cpp-python>=0.2.0 \
    grpcio>=1.60.0 \
    grpcio-tools>=1.60.0 \
    structlog>=23.0.0 \
    && rm -rf /wheels /root/.cache/pip

# Copy source code and proto files
COPY proto/ /app/proto/
COPY src/ /app/src/

# Create model and cache directories with proper permissions
RUN mkdir -p /app/model /app/rag_model && \
    chown -R appuser:appuser /app

# Set environment variables for offline mode and production
ENV TRANSFORMERS_OFFLINE=1
ENV HF_HUB_OFFLINE=1
ENV HF_HUB_DISABLE_TELEMETRY=1
ENV SENTENCE_TRANSFORMERS_HOME=/app/rag_model
ENV HF_HOME=/app/rag_model
ENV TORCH_HOME=/app/rag_model
ENV PYTHONPATH=/app:/app/src
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Production optimizations
ENV OMP_NUM_THREADS=1
ENV MKL_NUM_THREADS=1
ENV NUMEXPR_NUM_THREADS=1

# Switch to non-root user for security
USER appuser

# Expose gRPC port
EXPOSE 50052

# Health check for production
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD grpc-health-probe -addr=localhost:50052 -service=LLMService || exit 1

# Run the service (production gRPC server)
CMD ["python", "/app/src/llm_grpc_server.py"]