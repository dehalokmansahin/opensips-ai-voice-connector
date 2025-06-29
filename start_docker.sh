#!/bin/bash

echo "🚀 OpenSIPS AI Voice Connector - Docker Compose Startup"
echo "=" * 60

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker first."
    exit 1
fi

# Check if docker-compose is available
if ! command -v docker-compose > /dev/null 2>&1; then
    echo "❌ docker-compose is not installed. Please install docker-compose first."
    exit 1
fi

echo "✅ Docker is running"
echo "✅ docker-compose is available"

# Build and start services
echo ""
echo "🔧 Building and starting services..."
echo "   📦 Building opensips-ai-voice-connector image..."
echo "   📥 Pulling external images (opensips, vosk, piper, ollama)..."
echo "   🚀 Starting all services..."

docker-compose up --build -d

# Check if services are running
echo ""
echo "⏳ Waiting for services to start..."
sleep 10

echo ""
echo "📊 Service Status:"
docker-compose ps

echo ""
echo "🔍 Checking service health..."

# Check Ollama
echo "📡 Checking Ollama service..."
if curl -s http://localhost:11434/api/tags > /dev/null; then
    echo "   ✅ Ollama is responding"
    
    # Pull llama3.2:3b model if not exists
    echo "   📥 Checking/pulling llama3.2:3b model..."
    docker-compose exec -T ollama ollama pull llama3.2:3b
    echo "   ✅ Llama3.2:3b model ready"
else
    echo "   ⚠️ Ollama is not responding yet"
fi

# Check Vosk
echo "📡 Checking Vosk service..."
if curl -s http://localhost:2700 > /dev/null; then
    echo "   ✅ Vosk is responding"
else
    echo "   ⚠️ Vosk is not responding yet"
fi

# Check Piper TTS
echo "📡 Checking Piper TTS service..."
if curl -s http://localhost:8000 > /dev/null; then
    echo "   ✅ Piper TTS is responding"
else
    echo "   ⚠️ Piper TTS is not responding yet"
fi

echo ""
echo "🎯 Services URLs:"
echo "   🤖 Ollama LLM:    http://localhost:11434"
echo "   🎤 Vosk STT:      ws://localhost:2700"
echo "   🔊 Piper TTS:     http://localhost:8000"
echo "   📞 OpenSIPS:      sip:localhost:5060"
echo "   🎛️ OAVC:          http://localhost:8088"

echo ""
echo "📋 Useful commands:"
echo "   📊 View logs:     docker-compose logs -f"
echo "   📊 View OAVC logs: docker-compose logs -f opensips-ai-voice-connector"
echo "   🔄 Restart:       docker-compose restart"
echo "   🛑 Stop:          docker-compose down"
echo "   🗑️ Clean:         docker-compose down -v"

echo ""
echo "🎉 OpenSIPS AI Voice Connector is starting up!"
echo "   ⏳ Please wait a few minutes for all services to fully initialize"
echo "   📊 Monitor logs with: docker-compose logs -f" 