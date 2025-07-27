# Development Environment Setup Story
## OpenSIPS AI Voice Connector Project

**Story**: As James the developer, I need to set up a complete development environment for the OpenSIPS AI Voice Connector project so that I can develop, test, and validate the microservices-based AI voice processing system.

---

## Epic: Complete Development Environment Setup

### Story Background
The OpenSIPS AI Voice Connector is a microservices-based AI voice processing system with the following components:
- **ASR Service**: Speech-to-text using Vosk (Port 50051)
- **LLM Service**: Language model processing using LLaMA (Port 50052)  
- **TTS Service**: Text-to-speech using Piper (Port 50053)
- **Core Application**: OpenSIPS integration and pipeline orchestration (Port 8080)

### Prerequisites Validation
- [ ] **Task 1.1**: Verify Docker and Docker Compose installation
  - [ ] Run `docker --version` (require Docker 20.10+)
  - [ ] Run `docker-compose --version` (require 1.29+)
  - [ ] Verify Docker daemon is running
  - **AC**: Docker and Docker Compose are functional

- [ ] **Task 1.2**: Verify Python environment
  - [ ] Confirm Python 3.9+ is installed
  - [ ] Verify pip is available and updated
  - [ ] Check Python path configuration
  - **AC**: Python environment is ready for development

- [ ] **Task 1.3**: Validate system resources
  - [ ] Ensure minimum 8GB RAM available
  - [ ] Verify 10GB+ free disk space
  - [ ] Check network ports 5060, 8080, 50051-50053 are available
  - **AC**: System meets resource requirements

---

## Phase 1: Model Dependencies and Directory Structure

### Story 1.1: Model Directory Preparation
**As a developer, I need to prepare the AI model directories so that the services can access required model files.**

- [ ] **Task 1.1.1**: Create model directory structure
  ```bash
  mkdir -p models/vosk
  mkdir -p models/llm  
  mkdir -p models/piper
  mkdir -p models/rag_model
  ```
  - **AC**: All model directories exist with proper permissions

- [ ] **Task 1.1.2**: Download Vosk ASR model (if not present)
  - [ ] Download Turkish Vosk model or preferred language model
  - [ ] Extract to `./models/vosk/` directory
  - [ ] Verify model structure contains `Am.ngram`, `final.mdl`, etc.
  - **AC**: Vosk model is properly extracted and accessible

- [ ] **Task 1.1.3**: Prepare LLM model files (if not present)
  - [ ] Download or link LLaMA model file as `llama-model.gguf`
  - [ ] Place in `./models/llm/` directory
  - [ ] Verify file permissions and size
  - **AC**: LLM model is accessible for service loading

- [ ] **Task 1.1.4**: Setup Piper TTS models (if not present)
  - [ ] Download Turkish Piper model `tr_TR-fahrettin-medium`
  - [ ] Extract to `./models/piper/` directory
  - [ ] Verify `.onnx` and `.json` files exist
  - **AC**: Piper TTS models are ready for text-to-speech conversion

### Story 1.2: Log Directory and Configuration
**As a developer, I need proper logging directories so that I can monitor application behavior during development.**

- [ ] **Task 1.2.1**: Create logging directory structure
  ```bash
  mkdir -p logs
  chmod 755 logs
  ```
  - **AC**: Logs directory exists with write permissions

- [ ] **Task 1.2.2**: Validate configuration file
  - [ ] Verify `config/app.ini` exists and is readable
  - [ ] Check service port configurations (50051, 50052, 50053)
  - [ ] Validate OpenSIPS configuration parameters
  - **AC**: Configuration file is valid and contains required settings

---

## Phase 2: Docker Service Orchestration

### Story 2.1: ASR Service Deployment
**As a developer, I need the ASR service running so that speech-to-text conversion is available.**

- [ ] **Task 2.1.1**: Build ASR service container
  ```bash
  docker-compose build asr-service
  ```
  - **AC**: ASR service builds successfully without errors

- [ ] **Task 2.1.2**: Start ASR service
  ```bash
  docker-compose up -d asr-service
  ```
  - **AC**: ASR service container starts and reaches healthy state

- [ ] **Task 2.1.3**: Validate ASR service health
  ```bash
  # Check service logs
  docker-compose logs asr-service
  
  # Verify health check
  docker-compose ps asr-service
  ```
  - **AC**: Service shows "healthy" status and logs indicate successful startup
  - **AC**: Service responds on port 50051

### Story 2.2: LLM Service Deployment  
**As a developer, I need the LLM service running so that natural language processing is available.**

- [ ] **Task 2.2.1**: Build LLM service container
  ```bash
  docker-compose build llm-service
  ```
  - **AC**: LLM service builds successfully without errors

