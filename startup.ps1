#!/usr/bin/env pwsh
# OpenSIPS AI Voice Connector - Docker Compose Startup Script
# Tum servisleri orchestrate eder

Write-Host "OpenSIPS AI Voice Connector - Docker Compose Startup" -ForegroundColor Green
Write-Host ("=" * 60) -ForegroundColor Yellow

# Docker ve Docker Compose kontrolu
Write-Host "Checking Docker and Docker Compose..." -ForegroundColor Cyan
try {
    $dockerVersion = docker --version
    $composeVersion = docker-compose --version
    Write-Host "Docker: $dockerVersion" -ForegroundColor Green
    Write-Host "Docker Compose: $composeVersion" -ForegroundColor Green
} catch {
    Write-Host "Docker or Docker Compose not found!" -ForegroundColor Red
    Write-Host "Please install Docker Desktop and try again." -ForegroundColor Red
    exit 1
}

# Mevcut container'lari durdur ve temizle
Write-Host "`nStopping existing containers..." -ForegroundColor Yellow
docker-compose down --remove-orphans

# Images'i rebuild et (istege bagli)
$rebuildChoice = Read-Host "`nRebuild images? (y/N)"
if ($rebuildChoice -eq "y" -or $rebuildChoice -eq "Y") {
    Write-Host "Rebuilding images..." -ForegroundColor Cyan
    docker-compose build --no-cache
}

# Network'u temizle ve yeniden olustur
Write-Host "`nSetting up network..." -ForegroundColor Cyan
docker network prune -f
docker network create opensips_network 2>$null

# Volumes'i olustur
Write-Host "Creating volumes..." -ForegroundColor Cyan
docker volume create piper_models 2>$null
docker volume create llm_models 2>$null
docker volume create llm_cache 2>$null
docker volume create model_data 2>$null

# Servisleri sirayla baslat
Write-Host "`nStarting services..." -ForegroundColor Green

# 1. Once temel servisler
Write-Host "1. Starting OpenSIPS..." -ForegroundColor Cyan
docker-compose up -d opensips
Start-Sleep 5

# 2. AI Servisleri
Write-Host "2. Starting AI Services..." -ForegroundColor Cyan
docker-compose up -d vosk-server piper-tts-server llm-turkish-server
Start-Sleep 10

# 3. Ana uygulama (OAVC)
Write-Host "3. Starting OpenSIPS AI Voice Connector (OAVC)..." -ForegroundColor Cyan
docker-compose up -d opensips-ai-voice-connector
Start-Sleep 5

# Durum kontrolu
Write-Host "`nChecking service status..." -ForegroundColor Yellow
Start-Sleep 5

$services = @(
    "opensips",
    "vosk-server", 
    "piper-tts-server",
    "llm-turkish-server",
    "opensips-ai-voice-connector"
)

foreach ($service in $services) {
    $status = docker-compose ps $service --format "table {{.State}}" | Select-Object -Skip 1
    if ($status -match "Up") {
        Write-Host "$service : Running" -ForegroundColor Green
    } else {
        Write-Host "$service : Not Running" -ForegroundColor Red
    }
}

# Network bilgileri
Write-Host "`nNetwork Information:" -ForegroundColor Cyan
docker network inspect opensips_network --format '{{range .Containers}}{{.Name}}: {{.IPv4Address}}{{"\n"}}{{end}}'

# Servis URL'leri
Write-Host "`nService URLs:" -ForegroundColor Cyan
Write-Host "OpenSIPS SIP       : sip:localhost:5060" -ForegroundColor White
Write-Host "Vosk STT          : ws://localhost:2700" -ForegroundColor White
Write-Host "Piper TTS         : ws://localhost:8000/tts" -ForegroundColor White
Write-Host "LLM Turkish       : ws://localhost:8765" -ForegroundColor White
Write-Host "OAVC (Main App)   : tcp://localhost:8088-8089, udp://35010-35011" -ForegroundColor White

# Loglari goster
Write-Host "`nRecent logs:" -ForegroundColor Yellow
docker-compose logs --tail=10 opensips-ai-voice-connector

Write-Host "`nOpenSIPS AI Voice Connector started successfully!" -ForegroundColor Green
Write-Host "To view logs: docker-compose logs -f [service-name]" -ForegroundColor Cyan
Write-Host "To stop all: docker-compose down" -ForegroundColor Cyan

# Interruption test'i calistir
$testChoice = Read-Host "`nRun interruption tests? (y/N)"
if ($testChoice -eq "y" -or $testChoice -eq "Y") {
    Write-Host "Running interruption tests..." -ForegroundColor Cyan
    python test_interruption.py
}

Write-Host "`nAll systems ready! Happy calling!" -ForegroundColor Green