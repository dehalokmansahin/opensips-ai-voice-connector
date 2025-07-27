#!/bin/bash
# Development debugging helper script

set -e

SERVICE=${1:-"opensips-ai-core"}
COMMAND=${2:-"bash"}

echo "OpenSIPS AI Voice Connector - Development Debugging"
echo "===================================================="
echo "Service: $SERVICE"
echo "Command: $COMMAND"
echo ""

# Check if service is running
if ! docker-compose -f docker-compose.yml -f docker-compose.dev.yml ps "$SERVICE" | grep -q "Up"; then
    echo "❌ Service '$SERVICE' is not running"
    echo ""
    echo "Available services:"
    docker-compose -f docker-compose.yml -f docker-compose.dev.yml ps --services
    exit 1
fi

echo "Connecting to $SERVICE container for debugging..."
echo "================================================"

# Execute interactive shell or command in the service container
docker-compose -f docker-compose.yml -f docker-compose.dev.yml exec "$SERVICE" $COMMAND

echo ""
echo "Debugging session ended"
echo ""
echo "Usage: $0 [service-name] [command]"
echo "Examples:"
echo "  $0                          # Connect to core service with bash"
echo "  $0 asr-service             # Connect to ASR service with bash"
echo "  $0 opensips-ai-core python # Start Python REPL in core service"