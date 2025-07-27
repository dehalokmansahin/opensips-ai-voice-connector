# OpenSIPS AI Voice Connector Product Requirements Document (PRD)

## Goals and Background Context

### Goals

- Develop a real-time, low-latency voice assistant that enhances banking IVR user experience using microservices architecture
- Enable natural, bidirectional spoken interactions over standard SIP/RTP infrastructure with gRPC-based service communication
- Integrate seamlessly with existing banking call center systems through containerized deployment
- Provide sub-700ms end-to-end response latency for real-time conversational flow
- Support standard telephony audio formats (PCMU/8000) without requiring specialized hardware
- Deliver reliable barge-in capabilities for natural conversation interruption handling
- Maintain high availability and fault tolerance through independent microservices deployment
- Enable scalable deployment options (on-premise and cloud) via Docker orchestration

### Background Context

Banking IVR systems traditionally rely on menu-driven interactions that frustrate users with lengthy navigation paths and limited flexibility. This project addresses the need for conversational AI that can understand natural speech and respond intelligently while maintaining the reliability and security standards required for financial services.

The solution has evolved from a monolithic Pipecat-based approach to a modern microservices architecture where each AI component (ASR, LLM, TTS) operates as an independent gRPC service. The core application orchestrates these services through a robust service discovery and management layer, with OpenSIPS handling SIP/RTP telephony integration. This architecture enables independent scaling, deployment, and maintenance of AI components while maintaining the reliability and security standards required for financial services.

### Change Log

| Date | Version | Description | Author |
|------|---------|-------------|---------|
| 2025-07-27 | 1.0 | Initial PRD creation from Project Brief | John (PM) |
| 2025-07-27 | 2.0 | Updated with microservices architecture and current implementation status | John (PM) |

## Requirements

### Functional

**FR1:** The system must process incoming SIP/RTP audio calls through OpenSIPS integration with core application orchestration
**FR2:** The system must convert PCMU/8000 audio to PCM 16-bit, 16kHz for internal processing via audio transport layer
**FR3:** The system must detect speech segments using VAD (Silero) integrated through native pipecat audio.vad components
**FR4:** The system must convert speech to text using dedicated ASR gRPC service (Native Vosk integration, with future Faster-Whisper cloud option)
**FR5:** The system must process user queries through dedicated LLM gRPC service (LLaMA with llama-cpp-python, with future OpenAI cloud option)
**FR6:** The system must generate voice responses using dedicated TTS gRPC service (Piper with native integration, with future ElevenLabs cloud option)
**FR7:** The system must support real-time barge-in/interruption capabilities using pipecat audio.interruptions and pipeline orchestration
**FR8:** The system must handle "Card Delivery Status Inquiry" as the MVP pilot scenario
**FR9:** The system must maintain session context and conversation memory across microservices
**FR10:** The system must encode TTS output back to PCMU/8000 for SIP/RTP transmission
**FR11:** Each microservice (ASR, LLM, TTS) must operate independently with health monitoring and service discovery
**FR12:** The system must support Docker containerization with orchestrated deployment of all services
**FR13:** Services must communicate exclusively via gRPC with proper error handling and retry policies
**FR14:** The system must utilize native pipecat framework components (frames, observers, serializers, audio utilities) for pipeline orchestration and monitoring
**FR15:** Each service must support configurable backend selection (local vs cloud providers) for flexible deployment scenarios (future feature)

### Non Functional

**NFR1:** End-to-end response latency must not exceed 700ms (p95) across all microservices
**NFR2:** TTS service first audio output must be delivered within 200ms
**NFR3:** ASR service first token must be available within 250ms
**NFR4:** LLM service first token response must be generated within 300ms
**NFR5:** The system must handle 20ms RTP packet processing (~160 bytes each) in core application
**NFR6:** Each microservice must maintain independent high availability with health checks and graceful shutdown
**NFR7:** The system must log all pipeline stages with session IDs using structured logging across all services
**NFR8:** The system must support both on-premise and cloud deployment through Docker Compose and Kubernetes
**NFR9:** Services must be horizontally scalable through container orchestration
**NFR10:** gRPC communication must include authentication, timeouts, and circuit breaker patterns
**NFR11:** Service discovery must enable dynamic endpoint resolution and health monitoring

## Technical Assumptions

### Repository Structure: **Monorepo**

