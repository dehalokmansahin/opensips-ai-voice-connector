#!/bin/bash
# Fast development restart script for hot-reload optimization

set -e

echo "Restarting OpenSIPS AI Voice Connector - Development Mode"
echo "=========================================================="

# Fast restart without rebuild (for hot-reload)
echo "Restarting services..."
docker-compose -f docker-compose.yml -f docker-compose.dev.yml restart

echo "Services restarted!"
echo "Hot-reload should be active within 30 seconds"