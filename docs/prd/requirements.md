# Requirements

### Functional

**FR1:** The system must initiate outbound SIP calls using OpenSIPS to target IVR systems under test  
**FR2:** The system must send DTMF tones during calls to navigate IVR menu options  
**FR3:** The system must convert text prompts to speech using TTS service and play them to IVR  
**FR4:** The system must capture and transcribe IVR audio responses using ASR service  
**FR5:** The system must perform basic intent recognition on IVR responses using Turkish BERT  
**FR6:** The system must execute simple test scenarios step-by-step  
**FR7:** The system must provide a simple web interface for managing test scenarios  
**FR8:** The system must log call interactions and test results  
**FR9:** The system must validate test outcomes and mark pass/fail status  
**FR10:** The system must handle call failures and timeout scenarios gracefully

### Non Functional

**NFR1:** Test scenarios must complete within configurable timeouts  
**NFR2:** ASR transcription accuracy must be sufficient for intent recognition (>85%)  
**NFR3:** TTS audio quality must be clear for IVR system processing  
**NFR4:** The system must handle basic call volumes (5-10 concurrent calls)  
**NFR5:** Test results must be stored with basic logging  
**NFR6:** Web interface response times must be under 3 seconds