### Service Architecture
**Microservices within Monorepo** - Four independent services:
1. **ASR Service** (port 50051) - Native Vosk speech recognition with enhanced service base
2. **LLM Service** (port 50052) - LLaMA processing with llama-cpp-python integration  
3. **TTS Service** (port 50053) - Piper text-to-speech with streaming audio output
4. **Core Application** (port 8080) - OpenSIPS integration, pipeline management, and service orchestration

All services use common BaseService framework with standardized health checks, logging, and configuration management.

### Testing Requirements  
**Unit + Integration** - Unit tests for individual service components, integration tests for gRPC communication, end-to-end audio flow validation, and container orchestration testing.

### Additional Technical Assumptions and Requests

**Languages & Frameworks:**
- **Python 3.10+** for all microservices and core application
- **gRPC/protobuf** for all inter-service communication with health probes
- **Docker & Docker Compose** for container orchestration and deployment
- **FastAPI** for HTTP management interface and health endpoints
- **OpenSIPS configuration** for SIP proxy and routing
- **Native Pipecat Framework** (pipecat/src/pipecat) with selective component usage including:
  - **Frames system** for audio/text/control message passing
  - **Observers** for pipeline monitoring and logging
  - **Serializers** for audio format conversion and transport
  - **Audio utilities** including VAD, interruption strategies, and audio processing
  - **Pipeline orchestration** for managing audio flow and AI component coordination

**AI/ML Stack (Current Implementation):**
- **Native Vosk** for CPU-based ASR processing (primary implementation)
- **llama-cpp-python** for local LLM inference with threading support (primary implementation)
- **Piper TTS** with native library integration for audio synthesis (primary implementation)
- **Silero VAD** integrated through pipecat.services.audio.vad components
- **Native Pipecat Audio Processing** including filters, resamplers, and mixers
- **Service-specific health checks** with model validation

**AI/ML Stack (Future Cloud Options):**
- **Faster-Whisper** cloud integration for enhanced ASR accuracy (future feature)
- **OpenAI GPT-4o** cloud integration for advanced LLM capabilities (future feature)
- **ElevenLabs** cloud integration for premium TTS quality (future feature)
- **Configurable backend selection** per service for hybrid deployment scenarios

**Infrastructure (Current Implementation):**
- **Docker containerization** with multi-stage builds and health checks
- **Service discovery** through Docker networking and service registry
- **Structured logging** with service-specific identifiers and session tracking
- **Configuration management** via environment variables and config files
- **Independent scaling** of each microservice based on load requirements

**Deployment Targets (Implemented):**
- **Development mode** with live code mounting and debug logging
- **Production mode** with optimized containers and security hardening
- **Docker Compose orchestration** with dependency management and health checks
- **Model volume mounting** for efficient AI model management

## Epic List

**Epic 1: Foundation & Core Infrastructure** ✅ **COMPLETED**  
~~Establish project setup, containerization, OpenSIPS configuration, and basic audio pipeline with health monitoring.~~
Established monorepo structure, minimal pipecat extraction, core application architecture, and gRPC service foundations.

**Epic 2: Core AI Pipeline Integration** ✅ **COMPLETED**  
~~Implement VAD, ASR, LLM, and TTS components with Pipecat orchestration for basic voice processing.~~
Implemented independent microservices for ASR (Vosk), LLM (LLaMA), and TTS (Piper) with common service base, health monitoring, and Docker orchestration.

**Epic 3: Real-time Audio Transport & SIP Integration** 🔄 **IN PROGRESS**  
Complete RTP audio handling, PCMU/PCM conversion, full SIP call flow integration, and OpenSIPS refactoring for microservices architecture.

**Epic 4: Banking IVR Features & Optimization** ⏳ **PENDING**  
Implement Card Delivery Status Inquiry MVP scenario, conversation context, performance optimization, and production deployment preparation.

**Epic 5: Cloud AI Integration & Hybrid Deployment** 🚀 **FUTURE**  
Add cloud AI provider support (OpenAI, ElevenLabs, Faster-Whisper) with configurable backend selection and hybrid deployment capabilities.

## Current Implementation Status (Updated July 27, 2025)

### ✅ Completed Components

**Core Architecture:**
- Monorepo structure with clean service separation (`core/`, `services/`, `config/`)
- Native pipecat framework integration (pipecat/src/pipecat) with selective component usage
- gRPC service architecture with common BaseService foundation  
- Docker containerization with development and production modes
- Service discovery and health monitoring infrastructure
- Pipecat-based pipeline orchestration with frames, observers, and audio utilities

