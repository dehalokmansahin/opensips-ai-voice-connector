#!/usr/bin/env pwsh
# OpenSIPS AI Voice Connector - Monitoring Script
# Tum servislerin durumunu izler

Write-Host "OpenSIPS AI Voice Connector - System Monitor" -ForegroundColor Green
Write-Host ("=" * 60) -ForegroundColor Yellow

function Show-ServiceStatus {
    Write-Host "`nService Status Check:" -ForegroundColor Cyan
    
    $services = @(
        @{Name="opensips"; Port=5060; Type="SIP"},
        @{Name="vosk-server"; Port=2700; Type="STT"},
        @{Name="piper-tts-server"; Port=8000; Type="TTS"},
        @{Name="llm-turkish-server"; Port=8765; Type="LLM"},

        @{Name="opensips-ai-voice-connector"; Port=8088; Type="Main"}
    )
    
    foreach ($service in $services) {
        $containerStatus = docker-compose ps $service.Name --format "table {{.State}}" | Select-Object -Skip 1
        
        if ($containerStatus -match "Up") {
            # Port kontrolu
            $portCheck = Test-NetConnection -ComputerName localhost -Port $service.Port -WarningAction SilentlyContinue
            if ($portCheck.TcpTestSucceeded) {
                Write-Host "$($service.Name) ($($service.Type)): Running & Port $($service.Port) Open" -ForegroundColor Green
            } else {
                Write-Host "$($service.Name) ($($service.Type)): Running but Port $($service.Port) Closed" -ForegroundColor Yellow
            }
        } else {
            Write-Host "$($service.Name) ($($service.Type)): Not Running" -ForegroundColor Red
        }
    }
}

function Show-ResourceUsage {
    Write-Host "`nResource Usage:" -ForegroundColor Cyan
    
    $stats = docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}"
    Write-Host $stats
}

function Show-NetworkInfo {
    Write-Host "`nNetwork Information:" -ForegroundColor Cyan
    
    try {
        $networkInfo = docker network inspect opensips_network --format '{{range .Containers}}{{.Name}}: {{.IPv4Address}}{{"\n"}}{{end}}'
        Write-Host $networkInfo
    } catch {
        Write-Host "Network 'opensips_network' not found" -ForegroundColor Red
    }
}

function Show-RecentLogs {
    param([string]$ServiceName = "opensips-ai-voice-connector")
    
    Write-Host "`nRecent Logs for ${ServiceName}:" -ForegroundColor Cyan
    docker-compose logs --tail=20 $ServiceName
}

function Test-AIServices {
    Write-Host "`nTesting AI Services:" -ForegroundColor Cyan
    
    # Vosk STT Test
    try {
        $voskTest = Test-NetConnection -ComputerName localhost -Port 2700 -WarningAction SilentlyContinue
        if ($voskTest.TcpTestSucceeded) {
            Write-Host "Vosk STT: Accessible" -ForegroundColor Green
        } else {
            Write-Host "Vosk STT: Not accessible" -ForegroundColor Red
        }
    } catch {
        Write-Host "Vosk STT: Connection failed" -ForegroundColor Red
    }
    
    # Piper TTS Test
    try {
        $piperTest = Test-NetConnection -ComputerName localhost -Port 8000 -WarningAction SilentlyContinue
        if ($piperTest.TcpTestSucceeded) {
            Write-Host "Piper TTS: Accessible" -ForegroundColor Green
        } else {
            Write-Host "Piper TTS: Not accessible" -ForegroundColor Red
        }
    } catch {
        Write-Host "Piper TTS: Connection failed" -ForegroundColor Red
    }
    
    # LLM Turkish Server Test
    try {
        $llmTest = Test-NetConnection -ComputerName localhost -Port 8765 -WarningAction SilentlyContinue
        if ($llmTest.TcpTestSucceeded) {
            Write-Host "LLM Turkish: Accessible" -ForegroundColor Green
        } else {
            Write-Host "LLM Turkish: Not accessible" -ForegroundColor Red
        }
    } catch {
        Write-Host "LLM Turkish: Connection failed" -ForegroundColor Red
    }
}

function Show-InterruptionStatus {
    Write-Host "`nInterruption System Status:" -ForegroundColor Cyan
    
    # Interruption test calistir
    try {
        $testResult = python test_interruption.py 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Interruption System: All tests passed" -ForegroundColor Green
        } else {
            Write-Host "Interruption System: Some tests failed" -ForegroundColor Red
            Write-Host "Run 'python test_interruption.py' for details" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "Interruption System: Cannot run tests" -ForegroundColor Yellow
    }
}

# Ana monitoring loop
while ($true) {
    Clear-Host
    Write-Host "OpenSIPS AI Voice Connector - System Monitor" -ForegroundColor Green
    Write-Host "Last Update: $(Get-Date)" -ForegroundColor Gray
    Write-Host ("=" * 60) -ForegroundColor Yellow
    
    Show-ServiceStatus
    Show-ResourceUsage
    Show-NetworkInfo
    Test-AIServices
    Show-InterruptionStatus
    
    Write-Host "`nCommands:" -ForegroundColor Cyan
    Write-Host "  [L] Show logs for a service" -ForegroundColor White
    Write-Host "  [R] Restart a service" -ForegroundColor White
    Write-Host "  [T] Run interruption tests" -ForegroundColor White
    Write-Host "  [Q] Quit monitor" -ForegroundColor White
    Write-Host "  [Enter] Refresh (auto-refresh in 30s)" -ForegroundColor White
    
    $timeout = 30
    $choice = $null
    
    for ($i = $timeout; $i -gt 0; $i--) {
        Write-Host "`rRefreshing in $i seconds... (Press any key to interact)" -NoNewline -ForegroundColor Yellow
        
        if ([Console]::KeyAvailable) {
            $choice = [Console]::ReadKey($true).KeyChar
            break
        }
        
        Start-Sleep 1
    }
    
    Write-Host "`r" + " " * 60 + "`r" -NoNewline
    
    switch ($choice) {
        'l' { 
            $service = Read-Host "Enter service name"
            Show-RecentLogs -ServiceName $service
            Read-Host "Press Enter to continue"
        }
        'r' { 
            $service = Read-Host "Enter service name to restart"
            Write-Host "Restarting $service..." -ForegroundColor Yellow
            docker-compose restart $service
            Read-Host "Press Enter to continue"
        }
        't' { 
            Write-Host "Running interruption tests..." -ForegroundColor Cyan
            python test_interruption.py
            Read-Host "Press Enter to continue"
        }
        'q' { 
            Write-Host "Goodbye!" -ForegroundColor Green
            exit 
        }
    }
} 