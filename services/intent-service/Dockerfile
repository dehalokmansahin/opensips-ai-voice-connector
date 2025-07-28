# Turkish BERT Intent Recognition Service - Real AI Model Dockerfile
# Turkish BERT model for IVR response classification

FROM python:3.10-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV FLASK_ENV=production
ENV FLASK_PORT=5000
ENV FLASK_HOST=0.0.0.0
ENV CONFIDENCE_THRESHOLD=0.7
ENV MODEL_CACHE_DIR=/app/models/cache

# Install system dependencies for ML packages
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create directories for models, logs and data
RUN mkdir -p /app/models/cache /app/logs /app/data

# Copy training data
COPY data/ ./data/

# Copy service source code
COPY src/ ./src/

# Set proper permissions
RUN chmod +x ./src/main.py

# Pre-download Turkish BERT model (optional - reduces startup time)
# RUN python -c "from transformers import AutoTokenizer, AutoModelForSequenceClassification; \
#     AutoTokenizer.from_pretrained('dbmdz/bert-base-turkish-uncased', cache_dir='/app/models/cache'); \
#     AutoModelForSequenceClassification.from_pretrained('dbmdz/bert-base-turkish-uncased', cache_dir='/app/models/cache')"

# Health check with longer startup period for model loading
HEALTHCHECK --interval=30s --timeout=15s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# Expose service port
EXPOSE 5000

# Start the service
CMD ["python", "src/main.py"]