**Microservices Implementation:**
- **ASR Service** (enhanced_asr_server.py): Native Vosk integration with streaming recognition, health checks, and service statistics
  - *Future:* Faster-Whisper cloud backend support
- **LLM Service** (enhanced_llm_server.py): LLaMA with llama-cpp-python, conversation context, and streaming generation
  - *Future:* OpenAI GPT-4o cloud backend support  
- **TTS Service** (enhanced_tts_server.py): Piper TTS with streaming audio synthesis and voice management
  - *Future:* ElevenLabs cloud backend support
- **Common Service Base** (service_base.py): Standardized logging, health checks, configuration, and graceful shutdown

**Docker Infrastructure:**
- Production docker-compose.yml with service orchestration and health dependencies
- Development docker-compose.dev.yml with live code mounting
- Individual service Dockerfiles with proper health checks
- Service networking and volume management for model files

**Native Pipecat Integration:**
- **Frame System**: Core audio/text/control message passing using pipecat.frames
- **Audio Processing**: VAD (pipecat.audio.vad.silero), audio filters, and resamplers
- **Pipeline Management**: Pipeline orchestration using pipecat.pipeline components
- **Observers**: Monitoring and logging with pipecat.observers for debugging and analytics
- **Serializers**: Audio format conversion using pipecat.serializers for transport protocols
- **Services Integration**: Leveraging pipecat.services architecture patterns for AI component management

### 🔄 Current Phase: OpenSIPS Integration Refactoring

**Next Steps:**
- Refactor OpenSIPS integration layer to work with new microservices architecture
- Update RTP transport to communicate with gRPC services using pipecat transport components
- Implement conversation pipeline manager with native pipecat pipeline orchestration
- Integrate pipecat observers for comprehensive pipeline monitoring and logging
- Test end-to-end audio flow with pipecat frames and serializers

### ⏳ Remaining Work

**Phase 3:** Complete SIP/RTP integration with microservices
**Phase 4:** Implement banking IVR features and performance optimization
**Phase 5:** Production deployment and testing

## Epic 1: Foundation & Core Infrastructure ✅ COMPLETED

**Epic Goal:** Establish foundational project infrastructure including containerization, basic OpenSIPS configuration, Pipecat setup, and health monitoring while delivering an initial voice pipeline demonstration that validates the core technical stack.

### Story 1.1: Project Setup and Containerization
**As a** developer,  
**I want** a fully containerized development environment with proper dependency management,  
**so that** the team can develop consistently across different machines and deploy reliably.

**Acceptance Criteria:**
1. Docker Compose configuration for development environment with all required services
2. Dockerfile for Python Pipecat application with all AI/ML dependencies
3. Environment variable configuration for different deployment scenarios
4. README with setup instructions and development workflow
5. Git repository structure following monorepo conventions
6. CI/CD pipeline setup for automated testing and building

### Story 1.2: Basic OpenSIPS Configuration
**As a** system administrator,  
**I want** OpenSIPS configured for basic SIP call handling and RTP media relay,  
**so that** incoming calls can be routed to the AI Voice Connector.

**Acceptance Criteria:**
1. OpenSIPS configuration file for SIP proxy functionality
2. Basic call routing to AI Voice Connector endpoint
3. RTP media relay configuration for audio streams
4. SIP registration handling for testing scenarios
5. Basic logging and monitoring of SIP transactions
6. Health check endpoint for OpenSIPS service status

### Story 1.3: Pipecat Core Setup and Health Check
**As a** developer,  
**I want** basic Pipecat pipeline setup with health monitoring,  
**so that** we have a foundation for adding AI components and can verify system status.

**Acceptance Criteria:**
1. Pipecat application initialization with basic configuration
2. Health check HTTP endpoint returning system status
3. Basic logging framework with structured logging
4. Configuration management for different pipeline components
5. Basic audio input/output pipeline (passthrough) for testing
6. Integration with Docker container orchestration

### Story 1.4: gRPC Service Architecture Setup
**As a** system architect,  
**I want** gRPC service definitions and communication patterns established,  
**so that** all inter-service communication follows consistent protocols and interfaces.

