# Docker Setup for OpenSIPS AI Voice Connector

This document describes how to run the OpenSIPS AI Voice Connector using Docker containers.

## Architecture

The application is split into microservices:

- **asr-service** (port 50051): Speech-to-Text using Vosk
- **llm-service** (port 50052): Language Model using LLaMA
- **tts-service** (port 50053): Text-to-Speech using Piper
- **opensips-ai-core** (port 8080): Main application coordinating all services

## Prerequisites

1. **Docker and Docker Compose** installed
2. **Model files** in the correct directories:
   ```
   models/
   ├── vosk/          # Vosk ASR model files
   ├── llm/           # LLaMA model files (.gguf)
   └── piper/         # Piper TTS model files (.onnx + .json)
   ```

## Model Setup

### ASR Models (Vosk)
Download a Vosk model for your language:
```bash
mkdir -p models/vosk
cd models/vosk
wget https://alphacephei.com/vosk/models/vosk-model-en-us-0.22.zip
unzip vosk-model-en-us-0.22.zip
mv vosk-model-en-us-0.22/* .
```

### LLM Models (LLaMA)
Place your LLaMA model file:
```bash
mkdir -p models/llm
# Copy your llama-model.gguf file to models/llm/
```

### TTS Models (Piper)
Download Piper models:
```bash
mkdir -p models/piper
cd models/piper
# Download Turkish voice model
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/tr/tr_TR/fahrettin/medium/tr_TR-fahrettin-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/tr/tr_TR/fahrettin/medium/tr_TR-fahrettin-medium.onnx.json
```

## Running the Services

### Production Mode
```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Check status
docker-compose ps

# Stop services
docker-compose down
```

### Development Mode
```bash
# Start with development overrides
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# This enables:
# - Volume mounting for live code changes
# - Debug logging
# - Development Dockerfiles
```

## Health Checks

All services include health checks:

```bash
# Check service health
docker-compose ps

# Manual health check
docker exec opensips-asr-service grpc-health-probe -addr=localhost:50051
docker exec opensips-llm-service grpc-health-probe -addr=localhost:50052
docker exec opensips-tts-service grpc-health-probe -addr=localhost:50053
curl http://localhost:8080/health
```

## Environment Configuration

### Service Ports
- ASR: `ASR_SERVICE_LISTEN_ADDR=[::]:50051`
- LLM: `LLM_SERVICE_LISTEN_ADDR=[::]:50052`  
- TTS: `TTS_SERVICE_LISTEN_ADDR=[::]:50053`

### Resource Limits
```bash
# Adjust worker counts based on your hardware
export ASR_MAX_WORKERS=10
export LLM_MAX_WORKERS=4
export TTS_MAX_WORKERS=10
```

### Model Paths
```bash
# ASR Configuration
export VOSK_MODEL_PATH=/app/model
export VOSK_SAMPLE_RATE=16000

# LLM Configuration  
export LLM_MODEL_PATH=/app/model/llama-model.gguf
export LLM_CONTEXT_SIZE=2048
export LLM_GPU_LAYERS=0

# TTS Configuration
export PIPER_MODEL_DIR=/app/model
export PIPER_MODEL_NAME=tr_TR-fahrettin-medium
```

## Troubleshooting

### Service Won't Start
```bash
# Check logs
docker-compose logs <service-name>

# Common issues:
# 1. Missing model files
# 2. Port conflicts
# 3. Insufficient memory
```

### Model Loading Issues
```bash
# Verify model files exist
docker exec opensips-asr-service ls -la /app/model
docker exec opensips-llm-service ls -la /app/model  
docker exec opensips-tts-service ls -la /app/model

# Check model permissions
docker exec opensips-asr-service file /app/model/*
```

### Performance Issues
```bash
# Monitor resource usage
docker stats

# Adjust worker counts
# Edit docker-compose.yml environment variables
```

### Network Issues
```bash
# Test inter-service communication
docker exec opensips-ai-core ping asr-service
docker exec opensips-ai-core ping llm-service
docker exec opensips-ai-core ping tts-service
```

## Development Workflow

1. **Make code changes** in the respective service directories
2. **For immediate testing** (dev mode):
   ```bash
   docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d
   ```
   
3. **For production testing**:
   ```bash
   docker-compose build <service-name>
   docker-compose up -d <service-name>
   ```

## Scaling Services

```bash
# Scale individual services
docker-compose up -d --scale asr-service=2 --scale tts-service=3

# Note: You'll need to implement load balancing for multiple instances
```

## Logs and Monitoring

```bash
# Follow all logs
docker-compose logs -f

# Follow specific service
docker-compose logs -f asr-service

# View last 100 lines
docker-compose logs --tail=100 llm-service
```