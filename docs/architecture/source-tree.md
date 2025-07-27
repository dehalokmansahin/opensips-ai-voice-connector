# Source Tree

```plaintext
opensips-ai-voice-connector/
├── services/                           # Microservices
│   ├── ai-voice-connector/             # Main orchestrator service
│   │   ├── src/
│   │   │   ├── main.py                 # FastAPI + gRPC server
│   │   │   ├── audio/                  # Audio processing
│   │   │   │   ├── codecs.py           # PCMU/PCM conversion
│   │   │   │   └── streaming.py        # RTP handling
│   │   │   ├── grpc_services/          # gRPC service implementations
│   │   │   └── opensips/               # OpenSIPS integration
│   │   ├── proto/                      # gRPC protocol definitions
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   ├── pipecat-orchestrator/           # Pipecat pipeline manager
│   │   ├── src/
│   │   │   ├── main.py                 # Pipecat application
│   │   │   ├── pipeline/               # Pipeline configuration
│   │   │   ├── providers/              # AI provider adapters
│   │   │   └── interruption/           # Barge-in handling
│   │   └── requirements.txt
│   ├── vad-service/                    # Voice Activity Detection
│   │   ├── src/
│   │   │   ├── main.py                 # gRPC service
│   │   │   ├── silero/                 # Silero VAD integration
│   │   │   └── models/                 # VAD model management
│   │   └── requirements.txt
│   ├── asr-service/                    # Automatic Speech Recognition
│   │   ├── src/
│   │   │   ├── main.py                 # gRPC service
│   │   │   ├── providers/              # VOSK & Faster-Whisper
│   │   │   └── streaming/              # Token streaming
│   │   └── requirements.txt
│   ├── llm-service/                    # Language Model Processing
│   │   ├── src/
│   │   │   ├── main.py                 # gRPC service
│   │   │   ├── providers/              # LLaMA & OpenAI
│   │   │   ├── banking/                # Banking intent handling
│   │   │   └── context/                # Context management
│   │   └── requirements.txt
│   ├── tts-service/                    # Text-to-Speech
│   │   ├── src/
│   │   │   ├── main.py                 # gRPC service
│   │   │   ├── providers/              # Piper & ElevenLabs
│   │   │   └── voices/                 # Voice configuration
│   │   └── requirements.txt
│   ├── session-manager/                # Session lifecycle management
│   │   ├── src/
│   │   │   ├── main.py                 # gRPC service
│   │   │   ├── database/               # PostgreSQL models
│   │   │   ├── cache/                  # Redis operations
│   │   │   └── models/                 # Data models
│   │   └── requirements.txt
│   ├── context-store/                  # Conversation context
│   │   ├── src/
│   │   │   ├── main.py                 # gRPC service
│   │   │   ├── redis/                  # Redis operations
│   │   │   └── cleanup/                # TTL management
│   │   └── requirements.txt
│   └── banking-service/                # Banking system integration
│       ├── src/
│       │   ├── main.py                 # gRPC service
│       │   ├── apis/                   # Banking API clients
│       │   ├── auth/                   # Customer authentication
│       │   └── intents/                # Banking intent handlers
│       └── requirements.txt
├── shared/                             # Shared libraries
│   ├── proto/                          # Common gRPC definitions
│   ├── models/                         # Shared data models
│   ├── utils/                          # Common utilities
│   └── testing/                        # Test utilities
├── infrastructure/                     # Deployment and infrastructure
│   ├── docker/                         # Docker configurations
│   │   ├── docker-compose.dev.yml      # Development environment
│   │   ├── docker-compose.prod.yml     # Production environment
│   │   └── Dockerfile.base             # Base Python image
│   ├── opensips/                       # OpenSIPS configuration
│   │   ├── opensips.cfg                # Main configuration
│   │   └── scripts/                    # SIP routing scripts
│   ├── kubernetes/                     # K8s manifests
│   │   ├── services/                   # Service definitions
│   │   ├── deployments/                # Deployment configs
│   │   └── monitoring/                 # Prometheus/Grafana
│   └── monitoring/                     # Observability
│       ├── prometheus/                 # Metrics collection
│       ├── grafana/                    # Dashboards
│       └── logging/                    # Structured logging
├── scripts/                            # Development and deployment scripts
│   ├── dev-setup.sh                    # Development environment setup
│   ├── proto-gen.sh                    # gRPC code generation
│   ├── test-all.sh                     # Run all tests
│   └── deploy.sh                       # Deployment script
├── docs/                               # Documentation
│   ├── architecture.md                 # This document
│   ├── prd.md                          # Product requirements
│   ├── api/                            # API documentation
│   └── deployment/                     # Deployment guides
├── tests/                              # Integration and system tests
│   ├── integration/                    # Service integration tests
│   ├── performance/                    # Load and latency tests
│   └── e2e/                            # End-to-end scenarios
├── .github/                            # CI/CD workflows
│   └── workflows/                      # GitHub Actions
├── pyproject.toml                      # Python project configuration
├── docker-compose.yml                  # Default development setup
└── README.md                           # Project overview
```