**Acceptance Criteria:**
1. gRPC service definitions (.proto files) for core services
2. gRPC server implementation for AI Voice Connector service
3. gRPC client libraries for inter-service communication
4. Authentication and security configuration for gRPC endpoints
5. Error handling and retry policies for gRPC calls
6. Performance monitoring and metrics collection for gRPC services

## Epic 2: Core AI Pipeline Integration

**Epic Goal:** Implement the complete AI pipeline with VAD, ASR, LLM, and TTS components orchestrated by Pipecat, enabling basic voice-to-voice processing with configurable AI backends for both local and cloud deployment options.

### Story 2.1: VAD Integration with Silero
**As a** voice processing system,  
**I want** reliable voice activity detection using Silero VAD,  
**so that** speech segments can be accurately identified and forwarded to ASR processing.

**Acceptance Criteria:**
1. Silero VAD integration with configurable thresholds (speech_prob_threshold, min_speech_duration_ms, min_silence_duration_ms)
2. PCM 16kHz mono audio input processing
3. Speech segment detection and boundary identification
4. VAD processing latency under 20ms per audio chunk
5. Logging of VAD decisions and timing metrics
6. Unit tests for VAD configuration and edge cases

### Story 2.2: ASR Implementation with Dual Backend Support
**As a** voice processing system,  
**I want** speech-to-text conversion with both VOSK and Faster-Whisper options,  
**so that** we can choose between cost-effective CPU processing and high-accuracy GPU processing.

**Acceptance Criteria:**
1. VOSK ASR integration for CPU-based processing
2. Faster-Whisper ASR integration for GPU-based processing
3. Configuration-driven ASR backend selection
4. First token latency under 250ms
5. Streaming token output to LLM component
6. Error handling for ASR failures and empty transcriptions

### Story 2.3: LLM Integration with Dual Provider Support
**As a** conversational AI system,  
**I want** language model processing with both local LLaMA and cloud OpenAI options,  
**so that** we can balance cost, privacy, and capability requirements.

**Acceptance Criteria:**
1. Local LLaMA integration with GPU inference
2. OpenAI GPT-4o integration with streaming via gRPC
3. Configuration-driven LLM provider selection
4. First token response under 300ms
5. Session context management and conversation memory
6. Banking-appropriate response filtering and safety controls

### Story 2.4: TTS Implementation with Dual Backend Support
**As a** voice response system,  
**I want** text-to-speech conversion with both Piper and ElevenLabs options,  
**so that** we can choose between local processing and cloud-quality voice synthesis.

**Acceptance Criteria:**
1. Piper TTS integration for CPU-based synthesis
2. ElevenLabs TTS integration for cloud-based synthesis
3. Configuration-driven TTS backend selection
4. First audio output under 200ms
5. Streaming audio output for reduced latency
6. PCM 22050Hz mono output format

### Story 2.5: End-to-End Pipeline Orchestration
**As a** system integrator,  
**I want** complete Pipecat orchestration of the VAD→ASR→LLM→TTS pipeline,  
**so that** voice input produces coherent voice responses with proper error handling.

**Acceptance Criteria:**
1. Pipecat pipeline configuration linking all AI components
2. Audio flow management from input through all processing stages
3. Error handling and recovery for component failures
4. Session management across pipeline stages
5. Comprehensive logging of pipeline flow and timing
6. Integration tests for complete voice-to-voice processing

## Epic 3: Real-time Audio Transport & SIP Integration

**Epic Goal:** Complete the real-time audio transport layer with full SIP/RTP integration, PCMU/PCM audio conversion, and seamless connection between OpenSIPS and the AI pipeline, enabling end-to-end voice calls with sub-700ms latency.

### Story 3.1: RTP Audio Stream Handling
**As a** telephony system,  
**I want** proper RTP audio stream ingestion and transmission,  
**so that** audio can flow bidirectionally between callers and the AI pipeline.

**Acceptance Criteria:**
1. RTP audio stream reception from OpenSIPS with 20ms packet handling (~160 bytes each)
2. RTP audio stream transmission back to OpenSIPS for caller playback
3. Real-time audio buffering and jitter handling
4. Packet loss detection and basic recovery mechanisms
5. RTP session management and cleanup
6. Monitoring of audio stream quality metrics

### Story 3.2: PCMU/PCM Audio Conversion
**As a** audio processing system,  
**I want** seamless conversion between PCMU/8000 and PCM formats,  
**so that** telephony audio can be processed by AI components and returned to callers.

