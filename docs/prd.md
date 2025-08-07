# OpenSIPS AI Voice Connector - Architecture Modernization PRD

## Intro Project Analysis and Context

### Existing Project Overview

#### Analysis Source
- IDE-based fresh analysis with brownfield architecture document created at: `docs/brownfield-architecture.md`

#### Current Project State
The OpenSIPS AI Voice Connector is a real-time AI voice processing pipeline that provides natural conversation experiences through a VAD → STT → LLM → TTS pipeline with barge-in interruption support. Currently deployed as a monolithic Docker Compose application using OpenSIPS for SIP telephony, with containerized AI services (Vosk for STT, Llama 3.2 for LLM, Piper for TTS). The system follows a simplified architecture pattern inspired by Twilio/Telnyx implementations.

### Available Documentation Analysis

#### Available Documentation
- [x] Tech Stack Documentation (brownfield-architecture.md)
- [x] Source Tree/Architecture (brownfield-architecture.md)
- [ ] Coding Standards (patterns observed in code)
- [x] API Documentation (WebSocket interfaces documented)
- [x] External API Documentation (service integrations)
- [ ] UX/UI Guidelines (N/A - voice-only interface)
- [x] Technical Debt Documentation (constraints identified)
- [x] Docker deployment documentation
- [x] Configuration documentation

### Enhancement Scope Definition

#### Enhancement Type
- [x] Technology Stack Upgrade
- [x] Integration with New Systems
- [x] Major Feature Modification

#### Enhancement Description
Architecture modernization to support Google Cloud Platform deployment with multi-provider telephony (adding Twilio alongside OpenSIPS), multi-provider LLM support (adding Ollama alongside Llama), and enhanced STT capabilities (adding Faster-whisper alongside Vosk).

#### Impact Assessment
- [x] Major Impact (architectural changes required)

### Goals and Background Context

#### Goals
- Enable cloud-native deployment on Google Cloud Platform (GKE/Cloud Run)
- Support Twilio telephony for broader reach and reliability
- Add Ollama integration for flexible local LLM deployment
- Integrate Faster-whisper for improved STT accuracy and performance
- Maintain backward compatibility with existing OpenSIPS deployment
- Create provider-agnostic architecture for future extensibility

#### Background Context
The current system is tightly coupled to OpenSIPS for telephony and specific AI service implementations. To scale and reach broader markets, the system needs cloud deployment capabilities and support for industry-standard telephony providers like Twilio. Additionally, supporting multiple AI providers (Ollama for LLMs, Faster-whisper for STT) will provide flexibility in deployment scenarios and performance optimization. This modernization will transform the system from a monolithic local deployment to a cloud-native, multi-provider architecture while maintaining all existing functionality.

### Change Log

| Change | Date | Version | Description | Author |
|--------|------|---------|-------------|---------|
| Initial | 2025-01-07 | 1.0 | Created Architecture Modernization PRD | PM |

## Requirements

### Functional

- **FR1**: The system shall support both OpenSIPS and Twilio as telephony providers, selectable via configuration
- **FR2**: The system shall integrate with Ollama for LLM services alongside existing Llama WebSocket service
- **FR3**: The system shall support Faster-whisper for STT alongside existing Vosk service
- **FR4**: The system shall provide a transport factory pattern to dynamically select telephony provider at runtime
- **FR5**: The system shall provide a service factory pattern to dynamically select AI providers at runtime
- **FR6**: The system shall support deployment on Google Kubernetes Engine (GKE)
- **FR7**: The system shall support deployment on Cloud Run for serverless scenarios
- **FR8**: The system shall maintain all existing barge-in interruption capabilities across all providers
- **FR9**: The system shall support provider-specific configuration via environment variables and INI files
- **FR10**: The system shall provide health checks and readiness probes for cloud deployment

### Non Functional

- **NFR1**: The system shall maintain existing performance targets (≤1.5s round-trip, ≤300ms interruption response)
- **NFR2**: The system shall support horizontal scaling in GKE with autoscaling policies
- **NFR3**: The system shall maintain backward compatibility with existing OpenSIPS deployments
- **NFR4**: The system shall support 8kHz audio for Twilio telephony and existing sample rates for OpenSIPS
- **NFR5**: The system shall use Cloud-native logging and monitoring (Cloud Operations)
- **NFR6**: The system shall support zero-downtime deployments using rolling updates
- **NFR7**: The system shall maintain existing Turkish language support across all providers
- **NFR8**: The system shall use Cloud Secrets Manager for sensitive configuration

### Compatibility Requirements

- **CR1**: Existing OpenSIPS configuration and deployment must continue to work without modification
- **CR2**: Existing WebSocket interfaces for AI services must remain compatible
- **CR3**: Existing configuration file structure (INI format) must be maintained with extensions
- **CR4**: Existing Docker Compose development workflow must continue to function

