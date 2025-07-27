# Epic 1: OpenSIPS Outbound Call Foundation

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
