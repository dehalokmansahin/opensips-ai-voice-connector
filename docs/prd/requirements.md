# Requirements

## Functional

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

## Non Functional

- **NFR1**: The system shall maintain existing performance targets (≤1.5s round-trip, ≤300ms interruption response)
- **NFR2**: The system shall support horizontal scaling in GKE with autoscaling policies
- **NFR3**: The system shall maintain backward compatibility with existing OpenSIPS deployments
- **NFR4**: The system shall support 8kHz audio for Twilio telephony and existing sample rates for OpenSIPS
- **NFR5**: The system shall use Cloud-native logging and monitoring (Cloud Operations)
- **NFR6**: The system shall support zero-downtime deployments using rolling updates
- **NFR7**: The system shall maintain existing Turkish language support across all providers
- **NFR8**: The system shall use Cloud Secrets Manager for sensitive configuration

## Compatibility Requirements

- **CR1**: Existing OpenSIPS configuration and deployment must continue to work without modification
- **CR2**: Existing WebSocket interfaces for AI services must remain compatible
- **CR3**: Existing configuration file structure (INI format) must be maintained with extensions
- **CR4**: Existing Docker Compose development workflow must continue to function