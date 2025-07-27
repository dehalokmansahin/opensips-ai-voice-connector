# IVR Flow Automation System Product Requirements Document (PRD)

## Goals and Background Context

### Goals
- Enable automated testing of IVR systems through phone call interactions
- Replace manual IVR testing with automated voice-based test execution
- Provide a web interface for managing test scenarios and monitoring call progress
- Support DTMF tone generation for IVR navigation testing
- Enable step-by-step test case execution with real-time validation
- Utilize existing Pipecat ASR/TTS infrastructure for voice processing
- Support multiple phone lines with organized scenario management

### Background Context

This project transforms an existing OpenSIPS AI Voice Connector into a specialized IVR Flow Automation System. The system addresses the challenge of manual IVR testing by automating the entire testing workflow through programmatic phone calls. Instead of requiring human testers to manually call and navigate IVR systems, this solution uses Twilio for outbound calling, text-to-speech for sending prompts to IVRs, automatic speech recognition for capturing IVR responses, and intent recognition for validating expected behaviors. The system maintains the existing Pipecat ASR/TTS pipeline while removing the OpenSIPS dependency in favor of Twilio's more suitable telephony services for automated testing scenarios.

### Change Log

| Date | Version | Description | Author |
|------|---------|-------------|---------|
| 2025-07-27 | 1.0 | Initial PRD creation from Project Brief | John (PM) |
| 2025-07-27 | 2.0 | Updated with microservices architecture and current implementation status | John (PM) |

## Requirements

### Functional

**FR1:** The system must initiate outbound SIP calls using OpenSIPS to target IVR systems under test  
**FR2:** The system must send DTMF tones during calls to navigate IVR menu options  
**FR3:** The system must convert text prompts to speech using TTS service and play them to IVR  
**FR4:** The system must capture and transcribe IVR audio responses using ASR service  
**FR5:** The system must perform basic intent recognition on IVR responses using Turkish BERT  
**FR6:** The system must execute simple test scenarios step-by-step  
**FR7:** The system must provide a simple web interface for managing test scenarios  
**FR8:** The system must log call interactions and test results  
**FR9:** The system must validate test outcomes and mark pass/fail status  
**FR10:** The system must handle call failures and timeout scenarios gracefully

### Non Functional

**NFR1:** Test scenarios must complete within configurable timeouts  
**NFR2:** ASR transcription accuracy must be sufficient for intent recognition (>85%)  
**NFR3:** TTS audio quality must be clear for IVR system processing  
**NFR4:** The system must handle basic call volumes (5-10 concurrent calls)  
**NFR5:** Test results must be stored with basic logging  
**NFR6:** Web interface response times must be under 3 seconds

## User Interface Design Goals

### Overall UX Vision
Simple web interface for creating and running basic IVR tests. Focus on minimal functionality with clear test execution and results display.

### Key Interaction Paradigms
- **Simple Forms**: Basic forms for creating test scenarios
- **Test Execution**: Simple start/stop test controls
- **Results Display**: Basic table showing test outcomes

### Core Screens and Views
- **Test Management**: List and create test scenarios
- **Test Execution**: Run tests and view live status
- **Results**: View test outcomes and logs

### Accessibility: Basic
Standard web accessibility practices with keyboard navigation.

### Branding
Minimal, clean interface focusing on functionality over aesthetics.

### Target Device and Platforms: Web Desktop
Desktop browsers only for simplicity.

## Technical Assumptions

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

## Epic List

**Epic 1: OpenSIPS Outbound Call Foundation**  
Configure OpenSIPS for outbound SIP calls and adapt existing services for basic IVR testing.

**Epic 2: Simple Test Framework**  
Implement basic test scenario execution with Turkish BERT intent recognition.

**Epic 3: Basic Web Interface**  
Create simple web interface for test management and execution.

## Epic 1: OpenSIPS Outbound Call Foundation

**Epic Goal:** Configure OpenSIPS for outbound SIP calls to IVR systems and adapt existing ASR/TTS services for basic testing workflow while delivering a simple call-and-transcribe capability.

### Story 1.1: OpenSIPS Outbound Configuration
**As a** test engineer,  
**I want** OpenSIPS configured to make outbound SIP calls,  
**so that** I can call target IVR systems for testing.

**Acceptance Criteria:**
1. OpenSIPS routing configuration for outbound calls
2. SIP trunk setup for external connectivity
3. Basic call control through OpenSIPS MI interface
4. Call status monitoring (connected, failed, completed)
5. RTP audio stream handling for bidirectional communication

### Story 1.2: Test Controller Service
**As a** test orchestrator,  
**I want** a simple service to manage test execution,  
**so that** I can coordinate calls and audio processing.

**Acceptance Criteria:**
1. Test Controller service with REST API
2. Integration with OpenSIPS for call initiation
3. Coordination with existing ASR/TTS services
4. Basic test scenario storage (SQLite)
5. Test execution logging and results storage

### Story 1.3: DTMF Tone Generation
**As a** test system,  
**I want** to send DTMF tones during calls,  
**so that** I can navigate IVR menu options.

**Acceptance Criteria:**
1. DTMF tone generation capability
2. Timing control for tone sequences
3. Integration with call control flow
4. Support for common IVR navigation patterns

## Epic 2: Simple Test Framework

**Epic Goal:** Implement basic test scenario execution with intent recognition for validating IVR responses.

### Story 2.1: Turkish BERT Intent Recognition
**As a** test validator,  
**I want** intent recognition on transcribed IVR responses,  
**so that** I can validate expected behaviors.

**Acceptance Criteria:**
1. Turkish BERT model integration (dbmdz/bert-base-turkish-uncased)
2. Basic intent classification for common IVR responses
3. Pass/fail determination based on expected intents
4. Simple training data for IVR-specific responses

### Story 2.2: Test Scenario Execution
**As a** test runner,  
**I want** to execute test scenarios step-by-step,  
**so that** I can automate IVR testing workflows.

**Acceptance Criteria:**
1. Simple test scenario definition format
2. Step-by-step execution with audio prompts and responses
3. Conditional logic based on IVR responses
4. Test result reporting with pass/fail status

## Epic 3: Basic Web Interface

**Epic Goal:** Create simple web interface for managing and executing tests.

### Story 3.1: Test Management Interface
**As a** test manager,  
**I want** a web interface to create and manage test scenarios,  
**so that** I can easily configure IVR tests.

**Acceptance Criteria:**
1. Simple forms for test scenario creation
2. List view of existing test scenarios
3. Basic test configuration options
4. Test scenario editing capabilities

### Story 3.2: Test Execution Interface
**As a** test operator,  
**I want** to run tests and monitor progress,  
**so that** I can execute IVR testing workflows.

**Acceptance Criteria:**
1. Test execution controls (start/stop)
2. Real-time test status display
3. Live call progress monitoring
4. Test results display with logs

## Next Steps

### Implementation Priority
Start with Epic 1 to establish OpenSIPS outbound calling capabilities and basic test framework foundation.

### Architect Prompt
Review the simplified IVR Flow Automation System requirements and create a technical architecture plan for transforming the existing voice assistant into an automated IVR testing platform using OpenSIPS for outbound calls.

### Development Focus
Keep implementation simple and focused on core IVR testing capabilities with minimal complexity.