# OpenSIPS AI Voice Connector - Docker Compose Startup Script for Windows
# PowerShell version

Write-Host "🚀 OpenSIPS AI Voice Connector - Docker Compose Startup" -ForegroundColor Green
Write-Host ("=" * 60) -ForegroundColor Yellow

# Check if Docker is running
try {
    docker info | Out-Null
    Write-Host "✅ Docker is running" -ForegroundColor Green
}
catch {
    Write-Host "❌ Docker is not running. Please start Docker Desktop first." -ForegroundColor Red
    exit 1
}

# Check if docker-compose is available
try {
    docker-compose --version | Out-Null
    Write-Host "✅ docker-compose is available" -ForegroundColor Green
}
catch {
    Write-Host "❌ docker-compose is not installed. Please install docker-compose first." -ForegroundColor Red
    exit 1
}

# Build and start services
Write-Host ""
Write-Host "🔧 Building and starting services..." -ForegroundColor Cyan
Write-Host "   📦 Building opensips-ai-voice-connector image..."
Write-Host "   📥 Pulling external images (opensips, vosk, piper, ollama)..."
Write-Host "   🚀 Starting all services..."

docker-compose up --build -d

# Check if services are running
Write-Host ""
Write-Host "⏳ Waiting for services to start..." -ForegroundColor Yellow
Start-Sleep -Seconds 10

Write-Host ""
Write-Host "📊 Service Status:" -ForegroundColor Cyan
docker-compose ps

Write-Host ""
Write-Host "🔍 Checking service health..." -ForegroundColor Cyan

# Check LLaMA Server
Write-Host "📡 Checking LLaMA server..." -ForegroundColor Blue
try {
    # Note: WebSocket test is more complex, so we'll check if the container is running
    $llamaContainer = docker-compose ps llama-server --format json | ConvertFrom-Json
    if ($llamaContainer.State -eq "running") {
        Write-Host "   ✅ LLaMA server container is running" -ForegroundColor Green
        Write-Host "   📝 Run test: python test_llama_integration.py" -ForegroundColor Yellow
    } else {
        Write-Host "   ⚠️ LLaMA server container is not running" -ForegroundColor Yellow
    }
}
catch {
    Write-Host "   ⚠️ LLaMA server status unknown" -ForegroundColor Yellow
}

# Check Vosk
Write-Host "📡 Checking Vosk service..." -ForegroundColor Blue
try {
    $null = Invoke-WebRequest -Uri "http://localhost:2700" -TimeoutSec 5 -ErrorAction Stop
    Write-Host "   ✅ Vosk is responding" -ForegroundColor Green
}
catch {
    Write-Host "   ⚠️ Vosk is not responding yet" -ForegroundColor Yellow
}

# Check Piper TTS
Write-Host "📡 Checking Piper TTS service..." -ForegroundColor Blue
try {
    $null = Invoke-WebRequest -Uri "http://localhost:8000" -TimeoutSec 5 -ErrorAction Stop
    Write-Host "   ✅ Piper TTS is responding" -ForegroundColor Green
}
catch {
    Write-Host "   ⚠️ Piper TTS is not responding yet" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "🎯 Services URLs:" -ForegroundColor Magenta
Write-Host "   🤖 LLaMA Server:  ws://localhost:8765"
Write-Host "   🎤 Vosk STT:      ws://localhost:2700"
Write-Host "   🔊 Piper TTS:     http://localhost:8000"
Write-Host "   📞 OpenSIPS:      sip:localhost:5060"
Write-Host "   🎛️ OAVC:          http://localhost:8088"

Write-Host ""
Write-Host "📋 Useful commands:" -ForegroundColor Cyan
Write-Host "   📊 View logs:       docker-compose logs -f"
Write-Host "   📊 View OAVC logs:  docker-compose logs -f opensips-ai-voice-connector"
Write-Host "   🔄 Restart:         docker-compose restart"
Write-Host "   🛑 Stop:            docker-compose down"
Write-Host "   🗑️ Clean:           docker-compose down -v"

Write-Host ""
Write-Host "🎉 OpenSIPS AI Voice Connector is starting up!" -ForegroundColor Green
Write-Host "   ⏳ Please wait a few minutes for all services to fully initialize" -ForegroundColor Yellow
Write-Host "   📊 Monitor logs with: docker-compose logs -f" -ForegroundColor Cyan

Write-Host ""
Write-Host "🔧 Next Steps:" -ForegroundColor Magenta
Write-Host "   1. Wait for all services to initialize (2-3 minutes)"
Write-Host "   2. Check logs: docker-compose logs -f"
Write-Host "   3. Test with SIP client on localhost:5060"
Write-Host "   4. Monitor pipeline with: docker-compose logs -f opensips-ai-voice-connector" 