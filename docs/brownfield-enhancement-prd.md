# OpenSIPS AI Voice Connector Development Environment Stabilization PRD

## Intro Project Analysis and Context

### Analysis Source
**IDE-based fresh analysis** with comprehensive QA review findings available from previous assessment.

### Current Project State
The OpenSIPS AI Voice Connector is a microservices-based AI voice processing system featuring:
- **ASR Service**: Speech-to-text using Vosk (Port 50051)
- **LLM Service**: Language model processing using LLaMA (Port 50052)  
- **TTS Service**: Text-to-speech using Piper (Port 50053)
- **Core Application**: OpenSIPS integration and pipeline orchestration (Port 8080)

The system has achieved substantial infrastructure completion but requires critical fixes for development stability.

### Available Documentation Analysis
**Using existing project analysis** - comprehensive documentation available:

#### Available Documentation
- ✅ Tech Stack Documentation (Python 3.10+, Docker, gRPC microservices)
- ✅ Source Tree/Architecture (complete microservices structure documented)
- ✅ Coding Standards (Black formatter, Ruff linter, structured logging)
- ✅ API Documentation (gRPC service specifications)
- ✅ External API Documentation (Vosk, LLaMA, Piper model integrations)
- ❌ UX/UI Guidelines (CLI/management interface only)
- ✅ Technical Debt Documentation (QA review identified critical issues)

### Enhancement Scope Definition

#### Enhancement Type
- ✅ **Bug Fix and Stability Improvements**
- ✅ **Performance/Scalability Improvements** 
- ✅ **Integration with New Systems** (testing frameworks)

#### Enhancement Description
Stabilize the development environment by resolving critical service import issues, implementing comprehensive unit testing frameworks across all microservices, and optimizing the LLM service build process for efficient development workflow.

#### Impact Assessment
- ✅ **Moderate Impact** (some existing code changes for imports and testing)
- ❌ Minimal Impact (isolated additions)
- ❌ Significant Impact (substantial existing code changes)
- ❌ Major Impact (architectural changes required)

### Goals and Background Context

#### Goals
• Resolve service import issues preventing proper microservice communication
• Implement comprehensive unit testing framework across ASR, LLM, and TTS services
• Optimize LLM service Docker build for faster development iterations
• Enable grpc-health-probe functionality for proper service health monitoring
• Establish hot-reload development workflow with docker-compose.dev.yml

#### Background Context
The recent QA review revealed that while the infrastructure foundation is solid with proper Docker orchestration and configuration management, critical development blockers prevent the system from being fully functional for development use. The existing architecture is sound, but service-level implementation issues (import problems, missing test infrastructure, build optimization) must be resolved to enable productive development workflows. This enhancement addresses the technical debt identified in the QA review while maintaining the existing microservices architecture.

### Change Log

| Change | Date | Version | Description | Author |
|--------|------|---------|-------------|--------|
| Initial PRD | 2025-07-27 | 1.0 | Development environment stabilization requirements | BMad PM Agent |

## Requirements

### Functional

**FR1**: The service import system will resolve common_pb2 module dependencies across all gRPC services without breaking existing proto file functionality.

**FR2**: Each microservice (ASR, LLM, TTS) will include a comprehensive unit testing framework using pytest with asyncio support for gRPC testing.

**FR3**: The LLM service Docker build process will be optimized to reduce build times while maintaining full PyTorch functionality.

**FR4**: All Docker services will include grpc-health-probe installation for proper health check functionality.

**FR5**: A development mode configuration (docker-compose.dev.yml) will enable hot-reload capabilities for source code changes.

**FR6**: Test fixtures and factories will be created following the established testing strategy for shared test data generation.

### Non Functional

**NFR1**: Service startup times must not exceed current baselines (ASR/TTS: 40s, LLM: 60s, Core: 60s) after optimizations.

**NFR2**: Unit test execution must complete within 30 seconds per service for rapid development feedback.

**NFR3**: Docker build optimization must maintain current memory usage patterns (< 4GB total system usage).

**NFR4**: Hot-reload functionality must reflect code changes within 30 seconds of file modification.

