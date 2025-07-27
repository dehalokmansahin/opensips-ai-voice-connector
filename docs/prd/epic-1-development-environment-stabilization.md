# Epic 1: Development Environment Stabilization

**Epic Goal**: Establish a fully functional, optimized development environment for the OpenSIPS AI Voice Connector that enables productive development workflows while maintaining system integrity and performance.

**Integration Requirements**: All changes must preserve existing production functionality while enabling enhanced development capabilities through proper testing, optimized builds, and reliable service communication.

## Story 1.1: Resolve Service Import Dependencies

As a **developer**,
I want **all gRPC services to properly import common_pb2 modules**,
so that **services can communicate without import errors and the development environment functions correctly**.

### Acceptance Criteria

1. All services (ASR, LLM, TTS) can import common_pb2 without ModuleNotFoundError
2. Proto file compilation generates all required _pb2 and _pb2_grpc modules
3. Services start successfully and establish gRPC communication channels
4. Service registry can connect to and health-check all services
5. End-to-end pipeline test passes without import-related failures

### Integration Verification

**IV1**: **Existing Functionality Verification** - All current Docker Compose services start and reach healthy status using existing health check definitions
**IV2**: **Integration Point Verification** - Service-to-service gRPC communication maintains current timeout and retry behavior patterns
**IV3**: **Performance Impact Verification** - Service startup times remain within established baselines (40s for ASR/TTS, 60s for LLM/Core)

## Story 1.2: Implement Comprehensive Unit Testing Framework

As a **developer**,
I want **each microservice to have a complete unit testing framework with pytest and async support**,
so that **I can develop and refactor with confidence while maintaining code quality standards**.

### Acceptance Criteria

1. Each service (ASR, LLM, TTS) has a tests/ directory with pytest configuration
2. Unit tests cover core service functionality with async/await patterns for gRPC testing
3. Test fixtures and factories are available for common test data scenarios
4. Tests can be executed independently and in parallel without conflicts
5. Test coverage reporting is available and meets minimum thresholds per testing strategy

### Integration Verification

**IV1**: **Existing Functionality Verification** - All existing validation scripts (validate_dev_env.py, test_e2e_flow.py) continue to function without modification
**IV2**: **Integration Point Verification** - New test framework does not interfere with existing Docker health checks or service startup procedures
**IV3**: **Performance Impact Verification** - Test execution completes within 30 seconds per service and does not impact production service performance

## Story 1.3: Optimize LLM Service Build Process

As a **developer**,
I want **the LLM service to build efficiently with optimized Docker layers**,
so that **development iterations are faster and the build process doesn't block development workflow**.

### Acceptance Criteria

1. LLM service Docker build completes in significantly reduced time through multi-stage builds
2. Final image size is optimized while maintaining full PyTorch functionality
3. Model loading performance is preserved or improved after build optimization
4. Build process supports development mode with faster rebuilds for code changes
5. Production functionality remains identical to current implementation

### Integration Verification

**IV1**: **Existing Functionality Verification** - LLM service maintains current gRPC API compatibility and model inference performance
**IV2**: **Integration Point Verification** - Optimized service integrates properly with existing Docker Compose orchestration and health check timing
**IV3**: **Performance Impact Verification** - Memory usage remains within established limits and service communication latency is preserved

## Story 1.4: Enable Development Mode with Hot Reload

As a **developer**,
I want **a development configuration that supports hot-reload and debugging capabilities**,
so that **I can make code changes efficiently without rebuilding containers for every modification**.

### Acceptance Criteria

1. docker-compose.dev.yml extends production configuration with development-specific overrides
2. Source code directories are mounted as volumes for hot-reload functionality
3. Development mode enables debug logging and enhanced error output
4. Code changes reflect in running services within 30 seconds
5. Development and production modes can be switched without conflicts

### Integration Verification

**IV1**: **Existing Functionality Verification** - Production docker-compose.yml behavior is unchanged and development mode can be cleanly switched back to production
**IV2**: **Integration Point Verification** - Development mode maintains all service-to-service communication patterns and health check requirements
**IV3**: **Performance Impact Verification** - Hot-reload functionality does not impact production performance and development mode clearly indicates its status

## Story 1.5: Implement Service Health Monitoring

As a **developer**,
I want **proper health check mechanisms with grpc-health-probe functionality**,
so that **I can reliably monitor service status and debug connectivity issues during development**.

### Acceptance Criteria

1. All service Dockerfiles include grpc-health-probe installation
2. Health check endpoints respond correctly for all gRPC services
3. Docker Compose health checks function reliably with appropriate timeouts
4. Service health status is clearly visible in logs and monitoring output
5. Failed health checks provide actionable debugging information

### Integration Verification

**IV1**: **Existing Functionality Verification** - Current Docker Compose orchestration and dependency management behavior is preserved
**IV2**: **Integration Point Verification** - Health check integration maintains existing service startup sequencing and dependency waiting
**IV3**: **Performance Impact Verification** - Health check overhead does not impact service performance and responds within established 10-second timeout requirements