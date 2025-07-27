#!/bin/bash
# Development environment status check script

set -e

echo "OpenSIPS AI Voice Connector - Development Status"
echo "==============================================="

# Check if development environment is running
if docker-compose -f docker-compose.yml -f docker-compose.dev.yml ps | grep -q "Up"; then
    echo "✅ Development environment is RUNNING"
    echo ""
    
    echo "Service Status:"
    echo "---------------"
    docker-compose -f docker-compose.yml -f docker-compose.dev.yml ps
    
    echo ""
    echo "Health Check:"
    echo "-------------"
    
    # Check core application
    if curl -f http://localhost:8080/health >/dev/null 2>&1; then
        echo "✅ Core Application (http://localhost:8080) - HEALTHY"
    else
        echo "❌ Core Application (http://localhost:8080) - UNHEALTHY"
    fi
    
    # Check gRPC services (basic connection test)
    if command -v grpc-health-probe >/dev/null 2>&1; then
        for port in 50051 50052 50053; do
            if grpc-health-probe -addr=localhost:$port >/dev/null 2>&1; then
                echo "✅ gRPC Service (localhost:$port) - HEALTHY"
            else
                echo "❌ gRPC Service (localhost:$port) - UNHEALTHY"
            fi
        done
    else
        echo "⚠️  grpc-health-probe not available, skipping gRPC health checks"
    fi
    
    echo ""
    echo "Hot-reload Status:"
    echo "------------------"
    if [ "$DEVELOPMENT_MODE" = "1" ]; then
        echo "✅ Hot-reload is ENABLED"
    else
        echo "⚠️  Hot-reload status unclear (check container logs)"
    fi
    
else
    echo "❌ Development environment is NOT RUNNING"
    echo ""
    echo "To start: ./scripts/dev-start.sh"
fi

echo ""
echo "Quick Actions:"
echo "--------------"
echo "Start:   ./scripts/dev-start.sh"
echo "Stop:    ./scripts/dev-stop.sh"
echo "Restart: ./scripts/dev-restart.sh"
echo "Logs:    ./scripts/dev-logs.sh [service-name]"