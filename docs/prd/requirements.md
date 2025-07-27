# Requirements

### Functional

**FR1:** The system must process incoming SIP/RTP audio calls through OpenSIPS integration
**FR2:** The system must convert PCMU/8000 audio to PCM 16-bit, 16kHz for internal processing
**FR3:** The system must detect speech segments using VAD (Silero) with configurable thresholds
**FR4:** The system must convert speech to text using ASR (VOSK or Faster-Whisper)
**FR5:** The system must process user queries through LLM (LLaMA or OpenAI GPT-4o) via gRPC interfaces
**FR6:** The system must generate voice responses using TTS (Piper or ElevenLabs)
**FR7:** The system must support real-time barge-in/interruption capabilities
**FR8:** The system must handle "Card Delivery Status Inquiry" as the MVP pilot scenario
**FR9:** The system must maintain session context and conversation memory
**FR10:** The system must encode TTS output back to PCMU/8000 for SIP/RTP transmission

### Non Functional

**NFR1:** End-to-end response latency must not exceed 700ms (p95)
**NFR2:** TTS first audio output must be delivered within 200ms
**NFR3:** ASR first token must be available within 250ms
**NFR4:** LLM first token response must be generated within 300ms
**NFR5:** The system must handle 20ms RTP packet processing (~160 bytes each)
**NFR6:** The system must maintain high availability for production banking environments
**NFR7:** The system must log all pipeline stages with session IDs for monitoring using gRPC-based telemetry
**NFR8:** The system must support both on-premise and cloud deployment options
