#!/bin/bash

# Development Environment Setup Script
set -e

echo "🚀 Setting up OpenSIPS AI Voice Connector development environment..."

# Check prerequisites
echo "📋 Checking prerequisites..."

# Check Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is required but not installed"
    exit 1
fi

# Check Docker Compose
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is required but not installed"
    exit 1
fi

# Check Python 3.11+
python_version=$(python3 --version 2>&1 | awk '{print $2}' | cut -d. -f1,2)
if ! python3 -c "import sys; exit(0 if sys.version_info >= (3, 11) else 1)" 2>/dev/null; then
    echo "❌ Python 3.11+ is required (found $python_version)"
    exit 1
fi

echo "✅ Prerequisites check passed"

# Create necessary directories
echo "📁 Creating directories..."
mkdir -p logs/{opensips,ai-voice-connector,vad,asr,llm,tts,session,context,banking}
mkdir -p data/{models,cache}

# Copy environment file
echo "⚙️ Setting up environment configuration..."
if [ ! -f .env ]; then
    cp .env.development .env
    echo "✅ Created .env from .env.development"
else
    echo "ℹ️ .env already exists, skipping copy"
fi

# Build base Docker image
echo "🐳 Building base Docker image..."
docker build -f infrastructure/docker/Dockerfile.base -t opensips-ai-voice-connector:base .

# Install Python development dependencies
echo "🐍 Installing Python development dependencies..."
pip install -e ".[dev]"

# Generate gRPC code
echo "🔧 Generating gRPC code..."
./scripts/proto-gen.sh

# Initialize database (if needed)
echo "🗄️ Initializing database..."
if [ ! -f .db-initialized ]; then
    docker-compose -f infrastructure/docker/docker-compose.dev.yml up -d postgres redis
    sleep 10  # Wait for database to be ready
    
    # Run database migrations
    echo "Running database migrations..."
    # Add migration commands here when ready
    
    touch .db-initialized
    echo "✅ Database initialized"
else
    echo "ℹ️ Database already initialized"
fi

# Pre-commit hooks setup
echo "🎣 Setting up pre-commit hooks..."
if command -v pre-commit &> /dev/null; then
    pre-commit install
    echo "✅ Pre-commit hooks installed"
else
    echo "⚠️ pre-commit not found, skipping hooks setup"
fi

echo ""
echo "🎉 Development environment setup complete!"
echo ""
echo "Next steps:"
echo "1. Start services: docker-compose -f infrastructure/docker/docker-compose.dev.yml up"
echo "2. Run tests: ./scripts/test-all.sh"
echo "3. View logs: docker-compose logs -f"
echo ""
echo "Useful commands:"
echo "- Start all services: docker-compose -f infrastructure/docker/docker-compose.dev.yml up -d"
echo "- Stop all services: docker-compose -f infrastructure/docker/docker-compose.dev.yml down"
echo "- View service status: docker-compose -f infrastructure/docker/docker-compose.dev.yml ps"
echo "- Follow logs: docker-compose -f infrastructure/docker/docker-compose.dev.yml logs -f [service-name]"