#!/bin/bash
# ==============================================================================
# OpenSIPS AI Voice Connector - Dynamic Startup Script
# ==============================================================================
# Bu script environment variable'ları kullanarak config template'ini process eder
# ve servisleri başlatır

set -e  # Exit on any error

# ==============================================================================
# 🔧 CONFIGURATION PROCESSING
# ==============================================================================

echo "🚀 OpenSIPS AI Voice Connector Dynamic Startup"
echo "==============================================="

# Environment variable defaults
OPENSIPS_LOG_LEVEL=${OPENSIPS_LOG_LEVEL:-3}
OPENSIPS_LOG_FACILITY=${OPENSIPS_LOG_FACILITY:-local0}
OPENSIPS_SIP_SECONDARY_PORT=${OPENSIPS_SIP_SECONDARY_PORT:-8080}
OPENSIPS_MI_PORT=${OPENSIPS_MI_PORT:-8087}
OPENSIPS_EVENT_PORT=${OPENSIPS_EVENT_PORT:-8090}
OAVC_HOST=${OAVC_HOST:-opensips-ai-voice-connector}
OAVC_SIP_PORT=${OAVC_SIP_PORT:-8089}

echo "📋 Configuration Values:"
echo "   - OpenSIPS Log Level: $OPENSIPS_LOG_LEVEL"
echo "   - OpenSIPS Log Facility: $OPENSIPS_LOG_FACILITY"
echo "   - OpenSIPS Secondary SIP Port: $OPENSIPS_SIP_SECONDARY_PORT"
echo "   - OpenSIPS MI Port: $OPENSIPS_MI_PORT"
echo "   - OpenSIPS Event Port: $OPENSIPS_EVENT_PORT"
echo "   - OAVC Host: $OAVC_HOST"
echo "   - OAVC SIP Port: $OAVC_SIP_PORT"

# ==============================================================================
# 📁 DIRECTORY SETUP
# ==============================================================================

# Create necessary directories
echo "📁 Creating directories..."
mkdir -p /app/logs
mkdir -p /app/logs/opensips
mkdir -p /app/logs/event-monitor
mkdir -p /var/log/opensips

# Set permissions
chmod 755 /app/logs
chmod 755 /app/logs/opensips
chmod 755 /app/logs/event-monitor
chmod 755 /var/log/opensips

# ==============================================================================
# ⚙️ CONFIG TEMPLATE PROCESSING
# ==============================================================================

# Function to process config template
process_config_template() {
    local template_file="$1"
    local output_file="$2"
    
    echo "🔧 Processing config template: $template_file -> $output_file"
    
    # Use sed to replace environment variables in template
    sed -e "s/__OPENSIPS_LOG_LEVEL__/$OPENSIPS_LOG_LEVEL/g" \
        -e "s/__OPENSIPS_LOG_FACILITY__/$OPENSIPS_LOG_FACILITY/g" \
        -e "s/__OPENSIPS_SIP_SECONDARY_PORT__/$OPENSIPS_SIP_SECONDARY_PORT/g" \
        -e "s/__OPENSIPS_MI_PORT__/$OPENSIPS_MI_PORT/g" \
        -e "s/__OPENSIPS_EVENT_PORT__/$OPENSIPS_EVENT_PORT/g" \
        -e "s/__OAVC_HOST__/$OAVC_HOST/g" \
        -e "s/__OAVC_SIP_PORT__/$OAVC_SIP_PORT/g" \
        "$template_file" > "$output_file"
    
    echo "✅ Config template processed successfully"
}

# Process OpenSIPS config template only if running OpenSIPS container
if [ "$1" = "opensips" ]; then
    if [ -f "/app/cfg/opensips.cfg.template" ]; then
        process_config_template "/app/cfg/opensips.cfg.template" "/etc/opensips/opensips.cfg"
    elif [ -f "/app/cfg/opensips.cfg" ]; then
        echo "📋 Using existing OpenSIPS config: /app/cfg/opensips.cfg"
        cp /app/cfg/opensips.cfg /etc/opensips/opensips.cfg
    else
        echo "⚠️ No OpenSIPS config found! Creating minimal config..."
        cat > /etc/opensips/opensips.cfg << EOF