**Acceptance Criteria:**
1. PCMU/8000 ulaw to PCM 16-bit, 16kHz conversion with <10ms latency
2. PCM 22050Hz mono to PCMU/8000 conversion with <10ms latency
3. Audio resampling and format conversion accuracy
4. Real-time processing without audio artifacts
5. Memory-efficient audio buffer management
6. Quality validation and audio integrity testing

### Story 3.3: AI Voice Connector Integration Layer
**As a** system architect,  
**I want** a comprehensive AI Voice Connector that bridges SIP/RTP and Pipecat,  
**so that** all audio transport, conversion, and AI orchestration work seamlessly together.

**Acceptance Criteria:**
1. AI Voice Connector service managing SIP session lifecycle via gRPC APIs
2. Integration with OpenSIPS for call setup and teardown
3. Audio stream routing between RTP and Pipecat pipeline
4. Session state management across call duration
5. Error handling for network and audio processing failures
6. Configuration management for different deployment scenarios

### Story 3.4: Barge-in and Interruption Handling
**As a** conversation participant,  
**I want** the ability to interrupt the AI assistant mid-response,  
**so that** natural conversational flow is maintained.

**Acceptance Criteria:**
1. MinWordsInterruptionStrategy implementation for detecting valid interruptions
2. Real-time audio monitoring during TTS playback
3. Immediate TTS cancellation when interruption detected
4. Smooth audio transition from TTS to user speech
5. Context preservation during interruption scenarios
6. Configurable interruption sensitivity and validation

### Story 3.5: End-to-End Call Flow Integration
**As a** banking customer,  
**I want** to make a complete voice call that connects through OpenSIPS to the AI assistant,  
**so that** I can have a natural conversation about my banking needs.

**Acceptance Criteria:**
1. Complete SIP call setup from external caller through OpenSIPS to AI Voice Connector
2. Bidirectional audio flow with proper call control
3. End-to-end latency measurement and validation (<700ms total)
4. Call termination and cleanup handling
5. Comprehensive integration testing with real SIP clients
6. Performance monitoring and latency reporting

### Story 3.6: Monitoring and Session Management
**As a** system administrator,  
**I want** comprehensive monitoring of call sessions and audio quality,  
**so that** I can ensure system performance and troubleshoot issues.

**Acceptance Criteria:**
1. Session ID assignment and tracking across all components
2. Real-time metrics collection for latency, audio quality, and system performance
3. Structured logging of call flow events and timing
4. Error classification and alerting (VAD timeout, ASR empty, LLM failure, TTS error)
5. Dashboard for monitoring active sessions and system health
6. Historical reporting and analytics capabilities

## Epic 4: Banking IVR Features & Optimization

**Epic Goal:** Implement the Card Delivery Status Inquiry MVP scenario with banking-specific conversation flows, optimize the entire system to meet strict latency targets, and prepare the solution for production deployment in a banking environment.

### Story 4.1: Card Delivery Status Inquiry Flow
**As a** banking customer,  
**I want** to inquire about my card delivery status through natural conversation,  
**so that** I can get real-time updates without navigating complex menu systems.

**Acceptance Criteria:**
1. Natural language understanding for card delivery inquiries (variations like "Where is my card?", "Card status", "When will my card arrive?")
2. Customer authentication integration (account number, phone verification, etc.)
3. Backend integration with card delivery tracking systems (mock API for MVP)
4. Conversational responses with delivery status, tracking numbers, and estimated delivery dates
5. Error handling for invalid accounts, missing information, or system unavailability
6. Conversation flow testing with multiple inquiry variations

### Story 4.2: Banking-Specific Context and Safety
**As a** banking compliance officer,  
**I want** appropriate security controls and conversation boundaries,  
**so that** customer data is protected and interactions remain within approved banking scenarios.

**Acceptance Criteria:**
1. PII (Personally Identifiable Information) filtering and protection in logs
2. Banking-appropriate response templates and conversation boundaries
3. Conversation timeout and session security controls
4. Audit logging for compliance requirements
5. Escalation paths for complex queries outside MVP scope
6. Security testing for data leakage and unauthorized access

### Story 4.3: Performance Optimization and Latency Tuning
**As a** system performance engineer,  
**I want** the entire pipeline optimized to consistently meet latency targets,  
**so that** customers experience responsive, real-time conversations.

