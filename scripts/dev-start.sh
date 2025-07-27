#!/bin/bash
# Fast development startup script
# Optimized for hot-reload performance with 30-second target

set -e

echo "Starting OpenSIPS AI Voice Connector - Development Mode"
echo "========================================================="

# Environment setup
export DEVELOPMENT_MODE=1
export CORE_LOG_LEVEL=DEBUG
export PYTHONUNBUFFERED=1
export PYTHONDONTWRITEBYTECODE=1

# Optimized Docker Compose startup with parallel builds
echo "Building and starting services (parallel mode)..."

# Use build cache and parallel processing for faster startup
docker-compose -f docker-compose.yml -f docker-compose.dev.yml build --parallel

# Start services with optimized dependency management
echo "Starting services..."
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up --remove-orphans

echo ""
echo "Development environment started!"
echo "Hot-reload enabled - code changes will trigger restart within 30 seconds"
echo ""
echo "Available services:"
echo "- Core Application: http://localhost:8080"
echo "- ASR Service: localhost:50051"
echo "- LLM Service: localhost:50052"
echo "- TTS Service: localhost:50053"
echo ""
echo "To stop: Ctrl+C or docker-compose -f docker-compose.yml -f docker-compose.dev.yml down"