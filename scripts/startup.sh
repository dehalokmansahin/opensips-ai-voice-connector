#!/bin/sh
# ==============================================================================
# OpenSIPS AI Voice Connector - Telnyx-Style Startup Script
# ==============================================================================
# Simplified startup for new Telnyx-style architecture

set -e  # Exit on any error

echo "🚀 OpenSIPS AI Voice Connector - Telnyx Style"
echo "============================================="

# ==============================================================================
# 📁 DIRECTORY SETUP
# ==============================================================================



echo "✅ Directories created"

# ==============================================================================
# 🔍 ENVIRONMENT VALIDATION
# ==============================================================================

echo "🔍 Environment Configuration:"
echo "   - SIP Host: ${SIP_HOST:-0.0.0.0}"
echo "   - SIP Port: ${SIP_PORT:-8089}"
echo "   - Log Level: ${LOG_LEVEL:-INFO}"
echo "   - Debug Mode: ${DEBUG_MODE:-false}"

# AI Services
echo "   - VOSK URL: ${VOSK_WEBSOCKET_URL:-ws://vosk-server:2700}"
echo "   - LLM URL: ${LLAMA_WEBSOCKET_URL:-ws://llm-turkish-server:8765}"
echo "   - TTS URL: ${PIPER_WEBSOCKET_URL:-ws://piper-tts-server:8000/tts}"

# VAD Configuration
echo "   - VAD Confidence: ${VAD_CONFIDENCE:-0.2}"
echo "   - VAD Start: ${VAD_START_SECS:-0.05}s"
echo "   - VAD Stop: ${VAD_STOP_SECS:-0.4}s"

# ==============================================================================
# 🚀 SERVICE STARTUP
# ==============================================================================

# Determine what to start based on container role
if [ "$1" = "opensips" ]; then
    echo "🚀 Starting OpenSIPS SIP Proxy..."
    exec opensips -f /etc/opensips/opensips.cfg -D -E
    
elif [ "$1" = "oavc" ] || [ -z "$1" ]; then
    echo "🚀 Starting OpenSIPS AI Voice Connector..."
    echo "📋 Architecture: SIP Client → OpenSIPS (port 5060) → AI Backend (port 8089) → AI Pipeline"
    echo ""

    # Navigate to project directory
    cd /app

    # Verify Python and dependencies
    echo "🐍 Checking Python environment..."
    python --version
    echo ""

    # Check if required AI services are running
    echo "🤖 Checking AI service connectivity..."

    # Check STT service
    if python -c "import asyncio, websockets; asyncio.run(websockets.connect('${VOSK_WEBSOCKET_URL:-ws://vosk-server:2700}'))" 2>/dev/null; then
        echo "✅ STT Service (VOSK) reachable at ${VOSK_WEBSOCKET_URL:-ws://vosk-server:2700}"
    else
        echo "⚠️  STT Service (VOSK) not reachable at ${VOSK_WEBSOCKET_URL:-ws://vosk-server:2700}"
    fi

    # Check LLM service  
    if python -c "import asyncio, websockets; asyncio.run(websockets.connect('${LLAMA_WEBSOCKET_URL:-ws://llm-turkish-server:8765}'))" 2>/dev/null; then
        echo "✅ LLM Service (Llama) reachable at ${LLAMA_WEBSOCKET_URL:-ws://llm-turkish-server:8765}"
    else
        echo "⚠️  LLM Service (Llama) not reachable at ${LLAMA_WEBSOCKET_URL:-ws://llm-turkish-server:8765}"
    fi

    # Check TTS service
    if python -c "import asyncio, websockets; asyncio.run(websockets.connect('${PIPER_WEBSOCKET_URL:-ws://piper-tts-server:8000/tts}'))" 2>/dev/null; then
        echo "✅ TTS Service (Piper) reachable at ${PIPER_WEBSOCKET_URL:-ws://piper-tts-server:8000/tts}"
    else
        echo "⚠️  TTS Service (Piper) not reachable at ${PIPER_WEBSOCKET_URL:-ws://piper-tts-server:8000/tts}"
    fi

    echo ""
    echo "🎵 OpenSIPS proxy should be running separately on port 5060"
    echo "🤖 Starting AI Voice Backend on port 8089..."
    echo "🔗 This backend will receive calls forwarded from OpenSIPS proxy"
    echo ""

    # Start AI Voice Backend (NOT OpenSIPS itself!)
    exec python src/main.py
    
else
    echo "❌ Unknown startup command: $1"
    echo "Usage: $0 [opensips|oavc]"
    exit 1
fi 