**Acceptance Criteria:**
1. End-to-end latency consistently under 700ms (p95) through optimization
2. Component-level latency optimization (VAD ≤20ms, ASR ≤250ms, LLM ≤300ms, TTS ≤200ms)
3. Memory and CPU optimization for concurrent session handling
4. GPU resource optimization for ML inference
5. Network optimization and buffering strategies
6. Load testing with multiple concurrent calls

### Story 4.4: Conversation Context and Memory Management
**As a** banking customer,  
**I want** the AI to remember context throughout our conversation,  
**so that** I don't have to repeat information and can have natural follow-up questions.

**Acceptance Criteria:**
1. Session-based conversation memory storing customer context
2. Context-aware responses that reference previous conversation elements
3. Memory management for long conversations without performance degradation
4. Context cleanup and session termination handling
5. Multi-turn conversation testing for card delivery scenarios
6. Memory overflow protection and graceful degradation

### Story 4.5: Production Deployment Configuration
**As a** system administrator,  
**I want** production-ready deployment configurations and operational procedures,  
**so that** the system can be deployed reliably in a banking environment.

**Acceptance Criteria:**
1. Production Docker configurations with security hardening
2. Environment-specific configuration management (dev, staging, production)
3. Backup and disaster recovery procedures
4. Production monitoring and alerting configuration
5. Deployment automation and rollback procedures
6. Documentation for operations team and troubleshooting guides

### Story 4.6: MVP Testing and Validation
**As a** product manager,  
**I want** comprehensive testing of the Card Delivery Status Inquiry MVP,  
**so that** we can validate the solution meets business requirements and customer needs.

**Acceptance Criteria:**
1. End-to-end testing with real banking customer scenarios
2. User acceptance testing with sample conversations
3. Performance validation under realistic load conditions
4. Integration testing with banking systems and data sources
5. Security and compliance testing for banking regulations
6. MVP demonstration and stakeholder sign-off

## Epic 5: Cloud AI Integration & Hybrid Deployment 🚀 FUTURE

**Epic Goal:** Enhance the system with cloud AI provider integrations to offer premium quality options and hybrid deployment flexibility, enabling customers to choose between cost-effective local processing and high-quality cloud services based on their specific needs and infrastructure constraints.

### Story 5.1: Faster-Whisper ASR Cloud Integration
**As a** system administrator,  
**I want** the option to use Faster-Whisper cloud ASR service,  
**so that** I can achieve higher transcription accuracy for critical banking conversations.

**Acceptance Criteria:**
1. Faster-Whisper API integration with secure authentication
2. Configuration option to switch between Vosk (local) and Faster-Whisper (cloud)
3. Streaming audio support with cloud API
4. Error handling and fallback to local ASR if cloud unavailable
5. Cost monitoring and usage tracking for cloud service
6. Performance comparison testing between local and cloud options

### Story 5.2: OpenAI GPT-4o LLM Cloud Integration
**As a** banking customer,  
**I want** access to advanced language understanding capabilities,  
**so that** I can have more natural and intelligent conversations about complex banking needs.

**Acceptance Criteria:**
1. OpenAI GPT-4o API integration with secure key management
2. Configuration option to switch between LLaMA (local) and OpenAI (cloud)
3. Banking-specific prompt engineering and safety controls
4. Conversation context management with cloud API
5. Cost optimization through intelligent caching and request batching
6. Compliance validation for cloud data processing

### Story 5.3: ElevenLabs TTS Cloud Integration
**As a** banking customer,  
**I want** natural, high-quality voice responses,  
**so that** my experience feels more human and professional.

**Acceptance Criteria:**
1. ElevenLabs API integration with voice selection options
2. Configuration option to switch between Piper (local) and ElevenLabs (cloud)
3. Streaming audio synthesis with low latency
4. Voice customization for brand consistency
5. Audio quality optimization for telephony transmission
6. Cost management and voice usage monitoring

### Story 5.4: Configurable Backend Selection Framework
**As a** system administrator,  
**I want** flexible configuration options for AI backend selection,  
**so that** I can optimize for cost, quality, and compliance requirements.

**Acceptance Criteria:**
1. Service-level configuration for backend selection (local/cloud/hybrid)
2. Runtime switching capabilities without service restart
3. Load balancing between local and cloud backends
4. Health monitoring for all backend options
5. Automatic failover from cloud to local backends
6. Configuration validation and deployment testing

