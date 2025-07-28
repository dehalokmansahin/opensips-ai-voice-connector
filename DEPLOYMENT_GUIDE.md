# IVR Flow Automation System - Deployment Guide

## Overview

The IVR Flow Automation System is a microservices-based platform for automated testing of Interactive Voice Response (IVR) systems, specifically designed for Turkish bank call center scenarios.

## System Architecture

### Core Services

1. **Intent Service** (Port 5000)
   - Turkish Bank Intent Recognition using BERT
   - REST API for text classification
   - Status: ✅ Production Ready

2. **TTS Service** (Port 50053) 
   - Text-to-Speech using Piper models
   - gRPC API for audio generation
   - Turkish voice support
   - Status: ✅ Production Ready

3. **Test Controller Service** (Port 50055)
   - IVR test orchestration and execution
   - Scenario management and results processing
   - REST API for test automation
   - Status: ✅ Production Ready

4. **ASR Service** (Port 50051) - OPTIONAL
   - Automatic Speech Recognition using Vosk
   - gRPC API for speech processing
   - Status: ⚠️ Requires Vosk models (not critical for IVR testing)

## Prerequisites

- Docker and Docker Compose
- Python 3.10+ (for health checking scripts)
- 8GB RAM minimum
- 20GB disk space

## Quick Start

### 1. Clone and Setup

```bash
git clone <repository-url>
cd opensips-ai-voice-connector
```

### 2. Start Core Services

```bash
# Start essential services for IVR testing
docker-compose up -d intent-service tts-service test-controller-service

# Check service status
docker-compose ps
```

### 3. Verify System Health

```bash
# Run comprehensive health check
python scripts/health_check.py
```

Expected output:
```
[READY] SYSTEM READY - All critical services operational
Critical services: 3/3 healthy
```

## Service Details

### Intent Service

**Purpose**: Turkish bank call center intent recognition

**Endpoints**:
- `GET /health` - Service health check
- `POST /classify` - Classify single text input
- `POST /v1/classify` - V1 API for classification
- `GET /intents` - List supported intents
- `GET /stats` - Service statistics

**Example Usage**:
```bash
curl -X POST http://localhost:5000/classify \
  -H "Content-Type: application/json" \
  -d '{"text": "I want to check my balance"}'
```

**Supported Intents**:
- `hesap_bakiye_sorgulama` - Account balance inquiry
- `kredi_karti_bilgi` - Credit card information
- `musteri_hizmetleri` - Customer service request
- `havale_eft` - Money transfer operations
- `sifre_unutma` - Password reset
- `hesap_acma` - Account opening
- `sikayet` - Complaint
- `bilinmeyen` - Unknown intent

### Test Controller Service

**Purpose**: IVR test scenario execution and management

**Key Endpoints**:
- `GET /health` - Service health check
- `GET /api/v1/scenarios` - List available test scenarios
- `POST /api/v1/scenarios/{id}/execute` - Execute test scenario
- `GET /api/v1/executions` - List active executions
- `GET /api/v1/executions/{id}/status` - Get execution status
- `GET /api/v1/executions/{id}/results` - Get detailed results

**Example Usage**:
```bash
# List scenarios
curl http://localhost:50055/api/v1/scenarios

# Check active executions
curl http://localhost:50055/api/v1/executions
```

### TTS Service

**Purpose**: Turkish text-to-speech generation

**Features**:
- gRPC API for audio synthesis
- Turkish voice model support
- Configurable audio parameters

**Configuration**:
- Model: `tr_TR-fahrettin-medium`
- Sample Rate: 22050 Hz
- Format: WAV

## Deployment Configurations

### Development Mode

```bash
# Start all services with logging
docker-compose up

# Restart specific service
docker-compose restart test-controller-service
```

### Production Mode

```bash
# Start in background with restart policies
docker-compose up -d

# View logs
docker-compose logs -f test-controller-service
```

### Service-Only Mode (Recommended)

```bash
# Start only the essential services
docker-compose up -d intent-service tts-service test-controller-service

# Skip ASR service if Vosk models are not available
```

## Monitoring and Health Checks

### Automated Health Monitoring

```bash
# Run comprehensive system check
python scripts/health_check.py

# Check specific service
curl http://localhost:5000/health  # Intent Service
curl http://localhost:50055/health # Test Controller
```

### Docker Health Checks

All services include built-in Docker health checks:

```bash
# Check container health status
docker-compose ps

# View detailed health status
docker inspect opensips-intent-service --format='{{.State.Health.Status}}'
```

### Service Logs

```bash
# View all service logs
docker-compose logs

# View specific service logs
docker-compose logs -f intent-service
docker-compose logs -f test-controller-service
```

## Configuration

### Environment Variables

**Intent Service**:
- `FLASK_ENV=production`
- `LOG_LEVEL=INFO`
- `FLASK_PORT=5000`