- [ ] **Task 2.2.2**: Start LLM service
  ```bash
  docker-compose up -d llm-service
  ```
  - **AC**: LLM service container starts and reaches healthy state

- [ ] **Task 2.2.3**: Validate LLM service health
  ```bash
  # Check service logs for model loading
  docker-compose logs llm-service
  
  # Verify health check passes
  docker-compose ps llm-service
  ```
  - **AC**: Service shows "healthy" status and model is loaded
  - **AC**: Service responds on port 50052

### Story 2.3: TTS Service Deployment
**As a developer, I need the TTS service running so that text-to-speech conversion is available.**

- [ ] **Task 2.3.1**: Build TTS service container
  ```bash
  docker-compose build tts-service
  ```
  - **AC**: TTS service builds successfully without errors

- [ ] **Task 2.3.2**: Start TTS service
  ```bash
  docker-compose up -d tts-service
  ```
  - **AC**: TTS service container starts and reaches healthy state

- [ ] **Task 2.3.3**: Validate TTS service health
  ```bash
  # Check service logs for Piper model loading
  docker-compose logs tts-service
  
  # Verify health check passes  
  docker-compose ps tts-service
  ```
  - **AC**: Service shows "healthy" status and Piper model is loaded
  - **AC**: Service responds on port 50053

### Story 2.4: Core Application Deployment
**As a developer, I need the core application running so that the complete pipeline is orchestrated.**

- [ ] **Task 2.4.1**: Build core application container
  ```bash
  docker-compose build opensips-ai-core
  ```
  - **AC**: Core application builds successfully without errors

- [ ] **Task 2.4.2**: Start core application with dependencies
  ```bash
  docker-compose up -d opensips-ai-core
  ```
  - **AC**: Core application waits for service dependencies and starts successfully

- [ ] **Task 2.4.3**: Validate core application health
  ```bash
  # Check core application logs
  docker-compose logs opensips-ai-core
  
  # Test health endpoint
  curl http://localhost:8080/health
  ```
  - **AC**: Core application shows "healthy" status
  - **AC**: HTTP management interface responds on port 8080
  - **AC**: SIP interface is bound to port 5060

---

## Phase 3: Service Health Validation and Connectivity Testing

### Story 3.1: Individual Service Health Checks
**As a developer, I need to verify each service is functioning independently so that I can isolate any issues.**

- [ ] **Task 3.1.1**: Test ASR service gRPC connectivity
  ```bash
  # Test using grpc-health-probe or custom test
  grpc-health-probe -addr=localhost:50051 -service=ASRService
  ```
  - **AC**: ASR service responds to health probe successfully

- [ ] **Task 3.1.2**: Test LLM service gRPC connectivity  
  ```bash
  grpc-health-probe -addr=localhost:50052 -service=LLMService
  ```
  - **AC**: LLM service responds to health probe successfully

- [ ] **Task 3.1.3**: Test TTS service gRPC connectivity
  ```bash
  grpc-health-probe -addr=localhost:50053 -service=TTSService
  ```
  - **AC**: TTS service responds to health probe successfully

### Story 3.2: Inter-Service Communication Validation
**As a developer, I need to verify services can communicate with each other so that the pipeline works end-to-end.**

- [ ] **Task 3.2.1**: Validate service discovery from core application
  ```bash
  # Check core application logs for service connections
  docker-compose logs opensips-ai-core | grep -E "(ASR|LLM|TTS).*(connected|available)"
  ```
  - **AC**: Core application successfully connects to all three services

- [ ] **Task 3.2.2**: Test service registry functionality
  ```bash
  # Run service registry health check from core
  docker-compose exec opensips-ai-core python -c "
  import asyncio
  from core.grpc_clients.service_registry import ServiceRegistry
  from core.config.settings import Settings
  
  async def test():
      settings = Settings('config/app.ini')
      await settings.load()
      registry = ServiceRegistry(settings.services)
      await registry.initialize()
      health = await registry.health_check_all()
      print('Service Health:', health)
      await registry.stop()
  
  asyncio.run(test())
  "
  ```
  - **AC**: Service registry reports all services as healthy

---

## Phase 4: End-to-End Pipeline Validation

### Story 4.1: Core Pipeline Testing
**As a developer, I need to verify the complete audio processing pipeline so that I can confirm the system works end-to-end.**

- [ ] **Task 4.1.1**: Run end-to-end flow test
  ```bash
  # Execute the comprehensive E2E test
  docker-compose exec opensips-ai-core python test_e2e_flow.py
  ```
  - **AC**: E2E test passes all validation steps
  - **AC**: Service connectivity test passes
  - **AC**: Individual services test passes  
  - **AC**: Pipeline integration test passes
  - **AC**: Session creation test passes

