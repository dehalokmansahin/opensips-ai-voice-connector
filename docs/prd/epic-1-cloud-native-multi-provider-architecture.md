# Epic 1: Cloud-Native Multi-Provider Architecture

**Epic Goal**: Transform the OpenSIPS AI Voice Connector into a cloud-native, multi-provider system that supports GCP deployment, Twilio telephony, Ollama LLMs, and Faster-whisper STT while maintaining full backward compatibility.

**Integration Requirements**: All changes must be additive, preserving existing OpenSIPS functionality. Provider selection must be configuration-driven. Cloud deployment must be optional.

## Story 1.1: Multi-Provider Transport Architecture

As a system architect,
I want to implement a transport factory pattern,
so that the system can dynamically select between OpenSIPS and Twilio telephony providers.

### Acceptance Criteria
1. Create abstract base transport class defining common interface
2. Refactor existing OpenSIPS transport to implement base class
3. Implement Twilio transport following pipecat/examples/twilio-chatbot pattern
4. Create transport factory that selects provider based on configuration
5. Add configuration schema for multi-provider transport settings

### Integration Verification
- IV1: Existing OpenSIPS calls continue to work with no configuration changes
- IV2: Transport factory correctly instantiates OpenSIPS transport when configured
- IV3: No performance degradation in existing OpenSIPS call handling

## Story 1.2: Twilio Telephony Integration

As a telephony user,
I want to make calls through Twilio,
so that I can use cloud-based telephony without SIP infrastructure.

### Acceptance Criteria
1. Implement TwilioFrameSerializer for audio handling
2. Create FastAPI WebSocket endpoint for Twilio Media Streams
3. Handle Twilio-specific audio format (8kHz PCMU)
4. Implement Twilio call control (answer, hangup, transfer)
5. Add Twilio configuration section to INI file

### Integration Verification
- IV1: System can handle both Twilio and OpenSIPS calls simultaneously
- IV2: Audio pipeline processes both 8kHz (Twilio) and higher sample rates (OpenSIPS)
- IV3: Barge-in interruption works correctly with Twilio calls

## Story 1.3: Ollama LLM Service Integration

As an AI developer,
I want to use Ollama for LLM services,
so that I can deploy various open-source models locally or in cloud.

### Acceptance Criteria
1. Create OllamaLLMService implementing Pipecat LLM interface
2. Support Ollama REST API for model management
3. Implement streaming responses compatible with pipeline
4. Add Ollama model configuration (model name, parameters)
5. Create service factory for LLM provider selection

### Integration Verification
- IV1: Existing Llama WebSocket service continues to function
- IV2: Service factory correctly selects provider based on configuration
- IV3: Pipeline maintains same latency targets with Ollama

## Story 1.4: Faster-whisper STT Integration

As a voice application user,
I want improved speech recognition accuracy,
so that the system better understands my speech input.

### Acceptance Criteria
1. Create FasterWhisperSTTService implementing Pipecat STT interface
2. Support local Faster-whisper model loading
3. Implement audio buffering for Faster-whisper processing
4. Add language and model size configuration
5. Extend service factory for STT provider selection

### Integration Verification
- IV1: Vosk STT service remains functional for existing deployments
- IV2: Audio pipeline handles both streaming (Vosk) and buffered (Faster-whisper) STT
- IV3: VAD and interruption detection work with both STT providers

## Story 1.5: Cloud-Ready Containerization

As a DevOps engineer,
I want properly structured containers for cloud deployment,
so that services can be deployed independently in Kubernetes.

### Acceptance Criteria
1. Create multi-stage Dockerfile for main application
2. Separate Dockerfile for each AI service (Ollama, Faster-whisper)
3. Implement health check endpoints for each service
4. Add readiness and liveness probes
5. Create docker-compose.cloud.yml for cloud-compatible local testing

### Integration Verification
- IV1: Existing docker-compose.dev.yml continues to work
- IV2: All services start correctly with new container structure
- IV3: Health checks accurately reflect service status

## Story 1.6: GKE Deployment Configuration

As a cloud architect,
I want Kubernetes manifests for GKE deployment,
so that the system can run in Google Kubernetes Engine.

### Acceptance Criteria
1. Create Kubernetes deployments for each service
2. Configure services and ingress for external access
3. Implement ConfigMaps for configuration management
4. Setup Secrets for sensitive data (API keys)
5. Create HorizontalPodAutoscaler for main application

### Integration Verification
- IV1: All services communicate correctly in Kubernetes networking
- IV2: RTP ports properly exposed for OpenSIPS in Kubernetes
- IV3: WebSocket connections stable through ingress

## Story 1.7: Cloud Run Serverless Deployment

As a platform engineer,
I want Cloud Run deployment option,
so that the system can run in a serverless environment for Twilio-only deployments.

### Acceptance Criteria
1. Create Cloud Run service definitions
2. Implement request-based scaling configuration
3. Setup Cloud Build for automated deployment
4. Configure environment variables for Cloud Run
5. Document limitations (no OpenSIPS in serverless)

### Integration Verification
- IV1: Twilio calls work correctly in Cloud Run
- IV2: Cold start times within acceptable limits (<5 seconds)
- IV3: WebSocket connections maintain stability

## Story 1.8: Configuration Management Enhancement

As a system administrator,
I want unified configuration for multi-provider setup,
so that I can easily manage provider selection and settings.

### Acceptance Criteria
1. Extend INI configuration schema for multiple providers
2. Implement environment variable overrides for cloud deployment
3. Create provider selection logic based on configuration
4. Add configuration validation on startup
5. Document all configuration options

### Integration Verification
- IV1: Existing single-provider configurations continue to work
- IV2: Provider selection correctly interprets configuration
- IV3: Environment variables properly override INI settings

## Story 1.9: Monitoring and Observability

As a operations engineer,
I want cloud-native monitoring and logging,
so that I can track system health and debug issues in production.

### Acceptance Criteria
1. Integrate with Google Cloud Operations (formerly Stackdriver)
2. Implement structured logging with correlation IDs
3. Add custom metrics for call quality and latency
4. Create dashboards for system monitoring
5. Setup alerts for critical issues

### Integration Verification
- IV1: Existing console logging remains functional
- IV2: Metrics accurately reflect system performance
- IV3: Log aggregation works across all services

## Story 1.10: Integration Testing and Documentation

As a developer,
I want comprehensive tests and documentation,
so that I can understand and verify the multi-provider system.

### Acceptance Criteria
1. Create integration tests for each provider combination
2. Add load testing for cloud deployment
3. Update README with cloud deployment instructions
4. Create provider-specific configuration guides
5. Document migration path from monolithic to cloud

### Integration Verification
- IV1: All existing tests continue to pass
- IV2: New tests cover provider switching scenarios
- IV3: Documentation accurately reflects both legacy and new deployments