**Test Controller Service**:
- `TEST_CONTROLLER_HOST=0.0.0.0`
- `TEST_CONTROLLER_PORT=50055`
- `LOG_LEVEL=INFO`
- `INTENT_SERVICE_URL=intent-service:5000`
- `TTS_SERVICE_URL=tts-service:50053`

**TTS Service**:
- `PIPER_MODEL_NAME=tr_TR-fahrettin-medium`
- `PIPER_SAMPLE_RATE=22050`
- `LOG_LEVEL=INFO`

### Volume Mounts

- `./logs:/app/logs` - Application logs
- `./data:/app/data` - Persistent data storage
- `./config:/app/config` - Configuration files

## Troubleshooting

### Common Issues

**1. Services not starting**
```bash
# Check logs
docker-compose logs <service-name>

# Rebuild service
docker-compose build <service-name>
docker-compose up -d <service-name>
```

**2. Port conflicts**
```bash
# Check port usage
netstat -an | findstr :5000
netstat -an | findstr :50055

# Change ports in docker-compose.yml if needed
```

**3. Turkish character encoding issues**
- Use proper UTF-8 encoding in requests
- Set Content-Type header with charset

**4. ASR Service failing**
- ASR service is optional for IVR testing
- Requires Vosk models which are not included
- Can be safely ignored for basic functionality

### Performance Optimization

**Memory Usage**:
- Intent Service: ~512MB
- TTS Service: ~1GB (with models)
- Test Controller: ~256MB
- Total: ~2GB recommended

**CPU Usage**:
- Intent Service: Low (classification is fast)
- TTS Service: Medium (audio synthesis)
- Test Controller: Low (orchestration only)

## API Documentation

### Intent Service API

```bash
# Health check
GET /health

# Classify text
POST /classify
{
  "text": "hesap bakiyemi öğrenmek istiyorum",
  "confidence_threshold": 0.85
}

# Response
{
  "intent": "hesap_bakiye_sorgulama",
  "confidence": 0.92,
  "meets_threshold": true,
  "alternatives": [...],
  "processing_time_ms": 12.5
}
```

### Test Controller API

```bash
# List scenarios
GET /api/v1/scenarios

# Execute scenario
POST /api/v1/scenarios/{scenario_id}/execute

# Get execution status
GET /api/v1/executions/{execution_id}/status

# Get detailed results
GET /api/v1/executions/{execution_id}/results
```

## Security Considerations

1. **Network Security**:
   - Services run on isolated Docker network
   - Only necessary ports exposed to host

2. **Data Security**:
   - No sensitive data persisted in containers
   - Logs rotated and cleaned regularly

3. **Access Control**:
   - No authentication implemented (internal use)
   - Consider adding API keys for production

## Backup and Recovery

### Data Backup

```bash
# Backup persistent data
tar -czf backup-$(date +%Y%m%d).tar.gz ./data ./logs

# Backup configuration
cp docker-compose.yml docker-compose.yml.backup
```

### Service Recovery

```bash
# Full system restart
docker-compose down
docker-compose up -d

# Individual service restart
docker-compose restart <service-name>
```

## Scaling Considerations

### Horizontal Scaling

Each service can be scaled independently:

```yaml
# In docker-compose.yml
services:
  intent-service:
    deploy:
      replicas: 3
    # Load balancer needed
```

### Vertical Scaling

Adjust resource limits:

```yaml
services:
  intent-service:
    deploy:
      resources:
        limits:
          memory: 1G
          cpus: '1.0'
```

## Support and Maintenance

### Regular Maintenance Tasks

1. **Daily**: Check service health with `python scripts/health_check.py`
2. **Weekly**: Review logs for errors and performance issues
3. **Monthly**: Update Docker images and restart services
4. **Quarterly**: Review and optimize resource allocation

### Log Management

```bash
# View recent logs
docker-compose logs --tail=100 -f

# Clear old logs
docker-compose down
docker system prune -f
```

### Updates and Patches

```bash
# Update system
git pull origin main
docker-compose build
docker-compose up -d

# Verify after update
python scripts/health_check.py
```

## Performance Metrics

### Expected Performance

- **Intent Classification**: <50ms per request
- **TTS Generation**: ~1-3 seconds per sentence
- **Test Execution**: Depends on scenario complexity
- **System Startup**: ~30-60 seconds

### Monitoring Commands

```bash
# Resource usage
docker stats

# Service response times
curl -w "@curl-format.txt" -s -o /dev/null http://localhost:5000/health

# Health check with timing
time python scripts/health_check.py
```

---

## System Status Summary

✅ **Production Ready Components**:
- Intent Service (Turkish BERT classification)
- TTS Service (Turkish voice synthesis) 
- Test Controller Service (scenario execution)
- Comprehensive health monitoring
- Docker orchestration

⚠️ **Optional Components**:
- ASR Service (requires additional Vosk models)
- OpenSIPS Core (not needed for basic IVR testing)

🎯 **Ready for Use**:
The system is ready for IVR flow automation testing with Turkish bank call center scenarios. All critical services are operational and tested.