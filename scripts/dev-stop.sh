#!/bin/bash
# Fast development stop script

set -e

echo "Stopping OpenSIPS AI Voice Connector - Development Mode"
echo "======================================================="

# Graceful shutdown with cleanup
docker-compose -f docker-compose.yml -f docker-compose.dev.yml down --remove-orphans

echo "Development environment stopped!"
echo ""
echo "To restart: ./scripts/dev-start.sh"