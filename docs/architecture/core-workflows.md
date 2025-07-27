# Core Workflows

The following sequence diagrams illustrate critical system workflows for voice call processing and banking integration.

### Card Delivery Inquiry Workflow

```mermaid
sequenceDiagram
    participant C as Banking Customer
    participant O as OpenSIPS
    participant AVC as AI Voice Connector
    participant SM as Session Manager
    participant P as Pipecat Orchestrator
    participant VAD as VAD Service
    participant ASR as ASR Service
    participant LLM as LLM Service
    participant CS as Context Store
    participant BS as Banking Service
    participant TTS as TTS Service
    participant BA as Banking APIs
    
    C->>O: SIP INVITE (voice call)
    O->>AVC: Route call to AI Voice Connector
    AVC->>SM: Create session (phone, SIP call ID)
    SM->>CS: Initialize conversation context
    AVC->>P: Start audio pipeline
    
    Note over C,TTS: Welcome message and audio processing
    P->>TTS: Generate welcome message
    TTS-->>P: Audio stream (PCM)
    P-->>AVC: Audio response
    AVC-->>O: RTP audio stream
    O-->>C: Welcome audio
    
    Note over C,BS: User query processing
    C->>O: RTP audio (user speech)
    O->>AVC: Forward audio stream
    AVC->>P: Process incoming audio
    P->>VAD: Detect speech segments
    VAD-->>P: Speech boundaries
    P->>ASR: Convert speech to text
    ASR-->>P: "Where is my credit card?"
    
    P->>LLM: Process user query + context
    LLM->>CS: Retrieve conversation context
    LLM->>BS: Classify intent: card_delivery_inquiry
    BS->>BA: Authenticate customer
    BA-->>BS: Customer verified
    BS->>BA: Query card delivery status
    BA-->>BS: Card shipped, tracking #12345
    BS-->>LLM: Delivery information
    LLM->>CS: Update conversation context
    LLM-->>P: Response text
    
    P->>TTS: Generate response audio
    TTS-->>P: Audio stream
    P-->>AVC: Response audio
    AVC-->>O: RTP audio
    O-->>C: "Your card was shipped yesterday..."
    
    Note over C,SM: Call completion
    C->>O: SIP BYE (end call)
    O->>AVC: Call termination
    AVC->>SM: End session
    SM->>CS: Clean up context (with TTL)
```

### Barge-in Interruption Workflow

```mermaid
sequenceDiagram
    participant C as Banking Customer
    participant AVC as AI Voice Connector
    participant P as Pipecat Orchestrator
    participant VAD as VAD Service
    participant ASR as ASR Service
    participant TTS as TTS Service
    
    Note over C,TTS: System is speaking
    TTS->>P: Streaming TTS audio
    P->>AVC: Outbound audio stream
    
    parallel
        P->>VAD: Monitor for speech during TTS
    and
        C->>AVC: User interruption (RTP audio)
        AVC->>P: Incoming audio stream
        P->>VAD: Process interruption audio
        VAD->>P: Speech detected (confidence > threshold)
    end
    
    P->>TTS: STOP current synthesis
    TTS-->>P: Synthesis halted
    P->>ASR: Process interruption speech
    ASR-->>P: "Wait, I have a question"
    
    Note over P: Context preserved, ready for new query
    P->>VAD: Reset for new speech detection
```
