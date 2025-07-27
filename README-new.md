# 🎯 OpenSIPS AI Voice Connector

**Banking IVR Voice Assistant with Pipecat AI Pipeline**

A microservices-based real-time voice processing system designed for banking environments. Features VAD → ASR → LLM → TTS pipeline with sub-700ms latency targets and comprehensive banking security controls.

## 🏗️ Architecture

```
📞 SIP Call → OpenSIPS → AI Voice Connector → gRPC Services
                                ↓
                    VAD → ASR → LLM → TTS Services
                                ↓
                      Banking Service Integration
```

### Microservices Architecture
- **AI Voice Connector**: Main orchestrator (FastAPI + gRPC)
- **VAD Service**: Voice Activity Detection (Silero)
- **ASR Service**: Speech Recognition (VOSK/Faster-Whisper)
- **LLM Service**: Language Model (LLaMA/OpenAI)
- **TTS Service**: Text-to-Speech (Piper/ElevenLabs)
- **Session Manager**: Call lifecycle management
- **Context Store**: Conversation memory (Redis)
- **Banking Service**: Banking system integration

## 🚀 Quick Start

### Prerequisites
- Docker Desktop 24.0.7+
- Python 3.11.7+
- Git

### 1. Clone & Setup
```bash
git clone <repository>
cd opensips-ai-voice-connector
chmod +x scripts/*.sh
./scripts/dev-setup.sh
```

### 2. Start Development Environment
```bash
docker-compose -f infrastructure/docker/docker-compose.dev.yml up -d
```

### 3. Verify Services
```bash
docker-compose -f infrastructure/docker/docker-compose.dev.yml ps
```

## 🐳 Services & Ports

| Service | HTTP Port | gRPC Port | Description |
|---------|-----------|-----------|-------------|
| **AI Voice Connector** | 8080 | 50051 | Main orchestrator service |
| **OpenSIPS** | 5060 | - | SIP Proxy Server |
| **VAD Service** | - | 50052 | Voice Activity Detection |
| **ASR Service** | - | 50053 | Speech Recognition |
| **LLM Service** | - | 50054 | Language Model Processing |
| **TTS Service** | - | 50055 | Text-to-Speech Synthesis |
| **Session Manager** | - | 50056 | Call lifecycle management |
| **Context Store** | - | 50057 | Conversation context |
| **Banking Service** | - | 50058 | Banking system integration |
| **PostgreSQL** | 5432 | - | Database |
| **Redis** | 6379 | - | Cache & Context Store |
| **Prometheus** | 9090 | - | Metrics & Monitoring |

## 🛠️ Development

### Project Structure
```
opensips-ai-voice-connector/
├── services/                           # Microservices
│   ├── ai-voice-connector/             # Main orchestrator
│   ├── vad-service/                    # Voice Activity Detection
│   ├── asr-service/                    # Speech Recognition
│   ├── llm-service/                    # Language Model
│   ├── tts-service/                    # Text-to-Speech
│   ├── session-manager/                # Session management
│   ├── context-store/                  # Context storage
│   └── banking-service/                # Banking integration
├── shared/                             # Shared libraries
│   ├── proto/                          # gRPC definitions
│   ├── models/                         # Data models
│   └── utils/                          # Common utilities
├── infrastructure/                     # Deployment configs
│   ├── docker/                         # Docker configurations
│   ├── kubernetes/                     # K8s manifests
│   └── monitoring/                     # Observability
├── scripts/                            # Development scripts
├── tests/                              # Test suites
└── docs/                               # Documentation
```

### Development Commands

```bash
# Setup development environment
./scripts/dev-setup.sh

# Generate gRPC code
./scripts/proto-gen.sh

# Run all tests
./scripts/test-all.sh

# Start all services
docker-compose -f infrastructure/docker/docker-compose.dev.yml up -d

# View logs
docker-compose -f infrastructure/docker/docker-compose.dev.yml logs -f

# Stop all services
docker-compose -f infrastructure/docker/docker-compose.dev.yml down
```

### Code Quality
- **Formatting**: Black
- **Linting**: Ruff
- **Type Checking**: MyPy
- **Testing**: Pytest with asyncio support

## 🎯 Performance Targets

| Component | Target | Current Implementation |
|-----------|--------|----------------------|
| **VAD Response** | ≤ 20ms | Silero VAD |
| **ASR Latency** | ≤ 250ms | VOSK (local) / Faster-Whisper (cloud) |
| **LLM Processing** | ≤ 300ms | LLaMA (local) / OpenAI (cloud) |
| **TTS Generation** | ≤ 200ms | Piper (local) / ElevenLabs (cloud) |
| **Total Round-Trip** | ≤ 700ms | End-to-end pipeline |

## 🏦 Banking Features

### MVP: Card Delivery Status Inquiry
- Natural language understanding for card delivery questions
- Customer authentication integration
- Banking API mock integration
- Compliance logging and audit trails
- Banking-appropriate conversation boundaries

### Security & Compliance
- PII protection in logs
- Session security controls
- Banking-grade authentication
- Audit logging for compliance
- Conversation timeout policies

## 🔧 Configuration

### Environment Files
- `.env.development` - Development settings
- `.env.production` - Production settings

### Key Configuration Areas
- Service discovery and networking
- AI model configurations
- Database connections
- Logging and monitoring
- Security and authentication

## 🧪 Testing

### Test Categories
- **Unit Tests**: Service-level testing
- **Integration Tests**: Inter-service communication
- **Performance Tests**: Latency and throughput
- **E2E Tests**: Full conversation scenarios

### Running Tests
```bash
# All tests
./scripts/test-all.sh

# Unit tests only
pytest tests/unit/

# Integration tests
pytest tests/integration/

# Performance tests
RUN_PERFORMANCE_TESTS=true ./scripts/test-all.sh
```

## 📊 Monitoring

### Available Metrics
- Service health and availability
- Request latency and throughput
- AI model performance
- Resource utilization
- Banking transaction metrics

### Monitoring Stack
- **Prometheus**: Metrics collection
- **Grafana**: Dashboards (future)
- **Structured Logging**: JSON-formatted logs
- **Health Checks**: Service availability monitoring

## 🚀 Deployment

### Development
```bash
docker-compose -f infrastructure/docker/docker-compose.dev.yml up -d
```

### Production
```bash
# Build production images
docker-compose -f infrastructure/docker/docker-compose.prod.yml build

# Deploy with Kubernetes (future)
kubectl apply -f infrastructure/kubernetes/
```

## 📖 Documentation

- [Product Requirements](docs/prd/)
- [Architecture Documentation](docs/architecture/)
- [API Documentation](docs/api/)
- [Deployment Guide](docs/deployment/)

## 📄 License

This project is licensed under the MIT License.

---

**🎊 Ready for banking voice AI! 📞**