### Story 5.5: Hybrid Deployment Scenarios
**As a** enterprise customer,  
**I want** the ability to use different AI backends based on call priority or customer tier,  
**so that** I can optimize costs while maintaining quality for premium customers.

**Acceptance Criteria:**
1. Customer tier-based backend routing
2. Call priority assessment and backend selection
3. Real-time cost vs quality optimization
4. Monitoring and analytics for hybrid usage patterns
5. Business rule engine for backend selection logic
6. Cost reporting and optimization recommendations

## Checklist Results Report

### Executive Summary

- **Overall PRD Completeness:** 85%
- **MVP Scope Appropriateness:** Just Right 
- **Readiness for Architecture Phase:** Ready
- **Most Critical Gaps:** Banking-specific business metrics and detailed user research

### Category Analysis Table

| Category                         | Status  | Critical Issues |
| -------------------------------- | ------- | --------------- |
| 1. Problem Definition & Context  | PASS    | None |
| 2. MVP Scope Definition          | PASS    | Well-scoped card delivery scenario |
| 3. User Experience Requirements  | PARTIAL | Limited to voice UI, needs conversation flow detail |
| 4. Functional Requirements       | PASS    | Complete with clear identifiers |
| 5. Non-Functional Requirements   | PASS    | Comprehensive latency targets |
| 6. Epic & Story Structure        | PASS    | Well-sequenced, appropriate sizing |
| 7. Technical Guidance            | PASS    | Clear architecture direction |
| 8. Cross-Functional Requirements | PARTIAL | Banking integration details needed |
| 9. Clarity & Communication       | PASS    | Well-structured and clear |

### Top Issues by Priority

**HIGH:**
- Banking compliance requirements need more detail (PCI DSS, SOX, etc.)
- Customer authentication flow specifics missing
- Error handling for banking system outages undefined

**MEDIUM:**
- Conversation timeout policies for banking security
- Data retention policies for call recordings
- Performance monitoring dashboard specifics

**LOW:**
- User research citations (acceptable for technical MVP)
- Competitive analysis depth (sufficient for initial implementation)

### MVP Scope Assessment

**✅ Scope is Appropriate:**
- Single use case (card delivery) is perfect for validation
- Technical complexity is manageable for MVP
- Clear path from MVP to production scaling

**⚠️ Considerations:**
- Banking integration mock APIs keep scope minimal
- Dual AI provider options provide good flexibility
- Timeline realistic for 4-epic structure

### Technical Readiness

**✅ Well Defined:**
- Clear technical stack and constraints
- Latency targets are specific and measurable
- Architecture guidance supports implementation

**⚠️ Areas for Architect Investigation:**
- GPU resource sizing for concurrent sessions
- Network topology for banking environment deployment
- OpenSIPS configuration optimization

### Recommendations

1. **Add banking compliance section** to Technical Assumptions
2. **Define customer authentication flow** in Story 4.1 acceptance criteria
3. **Specify banking system integration patterns** for production readiness
4. **Document conversation security policies** for banking environment

### Final Decision

**✅ ARCHITECTURE IMPLEMENTED** - The microservices architecture has been successfully implemented with gRPC services, Docker orchestration, and service management. Current focus is on OpenSIPS integration refactoring (Phase 3).

## Docker Deployment Guide

### Quick Start
```bash
# Development mode with live code changes
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# Production mode
docker-compose up -d

# Check service health
docker-compose ps
```

### Service Endpoints
- **ASR Service**: localhost:50051 (gRPC)
- **LLM Service**: localhost:50052 (gRPC) 
- **TTS Service**: localhost:50053 (gRPC)
- **Core Application**: localhost:8080 (HTTP management)

### Model Requirements
Place AI model files in respective directories:
- `models/vosk/` - Vosk ASR model files
- `models/llm/` - LLaMA model files (.gguf format)
- `models/piper/` - Piper TTS model files (.onnx + .json)

See `README.Docker.md` for complete deployment instructions.

## Next Steps

### Current Priority: Phase 3 - OpenSIPS Integration
Refactor the existing OpenSIPS integration layer to work with the new microservices architecture, enabling end-to-end voice call processing.

### Phase 4: Banking Features Implementation  
Once Phase 3 is complete, implement the Card Delivery Status Inquiry MVP scenario with banking-specific conversation flows and performance optimization.