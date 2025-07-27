#!/bin/bash
# Development testing script

set -e

echo "OpenSIPS AI Voice Connector - Development Testing"
echo "================================================="

# Ensure development environment is running
if ! docker-compose -f docker-compose.yml -f docker-compose.dev.yml ps | grep -q "Up"; then
    echo "❌ Development environment is not running"
    echo "Please start it first: ./scripts/dev-start.sh"
    exit 1
fi

echo "✅ Development environment is running"
echo ""

# Run tests inside the core container
echo "Running Unit Tests:"
echo "-------------------"
docker-compose -f docker-compose.yml -f docker-compose.dev.yml exec opensips-ai-core \
    python -m pytest /app/core/tests/ -v --tb=short

echo ""
echo "Running Integration Tests:"
echo "--------------------------"
docker-compose -f docker-compose.yml -f docker-compose.dev.yml exec opensips-ai-core \
    python -m pytest /app/tests/integration/ -v --tb=short

echo ""
echo "Testing gRPC Services:"
echo "----------------------"

# Test each gRPC service if grpc_cli is available
for service in asr llm tts; do
    echo "Testing $service service..."
    # Simple connection test using Python
    docker-compose -f docker-compose.yml -f docker-compose.dev.yml exec opensips-ai-core \
        python -c "
import grpc
import sys
try:
    channel = grpc.insecure_channel('${service}-service:5005$((51 + $(echo $service | wc -c) % 3))')
    grpc.channel_ready_future(channel).result(timeout=5)
    print('✅ $service service connection successful')
except Exception as e:
    print('❌ $service service connection failed:', e)
    sys.exit(1)
"
done

echo ""
echo "Development Testing Complete!"
echo "✅ All tests passed"