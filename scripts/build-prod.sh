#!/bin/bash
# Production build script
# Builds optimized production images with multi-stage builds and security hardening

set -e

echo "Building production environment..."
echo "================================="

# Build production images with multi-stage optimization
echo "Building LLM service (production)..."
docker-compose -f docker-compose.yml -f docker-compose.prod.yml build --parallel llm-service

echo "Building ASR service (production)..."
docker-compose -f docker-compose.yml -f docker-compose.prod.yml build --parallel asr-service

echo "Building TTS service (production)..."
docker-compose -f docker-compose.yml -f docker-compose.prod.yml build --parallel tts-service

echo "Building Core application (production)..."
docker-compose -f docker-compose.yml -f docker-compose.prod.yml build --parallel opensips-ai-core

echo ""
echo "Production build complete!"
echo "To start: docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d"
echo "Features: Minimal images, security hardening, resource limits"

# Show image sizes for comparison
echo ""
echo "Image sizes:"
echo "============"
docker images | grep -E "(opensips|llm|asr|tts)" | grep -v "<none>" | sort