## Technical Constraints and Integration Requirements

### Existing Technology Stack
**Languages**: Python 3.11+ (asyncio-based)
**Frameworks**: Pipecat (local fork), FastAPI (for Twilio integration)
**Database**: None (stateless design)
**Infrastructure**: Docker Compose, OpenSIPS 3.6
**External Dependencies**: Vosk (STT), Llama 3.2 (LLM), Piper (TTS)

### Integration Approach
**Database Integration Strategy**: N/A - Maintain stateless design
**API Integration Strategy**: Add FastAPI endpoints for Twilio while maintaining OpenSIPS datagram interfaces
**Frontend Integration Strategy**: N/A - Voice-only interface
**Testing Integration Strategy**: Add provider-specific test suites, maintain existing test structure

### Code Organization and Standards
**File Structure Approach**: Add provider-specific modules in existing service/transport directories
**Naming Conventions**: Follow existing pattern - provider_type.py (e.g., twilio_transport.py)
**Coding Standards**: Maintain existing async/await patterns, use factory patterns for providers
**Documentation Standards**: Update existing docs, add provider-specific configuration guides

### Deployment and Operations
**Build Process Integration**: Multi-stage Docker builds, separate images per service
**Deployment Strategy**: Kubernetes manifests for GKE, Cloud Run service definitions
**Monitoring and Logging**: Integrate with Cloud Operations, maintain existing logging
**Configuration Management**: Environment-based with Cloud Secrets Manager integration

### Risk Assessment and Mitigation
**Technical Risks**: Pipecat fork divergence, audio codec compatibility across providers
**Integration Risks**: WebSocket connection stability in cloud, RTP port management in Kubernetes
**Deployment Risks**: Stateful audio sessions in stateless cloud environments
**Mitigation Strategies**: Maintain provider abstraction layers, implement circuit breakers, use session affinity in load balancers

## Epic and Story Structure

### Epic Approach
**Epic Structure Decision**: Single comprehensive epic for architecture modernization with phased rollout. This approach ensures all architectural changes are coordinated while maintaining system stability throughout the migration.

## Epic 1: Cloud-Native Multi-Provider Architecture

**Epic Goal**: Transform the OpenSIPS AI Voice Connector into a cloud-native, multi-provider system that supports GCP deployment, Twilio telephony, Ollama LLMs, and Faster-whisper STT while maintaining full backward compatibility.

**Integration Requirements**: All changes must be additive, preserving existing OpenSIPS functionality. Provider selection must be configuration-driven. Cloud deployment must be optional.

### Story 1.1: Multi-Provider Transport Architecture

As a system architect,
I want to implement a transport factory pattern,
so that the system can dynamically select between OpenSIPS and Twilio telephony providers.

#### Acceptance Criteria
1. Create abstract base transport class defining common interface
2. Refactor existing OpenSIPS transport to implement base class
3. Implement Twilio transport following pipecat/examples/twilio-chatbot pattern
4. Create transport factory that selects provider based on configuration
5. Add configuration schema for multi-provider transport settings

#### Integration Verification
- IV1: Existing OpenSIPS calls continue to work with no configuration changes
- IV2: Transport factory correctly instantiates OpenSIPS transport when configured
- IV3: No performance degradation in existing OpenSIPS call handling

### Story 1.2: Twilio Telephony Integration

As a telephony user,
I want to make calls through Twilio,
so that I can use cloud-based telephony without SIP infrastructure.

#### Acceptance Criteria
1. Implement TwilioFrameSerializer for audio handling
2. Create FastAPI WebSocket endpoint for Twilio Media Streams
3. Handle Twilio-specific audio format (8kHz PCMU)
4. Implement Twilio call control (answer, hangup, transfer)
5. Add Twilio configuration section to INI file

#### Integration Verification
- IV1: System can handle both Twilio and OpenSIPS calls simultaneously
- IV2: Audio pipeline processes both 8kHz (Twilio) and higher sample rates (OpenSIPS)
- IV3: Barge-in interruption works correctly with Twilio calls

### Story 1.3: Ollama LLM Service Integration

As an AI developer,
I want to use Ollama for LLM services,
so that I can deploy various open-source models locally or in cloud.

#### Acceptance Criteria
1. Create OllamaLLMService implementing Pipecat LLM interface
2. Support Ollama REST API for model management
3. Implement streaming responses compatible with pipeline
4. Add Ollama model configuration (model name, parameters)
5. Create service factory for LLM provider selection

#### Integration Verification
- IV1: Existing Llama WebSocket service continues to function
- IV2: Service factory correctly selects provider based on configuration
- IV3: Pipeline maintains same latency targets with Ollama

### Story 1.4: Faster-whisper STT Integration

As a voice application user,
I want improved speech recognition accuracy,
so that the system better understands my speech input.

