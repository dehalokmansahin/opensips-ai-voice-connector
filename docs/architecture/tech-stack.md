# Tech Stack

This section defines the DEFINITIVE technology selections for the entire project. All implementation decisions must reference these choices.

### Cloud Infrastructure

- **Provider:** Hybrid (On-premise primary, Cloud optional)
- **Key Services:** Docker orchestration, Redis clustering, PostgreSQL, GPU compute nodes
- **Deployment Regions:** On-premise banking data centers, optional AWS/Azure regions for non-sensitive workloads

### Technology Stack Table

| Category | Technology | Version | Purpose | Rationale |
|----------|------------|---------|---------|-----------|
| **Language** | Python | 3.11.7 | Primary development language | Excellent AI/ML ecosystem, Pipecat compatibility, team expertise |
| **Runtime** | Python | 3.11.7 | Application runtime | Stable LTS version, optimal AI library support |
| **Framework** | FastAPI | 0.104.1 | gRPC service framework | High performance, async support, excellent gRPC integration |
| **Orchestrator** | Pipecat | Latest | Audio pipeline orchestration | Purpose-built for real-time audio AI pipelines |
| **Communication** | gRPC | 1.60.0 | Inter-service communication | Type safety, performance, streaming support |
| **SIP Proxy** | OpenSIPS | 3.4.x | SIP signaling and routing | Industry standard, proven banking deployments |
| **Audio Processing** | PyAudio | 0.2.13 | Audio I/O handling | Low-latency audio streaming |
| **VAD** | Silero VAD | Latest | Voice activity detection | Optimal accuracy/speed tradeoff |
| **ASR Local** | VOSK | 0.3.45 | CPU-based speech recognition | Cost-effective, offline capability |
| **ASR Cloud** | Faster-Whisper | 0.10.0 | GPU-based speech recognition | Higher accuracy for complex queries |
| **LLM Local** | LLaMA.cpp | Latest | On-premise language model | Privacy compliance, cost control |
| **LLM Cloud** | OpenAI API | GPT-4o | Cloud language model | Superior reasoning capabilities |
| **TTS Local** | Piper | 1.2.0 | CPU-based speech synthesis | Offline capability, consistent quality |
| **TTS Cloud** | ElevenLabs API | Latest | Cloud speech synthesis | Premium voice quality |
| **Database** | PostgreSQL | 15.5 | Session and configuration data | ACID compliance, banking standards |
| **Cache** | Redis | 7.2.3 | Session context and caching | High-performance, conversation state |
| **Monitoring** | Prometheus | 2.48.0 | Metrics collection | Industry standard, excellent alerting |
| **Logging** | Structured logging | Python stdlib | Application logging | JSON format, correlation IDs |
| **Containerization** | Docker | 24.0.7 | Application packaging | Consistent deployment across environments |
| **Orchestration** | Docker Compose | 2.23.0 | Local development | Simple multi-service orchestration |
| **Production Orchestration** | Kubernetes | 1.28.x | Production deployment | Scalability, high availability |
| **Testing** | pytest | 7.4.3 | Unit and integration testing | Comprehensive testing framework |
| **API Documentation** | gRPC reflection | Built-in | Service discovery | Dynamic API documentation |
| **Security** | TLS 1.3 | Latest | Transport encryption | Banking security standards |
