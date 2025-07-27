# Epic 2: Core AI Pipeline Integration

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