- [ ] **Task 4.1.2**: Validate pipecat pipeline integration
  ```bash
  # Test pipecat components individually
  docker-compose exec opensips-ai-core python -c "
  from core.pipecat.processors.grpc_processors import ASRProcessor, LLMProcessor, TTSProcessor
  print('Pipecat processors imported successfully')
  "
  ```
  - **AC**: Pipecat processors load without errors
  - **AC**: Pipeline components integrate successfully

### Story 4.2: Session Management Testing
**As a developer, I need to verify session creation and management so that calls can be handled properly.**

- [ ] **Task 4.2.1**: Test conversation session creation
  ```bash
  # Test session creation through pipeline manager
  docker-compose exec opensips-ai-core python -c "
  import asyncio
  from core.bot.pipeline_manager import PipelineManager
  from core.grpc_clients.service_registry import ServiceRegistry
  from core.config.settings import Settings
  
  async def test_session():
      settings = Settings('config/app.ini')
      await settings.load()
      registry = ServiceRegistry(settings.services)
      await registry.initialize()
      manager = PipelineManager(registry, settings)
      await manager.initialize()
      
      session = await manager.create_test_session('test_dev_session')
      if session:
          stats = session.get_stats()
          print('Session Stats:', stats)
          await session.cleanup()
          print('Session test passed')
      else:
          print('Session creation failed')
      
      await manager.stop()
      await registry.stop()
  
  asyncio.run(test_session())
  "
  ```
  - **AC**: Test session creates successfully
  - **AC**: Session statistics are populated
  - **AC**: Session cleanup completes without errors

---

## Phase 5: Development Workflow Verification

### Story 5.1: Development Mode Setup
**As a developer, I need development mode working so that I can make code changes efficiently.**

- [ ] **Task 5.1.1**: Test development Docker Compose configuration
  ```bash
  # Stop production containers
  docker-compose down
  
  # Start in development mode
  docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d
  ```
  - **AC**: Development containers start with source code mounted
  - **AC**: Code changes reflect without rebuilding containers

- [ ] **Task 5.1.2**: Validate development logging and debugging
  ```bash
  # Check debug logging is enabled
  docker-compose logs asr-service | grep DEBUG
  docker-compose logs llm-service | grep DEBUG  
  docker-compose logs tts-service | grep DEBUG
  ```
  - **AC**: Debug logging is active in development mode
  - **AC**: All services show detailed debug output

### Story 5.2: Hot Reload and Code Changes
**As a developer, I need hot reload working so that I can see changes immediately.**

- [ ] **Task 5.2.1**: Test code hot reload
  ```bash
  # Make a minor change to a service file
  echo "# Development test comment" >> services/asr-service/src/asr_grpc_server.py
  
  # Check if service picks up changes (may require restart depending on implementation)
  docker-compose restart asr-service
  docker-compose logs asr-service | tail -10
  ```
  - **AC**: Service restarts quickly with mounted source code
  - **AC**: Changes are reflected in the running service

### Story 5.3: Testing and Debugging Tools
**As a developer, I need testing tools working so that I can debug issues effectively.**

- [ ] **Task 5.3.1**: Validate development testing capabilities
  ```bash
  # Run tests in development environment
  docker-compose exec asr-service python -m pytest tests/ || echo "Tests directory may not exist yet"
  docker-compose exec llm-service python -m pytest tests/ || echo "Tests directory may not exist yet"
  docker-compose exec tts-service python -m pytest tests/ || echo "Tests directory may not exist yet"
  ```
  - **AC**: Test framework is accessible in development containers
  - **AC**: Services support test execution

- [ ] **Task 5.3.2**: Test interactive debugging capabilities
  ```bash
  # Test interactive access to services
  docker-compose exec opensips-ai-core python -c "
  print('Interactive Python access works')
  import core.config.settings
  print('Core modules can be imported')
  "
  ```
  - **AC**: Interactive debugging access works
  - **AC**: All modules can be imported and tested interactively

---

## Final Validation and Documentation

### Story 6.1: Complete System Validation
**As a developer, I need to perform final validation so that I can confirm the development environment is fully functional.**

- [ ] **Task 6.1.1**: Run comprehensive system check
  ```bash
  # Full system health check
  docker-compose ps
  docker-compose exec opensips-ai-core python test_e2e_flow.py
  
  # Check all service endpoints
  curl -f http://localhost:8080/health
  grpc-health-probe -addr=localhost:50051 -service=ASRService
  grpc-health-probe -addr=localhost:50052 -service=LLMService  
  grpc-health-probe -addr=localhost:50053 -service=TTSService
  ```
  - **AC**: All services show healthy status
  - **AC**: E2E test passes completely
  - **AC**: All health endpoints respond successfully