**NFR5**: All health checks must respond within 10 seconds to maintain existing Docker Compose orchestration timing.

### Compatibility Requirements

**CR1**: **Existing API Compatibility**: All gRPC service APIs must maintain current protobuf definitions and not break existing service communication patterns.

**CR2**: **Database Schema Compatibility**: Configuration file formats (app.ini) and model file structures must remain unchanged to preserve existing deployments.

**CR3**: **UI/UX Consistency**: HTTP management interface (port 8080) and logging output formats must maintain current behavior for operational consistency.

**CR4**: **Integration Compatibility**: Docker Compose service definitions must remain compatible with existing volume mounts and environment variable configurations.

## Technical Constraints and Integration Requirements

### Existing Technology Stack

**Languages**: Python 3.10+ with mandatory type hints
**Frameworks**: gRPC, asyncio, pipecat pipeline framework
**Database**: File-based configuration (app.ini), model files (Vosk, LLaMA, Piper)
**Infrastructure**: Docker Compose, custom network bridge (172.20.0.0/16)
**External Dependencies**: Vosk ASR models, LLaMA GGUF models, Piper TTS models

### Integration Approach

**Database Integration Strategy**: Maintain existing file-based configuration with enhanced validation and error handling
**API Integration Strategy**: Preserve current gRPC service definitions while fixing import resolution and adding health endpoints  
**Frontend Integration Strategy**: Maintain HTTP management interface while adding development debugging capabilities
**Testing Integration Strategy**: Implement pytest framework parallel to existing validation scripts without disrupting current testing approach

### Code Organization and Standards

**File Structure Approach**: Maintain existing services/{service-name}/src structure while adding services/{service-name}/tests directories
**Naming Conventions**: Follow existing Python module naming and gRPC service naming patterns
**Coding Standards**: Enforce existing Black formatter, Ruff linter, mypy type checking standards
**Documentation Standards**: Maintain structured logging format and add inline documentation for new testing utilities

### Deployment and Operations

**Build Process Integration**: Enhance existing Dockerfiles with multi-stage builds for LLM optimization while preserving current build outputs
**Deployment Strategy**: Maintain current docker-compose.yml for production with additional docker-compose.dev.yml for development
**Monitoring and Logging**: Preserve existing structured logging while adding debug-level output for development mode
**Configuration Management**: Maintain app.ini format while adding validation and development-specific overrides

### Risk Assessment and Mitigation

**Technical Risks**: 
- Proto file changes could break service communication
- LLM build optimization might affect model loading
- Test framework integration could interfere with existing validation

**Integration Risks**:
- Import resolution changes might create circular dependencies
- Health probe installation could affect container startup sequencing
- Development mode configurations could conflict with production settings

**Deployment Risks**:
- Docker build changes could increase image sizes
- Hot-reload functionality might impact performance in development
- New test dependencies could create version conflicts

**Mitigation Strategies**:
- Implement changes incrementally with rollback points
- Maintain separate development and production configurations
- Use Docker multi-stage builds to control image sizes
- Implement comprehensive integration testing before deployment

## Epic and Story Structure

### Epic Approach

**Epic Structure Decision**: Single comprehensive epic with rationale - This enhancement addresses interconnected development infrastructure issues that must be resolved together to achieve a stable development environment. The import fixes, testing framework, and build optimization are interdependent and should be implemented as a coordinated effort to avoid partial functionality states.

## Epic 1: Development Environment Stabilization

**Epic Goal**: Establish a fully functional, optimized development environment for the OpenSIPS AI Voice Connector that enables productive development workflows while maintaining system integrity and performance.

**Integration Requirements**: All changes must preserve existing production functionality while enabling enhanced development capabilities through proper testing, optimized builds, and reliable service communication.

### Story 1.1: Resolve Service Import Dependencies

As a **developer**,
I want **all gRPC services to properly import common_pb2 modules**,
so that **services can communicate without import errors and the development environment functions correctly**.

#### Acceptance Criteria

1. All services (ASR, LLM, TTS) can import common_pb2 without ModuleNotFoundError
2. Proto file compilation generates all required _pb2 and _pb2_grpc modules
3. Services start successfully and establish gRPC communication channels
4. Service registry can connect to and health-check all services
5. End-to-end pipeline test passes without import-related failures