#### Acceptance Criteria
1. Create FasterWhisperSTTService implementing Pipecat STT interface
2. Support local Faster-whisper model loading
3. Implement audio buffering for Faster-whisper processing
4. Add language and model size configuration
5. Extend service factory for STT provider selection

#### Integration Verification
- IV1: Vosk STT service remains functional for existing deployments
- IV2: Audio pipeline handles both streaming (Vosk) and buffered (Faster-whisper) STT
- IV3: VAD and interruption detection work with both STT providers

### Story 1.5: Cloud-Ready Containerization

As a DevOps engineer,
I want properly structured containers for cloud deployment,
so that services can be deployed independently in Kubernetes.

#### Acceptance Criteria
1. Create multi-stage Dockerfile for main application
2. Separate Dockerfile for each AI service (Ollama, Faster-whisper)
3. Implement health check endpoints for each service
4. Add readiness and liveness probes
5. Create docker-compose.cloud.yml for cloud-compatible local testing

#### Integration Verification
- IV1: Existing docker-compose.dev.yml continues to work
- IV2: All services start correctly with new container structure
- IV3: Health checks accurately reflect service status

### Story 1.6: GKE Deployment Configuration

As a cloud architect,
I want Kubernetes manifests for GKE deployment,
so that the system can run in Google Kubernetes Engine.

#### Acceptance Criteria
1. Create Kubernetes deployments for each service
2. Configure services and ingress for external access
3. Implement ConfigMaps for configuration management
4. Setup Secrets for sensitive data (API keys)
5. Create HorizontalPodAutoscaler for main application

#### Integration Verification
- IV1: All services communicate correctly in Kubernetes networking
- IV2: RTP ports properly exposed for OpenSIPS in Kubernetes
- IV3: WebSocket connections stable through ingress

### Story 1.7: Cloud Run Serverless Deployment

As a platform engineer,
I want Cloud Run deployment option,
so that the system can run in a serverless environment for Twilio-only deployments.

#### Acceptance Criteria
1. Create Cloud Run service definitions
2. Implement request-based scaling configuration
3. Setup Cloud Build for automated deployment
4. Configure environment variables for Cloud Run
5. Document limitations (no OpenSIPS in serverless)

#### Integration Verification
- IV1: Twilio calls work correctly in Cloud Run
- IV2: Cold start times within acceptable limits (<5 seconds)
- IV3: WebSocket connections maintain stability

### Story 1.8: Configuration Management Enhancement

As a system administrator,
I want unified configuration for multi-provider setup,
so that I can easily manage provider selection and settings.

#### Acceptance Criteria
1. Extend INI configuration schema for multiple providers
2. Implement environment variable overrides for cloud deployment
3. Create provider selection logic based on configuration
4. Add configuration validation on startup
5. Document all configuration options

#### Integration Verification
- IV1: Existing single-provider configurations continue to work
- IV2: Provider selection correctly interprets configuration
- IV3: Environment variables properly override INI settings

### Story 1.9: Monitoring and Observability

As a operations engineer,
I want cloud-native monitoring and logging,
so that I can track system health and debug issues in production.

#### Acceptance Criteria
1. Integrate with Google Cloud Operations (formerly Stackdriver)
2. Implement structured logging with correlation IDs
3. Add custom metrics for call quality and latency
4. Create dashboards for system monitoring
5. Setup alerts for critical issues

#### Integration Verification
- IV1: Existing console logging remains functional
- IV2: Metrics accurately reflect system performance
- IV3: Log aggregation works across all services

### Story 1.10: Integration Testing and Documentation

As a developer,
I want comprehensive tests and documentation,
so that I can understand and verify the multi-provider system.

#### Acceptance Criteria
1. Create integration tests for each provider combination
2. Add load testing for cloud deployment
3. Update README with cloud deployment instructions
4. Create provider-specific configuration guides
5. Document migration path from monolithic to cloud

#### Integration Verification
- IV1: All existing tests continue to pass
- IV2: New tests cover provider switching scenarios
- IV3: Documentation accurately reflects both legacy and new deployments

## Success Metrics

- Successful deployment on GKE with autoscaling
- Successful Twilio call handling with <1.5s latency
- Ollama LLM integration with multiple model support
- Faster-whisper achieving >95% accuracy for supported languages
- Zero downtime migration from existing deployment
- Maintain all existing performance targets

## Timeline Estimate

- **Phase 1** (Weeks 1-2): Multi-provider architecture (Stories 1.1-1.4)
- **Phase 2** (Week 3): Containerization and cloud preparation (Story 1.5)
- **Phase 3** (Week 4): GKE and Cloud Run deployment (Stories 1.6-1.7)
- **Phase 4** (Week 5): Configuration and monitoring (Stories 1.8-1.9)
- **Phase 5** (Week 6): Testing and documentation (Story 1.10)

Total estimated effort: 6 weeks for complete modernization