# Tech Stack Alignment

### Existing Technology Stack

| Category | Current Technology | Version | Usage in Enhancement | Notes |
|----------|-------------------|---------|---------------------|-------|
| **Core Language** | Python | 3.9+ | All services and core application | Maintained |
| **Service Communication** | gRPC/protobuf | 1.60.0/4.25.1 | ASR, TTS, Intent Recognition, Test Controller | Existing pattern extended |
| **Web Framework** | FastAPI | 0.108.0 | Test management web interface | Existing pattern reused |
| **Containerization** | Docker/Docker Compose | Latest | All services including new Intent & Test Controller | Existing pattern extended |
| **Audio Processing** | numpy, soundfile, scipy | 2.2.5, 0.12.1, 1.15.2 | RTP audio handling for IVR calls | Maintained |
| **ASR Engine** | Vosk | 0.3.45 | IVR response transcription | Maintained as-is |
| **TTS Engine** | Piper | 1.2.0 | IVR prompt generation | Maintained as-is |
| **SIP/Telephony** | OpenSIPS | Custom integration | **Modified for outbound calls** | Reconfigured |
| **Configuration** | configparser, pydantic | 6.0.0, 2.10.4 | Test scenario and service config | Maintained |
| **Testing** | pytest suite | 8.2.1+ | Extended for IVR test validation | Extended |

### New Technology Additions

| Technology | Version | Purpose | Rationale | Integration Method |
|------------|---------|---------|-----------|-------------------|
| **Turkish BERT** | dbmdz/bert-base-turkish-uncased | Intent classification from IVR responses | CPU-optimized, Turkish language support for IVR testing | New gRPC service (port 50054) |
| **Transformers** | Latest stable | BERT model loading and inference | Required for Turkish BERT | New Intent Recognition service |
| **SQLite** | Built-in Python | Test scenarios, results, intent training data | Lightweight, no additional infrastructure | New database files |
| **ONNX Runtime** | 1.19.2 | CPU-optimized BERT inference | Already in requirements, optimize Turkish BERT | Existing dependency |
