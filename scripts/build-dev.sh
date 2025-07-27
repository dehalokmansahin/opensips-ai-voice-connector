#!/bin/bash
# Development build script
# Builds optimized development images with hot-reload support

set -e

echo "Building development environment..."
echo "=================================="

# Build development images with caching
echo "Building LLM service (development)..."
docker-compose -f docker-compose.yml -f docker-compose.dev.yml build --parallel llm-service

echo "Building ASR service (development)..."
docker-compose -f docker-compose.yml -f docker-compose.dev.yml build --parallel asr-service

echo "Building TTS service (development)..."
docker-compose -f docker-compose.yml -f docker-compose.dev.yml build --parallel tts-service

echo "Building Core application (development)..."
docker-compose -f docker-compose.yml -f docker-compose.dev.yml build --parallel opensips-ai-core

echo ""
echo "Development build complete!"
echo "To start: docker-compose -f docker-compose.yml -f docker-compose.dev.yml up"
echo "Features: Hot-reload, debug logging, faster startup"