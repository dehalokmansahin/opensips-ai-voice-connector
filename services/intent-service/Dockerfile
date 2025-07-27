# Intent Recognition Service - CPU Optimized Dockerfile
# Foundation for Turkish BERT intent classification

FROM python:3.10-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV INTENT_SERVICE_PORT=50054
ENV INTENT_MODEL_PATH=/app/models
ENV CUDA_VISIBLE_DEVICES=""

# Install system dependencies for CPU-optimized ML
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create directories for models and data
RUN mkdir -p /app/models /app/data /app/logs

# Copy service source code
COPY src/ ./src/
COPY proto/ ./proto/

# Generate gRPC code if needed
RUN python -m grpc_tools.protoc \
    --python_out=./src \
    --grpc_python_out=./src \
    --proto_path=./proto \
    intent_service.proto

# Set proper permissions
RUN chmod +x ./src/main.py

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import grpc; import sys; sys.path.append('./src'); import intent_service_pb2_grpc; import intent_service_pb2; channel = grpc.insecure_channel('localhost:50054'); stub = intent_service_pb2_grpc.IntentRecognitionStub(channel); stub.HealthCheck(intent_service_pb2.google_dot_protobuf_dot_empty__pb2.Empty(), timeout=5); print('OK')" || exit 1

# Expose service port
EXPOSE 50054

# Start the service
CMD ["python", "-m", "src.main"]