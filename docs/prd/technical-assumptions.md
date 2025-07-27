# Technical Assumptions

### Repository Structure: **Monorepo**

### Service Architecture
**Microservices within Monorepo** - Separate services for AI Voice Connector, OpenSIPS proxy, and pipeline components while maintaining unified codebase management.

### Testing Requirements  
**Unit + Integration** - Unit tests for individual pipeline components, integration tests for end-to-end audio flow, and real-time latency validation.

### Additional Technical Assumptions and Requests

**Languages & Frameworks:**
- **Python** for Pipecat pipeline and AI components (ASR, LLM, TTS)
- **OpenSIPS configuration** for SIP proxy and routing
- **Docker containerization** for deployment consistency
- **gRPC** for inter-service communication and API interfaces
- **WebRTC/SIP protocols** for real-time audio transport

**AI/ML Stack:**
- **Pipecat** as core pipeline orchestrator  
- **Silero VAD** for speech detection
- **VOSK/Faster-Whisper** for ASR flexibility
- **LLaMA (local) / OpenAI GPT-4o (cloud)** for LLM options
- **Piper (local) / ElevenLabs (cloud)** for TTS options

**Infrastructure:**
- **GPU support** required for LLM inference and potentially ASR
- **Real-time processing** capabilities with <700ms total latency
- **Session management** for conversation context
- **Monitoring & logging** with structured logging and metrics

**Deployment Targets:**
- **On-premise deployment** for security/compliance requirements
- **Cloud deployment option** for scalability
- **Docker orchestration** (Docker Compose or Kubernetes)
