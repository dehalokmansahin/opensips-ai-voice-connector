# Technical Assumptions

### Repository Structure: Monorepo
Maintain the existing monorepo structure while restructuring services for IVR testing focus.

### Service Architecture
**Microservices within Monorepo** - Simple transformation for IVR testing:
1. **ASR Service** (port 50051) - Existing Vosk integration for IVR response transcription
2. **TTS Service** (port 50053) - Existing Piper integration for sending prompts to IVR
3. **Intent Recognition Service** (port 50054) - Turkish BERT for basic response validation
4. **Test Controller** (port 8080) - Simple test execution and OpenSIPS call management
5. **OpenSIPS** - Modified for outbound SIP calls to target IVR systems

### Testing Requirements
**Unit + Integration + E2E** - Comprehensive testing including unit tests for individual services, integration tests for call flows, end-to-end IVR testing validation, and web interface automation testing.

### Additional Technical Assumptions and Requests

**Languages & Frameworks:**
- **Python 3.10+** for all services (ASR, TTS, Intent Recognition, Test Controller)
- **FastAPI** for simple web interface and REST APIs
- **gRPC/protobuf** for inter-service communication
- **OpenSIPS** for SIP call management and outbound calling
- **Docker & Docker Compose** for containerized deployment

**AI/ML Stack:**
- **Existing Pipecat ASR/TTS** infrastructure for audio processing
- **Turkish BERT** (dbmdz/bert-base-turkish-uncased) for intent recognition
- **Transformers library** for BERT model integration

**Database & Storage:**
- **SQLite** for simple test results and configuration storage
- **File storage** for call recordings and logs

**Telephony Integration:**
- **OpenSIPS** modified for outbound SIP call initiation
- **RTP/PCMU** audio handling for IVR interaction
- **SIP MI (Management Interface)** for call control

**Deployment & DevOps:**
- **Docker containerization** with service-specific containers
- **Docker Compose** for local development and testing
- **Environment-based configuration** for different deployment targets
- **CI/CD pipeline** integration for automated testing
