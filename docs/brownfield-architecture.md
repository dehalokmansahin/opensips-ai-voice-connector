# OpenSIPS AI Voice Connector - Brownfield Architecture Document

## Introduction

This document captures the CURRENT STATE of the OpenSIPS AI Voice Connector codebase, including technical patterns, integration points, and architecture considerations. It serves as a reference for the planned architecture modernization to support Google Cloud Platform deployment, Twilio telephony, Ollama LLMs, and Faster-whisper STT.

### Document Scope

Focused on areas relevant to: **Architecture Modernization for GCP deployment with Twilio telephony, Ollama LLM support, and Faster-whisper STT integration**

### Change Log

| Date       | Version | Description                                    | Author    |
| ---------- | ------- | ---------------------------------------------- | --------- |
| 2025-01-07 | 1.0     | Initial brownfield analysis for modernization | Architect |

## Quick Reference - Key Files and Entry Points

### Critical Files for Understanding the System

- **Main Entry**: `src/main.py` - Simplified main entry following Twilio/Telnyx pattern
- **OpenSIPS Bot**: `src/opensips_bot.py` - Core bot implementation
- **Configuration**: `cfg/opensips-ai-voice-connector.ini`, `src/config.py`
- **Transport Layer**: `src/transports/opensips_transport.py` - OpenSIPS integration
- **Service Integrations**: 
  - `src/services/vosk_websocket.py` - Current STT (to be replaced with Faster-whisper)
  - `src/services/llama_websocket.py` - Current LLM (to be supplemented with Ollama)
  - `src/services/piper_websocket.py` - Current TTS
- **Pipeline**: `src/pipeline/` - Audio processing pipeline
- **Docker Config**: `docker-compose.dev.yml`, `Dockerfile`

### Enhancement Impact Areas for Modernization

Files/modules that will be affected by the planned enhancement:
- `src/transports/` - Add Twilio transport alongside OpenSIPS
- `src/services/` - Add Ollama and Faster-whisper services
- `docker-compose.yml` - Restructure for GCP deployment
- `src/config.py` - Add multi-provider configuration
- New: Cloud deployment configs (GKE, Cloud Run)

## High Level Architecture

### Technical Summary

Currently a monolithic Python application using OpenSIPS for SIP telephony, with containerized AI services for STT/TTS/LLM. Uses Pipecat framework for audio pipeline management. Architecture follows a simplified pattern inspired by Twilio/Telnyx implementations.

### Actual Tech Stack

| Category       | Technology        | Version      | Notes                                        |
| -------------- | ----------------- | ------------ | -------------------------------------------- |
| Runtime        | Python            | 3.11+        | Async-based with asyncio                    |
| Framework      | Pipecat           | Local fork   | Custom fork in `/pipecat` directory         |
| SIP Proxy      | OpenSIPS          | 3.6          | Current telephony layer                     |
| STT            | Vosk              | Turkish model| WebSocket-based, to be replaced             |
| LLM            | Llama 3.2         | 3b-turkish   | Local deployment, WebSocket                 |
| TTS            | Piper             | Turkish voice| WebSocket-based                             |
| Container      | Docker Compose    | v2           | Local development setup                     |
| Audio Codec    | PCMU/PCMA         | G.711        | RTP transport                                |

### Repository Structure Reality Check

- Type: Monorepo with embedded Pipecat fork
- Package Manager: pip (Python)
- Notable: Pipecat framework is included as local source, not as dependency

## Source Tree and Module Organization

### Project Structure (Actual)

```text
opensips-ai-voice-connector/
├── src/
│   ├── main.py                    # Main entry point (simplified pattern)
│   ├── opensips_bot.py           # Core bot implementation
│   ├── config.py                 # Configuration loader
│   ├── opensips_event_listener.py # OpenSIPS event handling
│   ├── pipeline/
│   │   ├── aggregators/          # Sentence aggregation
│   │   └── (pipeline modules)
│   ├── services/                 # AI service integrations
│   │   ├── vosk_websocket.py    # STT service (Vosk)
│   │   ├── llama_websocket.py   # LLM service (Llama)
│   │   └── piper_websocket.py   # TTS service (Piper)
│   ├── transports/               # Communication layers
│   │   ├── opensips_transport.py # OpenSIPS/RTP transport
│   │   ├── rtp_utils.py         # RTP packet handling
│   │   └── sip_backend_listener.py # SIP backend
│   └── serializers/              # Frame serialization
│       └── opensips.py           # OpenSIPS frame serializer
├── pipecat/                      # Embedded Pipecat framework (fork)
│   ├── src/pipecat/              # Pipecat source
│   └── examples/                 # Including twilio-chatbot example
├── cfg/                          # Configuration files
│   ├── opensips-ai-voice-connector.ini
│   └── opensips.cfg              # OpenSIPS configuration
├── docker/                       # Docker configurations
├── tests/                        # Test suite
└── docs/                         # Documentation
```

### Key Modules and Their Purpose

- **Main Application**: `src/main.py` - Orchestrates bot instances per call
- **OpenSIPS Bot**: `src/opensips_bot.py` - Pipecat pipeline configuration
- **Event Listener**: `src/opensips_event_listener.py` - Handles OpenSIPS events
- **Transport Layer**: `src/transports/opensips_transport.py` - RTP/audio handling
- **Service Adapters**: `src/services/*.py` - WebSocket clients for AI services
- **Pipeline Aggregators**: `src/pipeline/aggregators/` - Audio/text processing

