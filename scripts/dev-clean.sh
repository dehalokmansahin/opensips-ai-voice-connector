#!/bin/bash
# Development environment cleanup script

set -e

echo "OpenSIPS AI Voice Connector - Development Cleanup"
echo "================================================="

# Stop development environment
echo "Stopping development environment..."
docker-compose -f docker-compose.yml -f docker-compose.dev.yml down --remove-orphans

# Clean up development artifacts
echo "Cleaning up development artifacts..."

# Remove Python cache files
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true
find . -type f -name "*.pyo" -delete 2>/dev/null || true

# Clean up Docker build cache for development images
echo "Cleaning Docker build cache..."
docker builder prune -f

# Clean up unused development volumes (be careful with this)
echo "Cleaning unused Docker volumes..."
docker volume prune -f

# Clean up log files if they exist
if [ -d "logs" ]; then
    echo "Cleaning log files..."
    rm -rf logs/*.log 2>/dev/null || true
fi

echo ""
echo "Development cleanup complete!"
echo ""
echo "To restart clean development environment:"
echo "./scripts/dev-start.sh"