#### Integration Verification

**IV1**: **Existing Functionality Verification** - All current Docker Compose services start and reach healthy status using existing health check definitions
**IV2**: **Integration Point Verification** - Service-to-service gRPC communication maintains current timeout and retry behavior patterns
**IV3**: **Performance Impact Verification** - Service startup times remain within established baselines (40s for ASR/TTS, 60s for LLM/Core)

### Story 1.2: Implement Comprehensive Unit Testing Framework

As a **developer**,
I want **each microservice to have a complete unit testing framework with pytest and async support**,
so that **I can develop and refactor with confidence while maintaining code quality standards**.

#### Acceptance Criteria

1. Each service (ASR, LLM, TTS) has a tests/ directory with pytest configuration
2. Unit tests cover core service functionality with async/await patterns for gRPC testing
3. Test fixtures and factories are available for common test data scenarios
4. Tests can be executed independently and in parallel without conflicts
5. Test coverage reporting is available and meets minimum thresholds per testing strategy

#### Integration Verification

**IV1**: **Existing Functionality Verification** - All existing validation scripts (validate_dev_env.py, test_e2e_flow.py) continue to function without modification
**IV2**: **Integration Point Verification** - New test framework does not interfere with existing Docker health checks or service startup procedures
**IV3**: **Performance Impact Verification** - Test execution completes within 30 seconds per service and does not impact production service performance

### Story 1.3: Optimize LLM Service Build Process

As a **developer**,
I want **the LLM service to build efficiently with optimized Docker layers**,
so that **development iterations are faster and the build process doesn't block development workflow**.

#### Acceptance Criteria

1. LLM service Docker build completes in significantly reduced time through multi-stage builds
2. Final image size is optimized while maintaining full PyTorch functionality
3. Model loading performance is preserved or improved after build optimization
4. Build process supports development mode with faster rebuilds for code changes
5. Production functionality remains identical to current implementation

#### Integration Verification

**IV1**: **Existing Functionality Verification** - LLM service maintains current gRPC API compatibility and model inference performance
**IV2**: **Integration Point Verification** - Optimized service integrates properly with existing Docker Compose orchestration and health check timing
**IV3**: **Performance Impact Verification** - Memory usage remains within established limits and service communication latency is preserved

### Story 1.4: Enable Development Mode with Hot Reload

As a **developer**,
I want **a development configuration that supports hot-reload and debugging capabilities**,
so that **I can make code changes efficiently without rebuilding containers for every modification**.

#### Acceptance Criteria

1. docker-compose.dev.yml extends production configuration with development-specific overrides
2. Source code directories are mounted as volumes for hot-reload functionality
3. Development mode enables debug logging and enhanced error output
4. Code changes reflect in running services within 30 seconds
5. Development and production modes can be switched without conflicts

#### Integration Verification

**IV1**: **Existing Functionality Verification** - Production docker-compose.yml behavior is unchanged and development mode can be cleanly switched back to production
**IV2**: **Integration Point Verification** - Development mode maintains all service-to-service communication patterns and health check requirements
**IV3**: **Performance Impact Verification** - Hot-reload functionality does not impact production performance and development mode clearly indicates its status

### Story 1.5: Implement Service Health Monitoring

As a **developer**,
I want **proper health check mechanisms with grpc-health-probe functionality**,
so that **I can reliably monitor service status and debug connectivity issues during development**.

#### Acceptance Criteria

1. All service Dockerfiles include grpc-health-probe installation
2. Health check endpoints respond correctly for all gRPC services
3. Docker Compose health checks function reliably with appropriate timeouts
4. Service health status is clearly visible in logs and monitoring output
5. Failed health checks provide actionable debugging information

#### Integration Verification

**IV1**: **Existing Functionality Verification** - Current Docker Compose orchestration and dependency management behavior is preserved
**IV2**: **Integration Point Verification** - Health check integration maintains existing service startup sequencing and dependency waiting
**IV3**: **Performance Impact Verification** - Health check overhead does not impact service performance and responds within established 10-second timeout requirements