## Current Integration Architecture

### External Services

| Service        | Purpose  | Integration Type | Key Files                           |
| -------------- | -------- | ---------------- | ----------------------------------- |
| OpenSIPS       | SIP Proxy| UDP/Datagram     | `src/opensips_event_listener.py`   |
| Vosk Server    | STT      | WebSocket        | `src/services/vosk_websocket.py`   |
| Llama Server   | LLM      | WebSocket        | `src/services/llama_websocket.py`  |
| Piper Server   | TTS      | WebSocket        | `src/services/piper_websocket.py`  |

### Internal Integration Points

- **OpenSIPS Communication**: MI Datagram for commands, Event Datagram for notifications
- **Audio Pipeline**: VAD → STT → LLM → TTS with barge-in interruption
- **WebSocket Services**: All AI services use WebSocket for streaming
- **RTP Transport**: Port range 35000-35500 for audio streams

## Technical Patterns and Constraints

### Current Patterns

1. **Simplified Architecture**: Following Twilio/Telnyx pattern from examples
2. **Per-Call Bot Instance**: Each call spawns a new bot task
3. **WebSocket Streaming**: All AI services use WebSocket for real-time streaming
4. **Pipecat Pipeline**: Linear pipeline with frame-based processing
5. **Docker Composition**: All services run as containers

### Known Constraints

1. **Pipecat Fork**: Using local fork, not standard package - may diverge from upstream
2. **Turkish-Only**: Current models are Turkish-specific
3. **OpenSIPS Coupling**: Tightly coupled to OpenSIPS for telephony
4. **Port Ranges**: Fixed RTP port range (35000-35500)
5. **Monolithic Deployment**: All services must run together

## Modernization Requirements Analysis

### Twilio Integration Pattern (from examples)

Based on `pipecat/examples/twilio-chatbot/`:
- Uses FastAPI WebSocket endpoint
- TwilioFrameSerializer for audio handling
- Simplified bot pattern with single pipeline
- 8kHz audio sample rate for telephony

### Required Changes for Modernization

#### 1. Multi-Transport Support
- Add `src/transports/twilio_transport.py` alongside OpenSIPS
- Implement transport factory pattern for runtime selection
- Support both SIP (OpenSIPS) and WebSocket (Twilio) transports

#### 2. Multi-Provider AI Services
- Add `src/services/ollama_websocket.py` for Ollama LLM
- Add `src/services/faster_whisper.py` for Faster-whisper STT
- Implement service factory pattern for provider selection

#### 3. GCP Deployment Structure
- Create Kubernetes manifests for GKE deployment
- Cloud Run configurations for serverless option
- Use Cloud Load Balancer for traffic distribution
- Cloud Storage for model persistence

#### 4. Configuration Updates
- Multi-provider configuration in INI file
- Environment-based provider selection
- Cloud-native secret management

## Migration Path to Cloud Architecture

### Phase 1: Add Provider Support (Local)
1. Implement Twilio transport alongside OpenSIPS
2. Add Ollama service integration
3. Add Faster-whisper service integration
4. Test multi-provider switching locally

### Phase 2: Containerization for Cloud
1. Create separate Docker images for each service
2. Implement health checks and readiness probes
3. Add Cloud Build configurations
4. Setup Artifact Registry

### Phase 3: GCP Deployment
1. Create GKE cluster configuration
2. Deploy services to GKE with autoscaling
3. Setup Cloud Load Balancer
4. Implement Cloud CDN for static assets

### Phase 4: Production Readiness
1. Add monitoring with Cloud Operations
2. Implement distributed tracing
3. Setup CI/CD with Cloud Build
4. Add backup and disaster recovery

## Development and Deployment

### Current Local Development

```bash
# Start all services
./startup.ps1  # Windows PowerShell

# Or with Docker Compose
docker-compose -f docker-compose.dev.yml up

# Monitor services
./monitor.ps1
```

### Environment Variables
- Configuration via `cfg/opensips-ai-voice-connector.ini`
- Docker environment in `docker-compose.dev.yml`
- No centralized secret management

## Testing Reality

### Current Test Coverage
- Unit Tests: Basic coverage in `tests/unit/`
- Integration Tests: Minimal
- E2E Tests: Manual testing with SIP clients
- Interruption Tests: `test_interruption.py`

### Testing Gaps
- No Twilio integration tests
- No cloud deployment tests
- No multi-provider switching tests
- No load testing

## Appendix - Useful Commands and Scripts

### Frequently Used Commands

```bash
# Local development
docker-compose up -d               # Start services
docker-compose logs -f             # View logs
docker-compose restart <service>   # Restart service

# Testing
python test_interruption.py        # Test barge-in
python -m pytest tests/            # Run unit tests

# Monitoring
./monitor.ps1                      # System monitor (Windows)
```

### Configuration Files
- `cfg/opensips-ai-voice-connector.ini` - Main configuration
- `cfg/opensips.cfg` - OpenSIPS configuration
- `docker-compose.dev.yml` - Docker services

### Port Mappings
- 5060: OpenSIPS SIP
- 8088-8089: Main application
- 35000-35500: RTP audio streams
- 2700: Vosk STT
- 8000: Piper TTS
- 8765: Llama LLM

## Next Steps for Modernization

1. **Immediate**: Create PRD for architecture modernization
2. **Short-term**: Implement multi-provider support locally
3. **Medium-term**: Containerize for cloud deployment
4. **Long-term**: Full GCP production deployment

This document will be updated as the modernization progresses.