# Infrastructure and Deployment Integration

### Existing Infrastructure
**Current Deployment:** Docker Compose with health checks, service dependencies, and network isolation on bridge network 172.20.0.0/16

**Infrastructure Tools:** Docker containerization, health probe monitoring, volume mounting for models and logs, environment-based configuration

**Environments:** Single docker-compose.yml with dev/prod variants (docker-compose.dev.yml, docker-compose.prod.yml)

### Enhancement Deployment Strategy
**Deployment Approach:** Extend existing Docker Compose architecture with new services, maintaining health check patterns and service dependency management

**Infrastructure Changes:** 
- Add Intent Recognition service container (CPU-optimized)
- Add Test Controller service container
- Remove LLM service container and GPU dependencies
- Extend existing web interface or add new web management container
- Add SQLite volume mounts for test data persistence

**Pipeline Integration:** Leverage existing build scripts (build-dev.sh, build-prod.sh), extend existing validation scripts (validate-dev-setup.sh), integrate with existing test framework (pytest-based)

### Updated Docker Compose Configuration

```yaml
services:
  # Existing services - preserved
  asr-service:          # PRESERVED - no changes
  tts-service:          # PRESERVED - no changes
  # llm-service:        # REMOVED - no longer needed

  # New IVR testing services
  intent-service:
    build:
      context: ./services/intent-service
      dockerfile: Dockerfile
    container_name: opensips-intent-service
    ports:
      - "50054:50054"
    environment:
      - INTENT_SERVICE_LISTEN_ADDR=[::]:50054
      - BERT_MODEL_NAME=dbmdz/bert-base-turkish-uncased
      - ONNX_OPTIMIZATION=true
      - LOG_LEVEL=INFO
      - INTENT_MAX_WORKERS=4
    volumes:
      - ./data/training_data:/app/training_data:rw
    healthcheck:
      test: ["CMD", "grpc-health-probe", "-addr=localhost:50054", "-service=IntentService"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    restart: unless-stopped
    networks:
      - opensips-ai-network

  test-controller:
    build:
      context: ./services/test-controller-service
      dockerfile: Dockerfile
    container_name: opensips-test-controller
    ports:
      - "50055:50055"
    environment:
      - TEST_CONTROLLER_LISTEN_ADDR=[::]:50055
      - ASR_SERVICE_URL=asr-service:50051
      - TTS_SERVICE_URL=tts-service:50053
      - INTENT_SERVICE_URL=intent-service:50054
      - OPENSIPS_MI_URL=opensips-ai-core:8080
      - DATABASE_PATH=/app/data/test_scenarios.db
      - LOG_LEVEL=INFO
    volumes:
      - ./data:/app/data:rw
    depends_on:
      asr-service:
        condition: service_healthy
      tts-service:
        condition: service_healthy
      intent-service:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "grpc-health-probe", "-addr=localhost:50055", "-service=TestController"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
    restart: unless-stopped
    networks:
      - opensips-ai-network

  # Modified core service
  opensips-ai-core:
    build:
      context: .
      dockerfile: Dockerfile.core
    container_name: opensips-ai-core
    ports:
      - "8080:8080"  # HTTP management + web interface
      - "5060:5060/udp"  # SIP (modified for outbound)
      - "10000-10100:10000-10100/udp"  # RTP range
    environment:
      - CORE_LOG_LEVEL=INFO
      - ASR_SERVICE_URL=asr-service:50051
      - TTS_SERVICE_URL=tts-service:50053
      - INTENT_SERVICE_URL=intent-service:50054
      - TEST_CONTROLLER_URL=test-controller:50055
      - OPENSIPS_MODE=OUTBOUND_IVR_TESTING  # NEW - IVR testing mode
      - OPENSIPS_HOST=0.0.0.0
      - OPENSIPS_PORT=5060
      - RTP_PORT_RANGE_START=10000
      - RTP_PORT_RANGE_END=10100
    depends_on:
      asr-service:
        condition: service_healthy
      tts-service:
        condition: service_healthy
      intent-service:
        condition: service_healthy
      test-controller:
        condition: service_healthy
    volumes:
      - ./config:/app/config:ro
      - ./logs:/app/logs:rw
      - ./data:/app/data:rw  # NEW - test data access
```

### Rollback Strategy
**Rollback Method:** Docker Compose service rollback, maintain existing service versions in parallel during transition, database backup and restore procedures for test data

**Risk Mitigation:** 
- Preserve existing voice assistant functionality during transformation
- Independent service deployment allows selective rollback
- Test data isolation prevents impact on existing functionality
- Health check validation ensures service stability

**Monitoring:** 
- Extend existing health check monitoring to new services
- Add test execution monitoring and alerting
- Maintain existing log aggregation patterns
- Add test-specific metrics collection