# Minimal OpenSIPS Configuration
log_level=3
log_stderror=no
socket=udp:0.0.0.0:5060
loadmodule "sl.so"
route {
    sl_send_reply("503", "Service Temporarily Unavailable");
}
EOF
    fi
fi

# ==============================================================================
# 🔍 VALIDATION
# ==============================================================================

echo "🔍 Validating configuration..."

# Check if OpenSIPS config is valid (only for OpenSIPS container)
if [ "$1" = "opensips" ] && command -v opensips &> /dev/null; then
    echo "📋 Validating OpenSIPS configuration syntax..."
    if opensips -c -f /etc/opensips/opensips.cfg; then
        echo "✅ OpenSIPS configuration is valid"
    else
        echo "❌ OpenSIPS configuration has errors!"
        exit 1
    fi
elif [ "$1" = "opensips" ]; then
    echo "⚠️ OpenSIPS not found, skipping config validation"
fi

# Check required environment variables for OAVC
if [ "$1" = "oavc" ] || [ -z "$1" ]; then
    echo "🔍 Checking required environment variables for OAVC..."
    required_vars=("CONFIG_FILE" "PYTHONPATH")
    missing_vars=()

    for var in "${required_vars[@]}"; do
        if [ -z "${!var}" ]; then
            missing_vars+=("$var")
        fi
    done

    if [ ${#missing_vars[@]} -ne 0 ]; then
        echo "❌ Missing required environment variables: ${missing_vars[*]}"
        exit 1
    fi

    echo "✅ Environment validation passed"
fi

# ==============================================================================
# 🚀 SERVICE STARTUP
# ==============================================================================

# Determine what to start based on container role
if [ "$1" = "opensips" ]; then
    echo "🚀 Starting OpenSIPS SIP Proxy..."
    exec opensips -f /etc/opensips/opensips.cfg -D -E
    
elif [ "$1" = "event-monitor" ]; then
    echo "🚀 Starting OpenSIPS Event Monitor..."
    cd /app
    exec python src/opensips_event_listener.py
    
elif [ "$1" = "oavc" ] || [ -z "$1" ]; then
    echo "🚀 Starting OpenSIPS AI Voice Connector (OAVC)..."
    
    # Wait for dependencies if in Docker Compose environment
    if [ "$WAIT_FOR_DEPS" = "true" ]; then
        echo "⏳ Waiting for dependencies..."
        
        # Wait for OpenSIPS
        while ! nc -z opensips 5060; do
            echo "   🔗 Waiting for OpenSIPS (5060)..."
            sleep 2
        done
        
        # Wait for AI services
        while ! nc -z vosk-server "${VOSK_PORT:-2700}"; do
            echo "   🎙️ Waiting for Vosk STT (${VOSK_PORT:-2700})..."
            sleep 2
        done
        
        while ! nc -z piper-tts-server "${PIPER_PORT:-8000}"; do
            echo "   🔊 Waiting for Piper TTS (${PIPER_PORT:-8000})..."
            sleep 2
        done
        
        while ! nc -z llm-turkish-server "${LLM_PORT:-8765}"; do
            echo "   🧠 Waiting for LLM (${LLM_PORT:-8765})..."
            sleep 2
        done
        
        echo "✅ All dependencies ready!"
    fi
    
    # Start OAVC
    cd /app
    
    # Check if test mode
    if [ "$TEST_MODE" = "true" ]; then
        echo "🧪 Starting in TEST MODE..."
        exec python -m pytest tests/ -v
    else
        echo "🎯 Starting in PRODUCTION MODE..."
        exec python src/main.py
    fi
    
else
    echo "❌ Unknown startup command: $1"
    echo "Usage: $0 [opensips|event-monitor|oavc]"
    exit 1
fi 