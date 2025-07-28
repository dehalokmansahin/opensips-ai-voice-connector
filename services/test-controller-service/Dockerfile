FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY services/test-controller-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service source code
COPY services/test-controller-service/src/ ./src/
COPY services/test-controller-service/proto/ ./proto/

# Copy core modules (shared with other services) from build context root
COPY core/ ./core/

# Set Python path to include both app and core
ENV PYTHONPATH="/app:/app/src:/app/core"

# Install curl for healthcheck
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Expose service port
EXPOSE 50055

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:50055/health || exit 1

# Run the service
CMD ["python", "src/main.py"]