- [ ] **Task 6.1.2**: Performance baseline validation
  ```bash
  # Check resource usage
  docker stats --no-stream
  
  # Check response times
  time curl -s http://localhost:8080/health > /dev/null
  ```
  - **AC**: Memory usage is within expected limits (< 4GB total)
  - **AC**: CPU usage is reasonable (< 50% under load)
  - **AC**: Response times are acceptable (< 1s for health checks)

### Story 6.2: Documentation and Handoff
**As a developer, I need proper documentation so that other developers can use this environment.**

- [ ] **Task 6.2.1**: Document environment setup results
  - [ ] Record all successful validation steps
  - [ ] Document any customizations or workarounds used
  - [ ] Note performance baseline measurements
  - **AC**: Environment setup is documented and reproducible

- [ ] **Task 6.2.2**: Create development quick-start checklist
  - [ ] List essential commands for daily development
  - [ ] Document troubleshooting steps for common issues
  - [ ] Provide service restart and debugging procedures
  - **AC**: Quick-start guide is available for team use

---

## Acceptance Criteria Summary

### Overall Story Completion Criteria:
✅ **All microservices (ASR, LLM, TTS, Core) are running and healthy**
✅ **End-to-end pipeline test passes successfully**  
✅ **Service intercommunication is validated**
✅ **Development workflow supports code changes and debugging**
✅ **System performance meets baseline requirements**
✅ **Documentation is complete and actionable**

### Success Metrics:
- **Service Health**: 4/4 services showing healthy status
- **Test Coverage**: E2E test passes with 100% success rate
- **Response Time**: < 1 second for health checks, < 700ms for voice pipeline
- **Resource Usage**: < 4GB RAM, < 50% CPU under normal load
- **Development Efficiency**: Code changes reflect within 30 seconds

### Failure Recovery:
If any task fails, refer to troubleshooting steps in `README.md` and:
1. Check Docker logs: `docker-compose logs [service-name]`
2. Verify model files are present and accessible
3. Confirm network ports are not conflicting
4. Validate configuration file syntax and values
5. Ensure sufficient system resources are available

---

**Environment Setup Complete**: When all checkboxes are completed, the OpenSIPS AI Voice Connector development environment is ready for feature development, testing, and deployment.

---

## Dev Agent Record

### Agent Model Used
- Claude Sonnet 4 (claude-sonnet-4-20250514)

### Debug Log References
- Initial story implementation started
- Prerequisites validation completed (Docker 28.3.0, Python 3.10.11, 16GB RAM, 53GB disk)
- Model directory structure created successfully
- Configuration file validated and corrected for proper port mapping
- ASR and TTS service containers built successfully
- LLM service build in progress (large PyTorch dependencies)
- Development environment validation script created

### Completion Notes List
- Prerequisites Validation: ✅ COMPLETED
  - Docker and Docker Compose verified (28.3.0, v2.38.1)
  - Python 3.10.11 installation validated
  - System resources confirmed (16GB RAM, 53GB free disk)
  - Required ports available
- Phase 1 Model Setup: ✅ PARTIALLY COMPLETED
  - Directory structure created (models/vosk, models/llm, models/piper, logs)
  - Configuration file corrected for proper service port mapping
  - Model files need to be downloaded separately
- Phase 2 Docker Services: ✅ PARTIALLY COMPLETED
  - ASR service container built successfully
  - TTS service container built successfully  
  - LLM service build in progress (large dependencies)
  - Import issues identified in services (missing common_pb2)

### File List
- DEVELOPMENT_ENVIRONMENT_SETUP_STORY.md (this file)
- validate_dev_env.py (environment validation script)
- models/ directory structure created
- services/*/Dockerfile (updated for development)
- config/app.ini (corrected port configuration)

### Change Log
- Started systematic implementation of development environment setup
- Completed prerequisites validation successfully
- Created model directory structure
- Fixed port configuration mismatches in config/app.ini
- Built ASR and TTS service containers successfully
- Identified and documented import issues in services
- Created development environment validation script

### Issues Identified
1. Service import issues: Missing common_pb2 module in proto files
2. LLM service has large PyTorch dependencies causing long build times
3. Model files need to be downloaded separately for full functionality
4. Health check mechanisms need grpc-health-probe installation

### Next Steps for Full Completion
1. Fix service import issues (add common proto files)
2. Complete LLM service build or create lightweight version for development
3. Download required model files (Vosk, LLaMA, Piper)
4. Test end-to-end service communication
5. Optimize Docker builds for development workflow

### Status
- Partially Completed (Core infrastructure ready, services need fixes)