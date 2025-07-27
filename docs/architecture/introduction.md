# Introduction

This document outlines the architectural approach for enhancing the OpenSIPS AI Voice Connector with IVR Flow Automation System capabilities. Its primary goal is to serve as the guiding architectural blueprint for AI-driven development of new features while ensuring seamless integration with the existing system.

**Relationship to Existing Architecture:**
This document supplements existing project architecture by defining how new components will integrate with current systems. Where conflicts arise between new and existing patterns, this document provides guidance on maintaining consistency while implementing enhancements.

### Existing Project Analysis

**Current Project State:**
- **Primary Purpose:** Real-time AI voice processing system for telephony applications with sub-700ms latency
- **Current Tech Stack:** Python 3.9+, gRPC microservices (ASR/Vosk, LLM/LLaMA, TTS/Piper), OpenSIPS, Docker, Pipecat framework
- **Architecture Style:** Microservices architecture with gRPC communication and Docker containerization
- **Deployment Method:** Docker Compose with health checks and service dependency management

**Available Documentation:**
- Existing README.md with comprehensive project structure
- Docker compose configurations for dev/prod environments
- gRPC service implementations and protobuf definitions
- Comprehensive testing framework with pytest

**Identified Constraints:**
- Must maintain existing ASR/TTS service functionality
- CPU-only deployment requirement (no GPU dependencies)
- Existing OpenSIPS integration must be preserved during transformation
- Current service port allocation and network configuration
