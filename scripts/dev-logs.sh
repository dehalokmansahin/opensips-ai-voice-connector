#!/bin/bash
# Development logging script for debugging

set -e

# Default to showing all services if no argument provided
SERVICE=${1:-""}

if [ -z "$SERVICE" ]; then
    echo "Showing logs for all services (development mode)"
    echo "================================================"
    docker-compose -f docker-compose.yml -f docker-compose.dev.yml logs -f --tail=100
else
    echo "Showing logs for service: $SERVICE"
    echo "=================================="
    docker-compose -f docker-compose.yml -f docker-compose.dev.yml logs -f --tail=100 "$SERVICE"
fi

echo ""
echo "Available services: opensips-ai-core, asr-service, llm-service, tts-service"
echo "Usage: $0 [service-name]"