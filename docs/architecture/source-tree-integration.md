# Source Tree Integration

### New File Organization

```plaintext
opensips-ai-voice-connector/
├── core/                           # Existing core - preserved
│   ├── grpc_clients/               # Existing gRPC clients
│   │   ├── asr_client.py          # Existing - preserved
│   │   ├── tts_client.py          # Existing - preserved
│   │   ├── test_controller_client.py  # NEW - Test Controller client
│   │   └── intent_client.py       # NEW - Intent Recognition client
│   ├── opensips/                   # Existing OpenSIPS integration
│   │   ├── integration.py         # Existing - modified for outbound calls
│   │   ├── outbound_call_manager.py # NEW - Outbound call management
│   │   └── dtmf_generator.py      # NEW - DTMF tone generation
│   ├── ivr_testing/               # NEW - IVR testing core
│   │   ├── __init__.py
│   │   ├── test_executor.py       # Test execution orchestration
│   │   ├── scenario_manager.py    # Test scenario management
│   │   └── result_processor.py    # Test result processing
│   └── web/                       # NEW - Web interface
│       ├── __init__.py
│       ├── app.py                 # FastAPI web application
│       ├── routers/               # API route handlers
│       │   ├── scenarios.py      # Test scenario endpoints
│       │   ├── executions.py     # Test execution endpoints
│       │   └── monitoring.py     # Real-time monitoring
│       └── static/                # Static web assets
├── services/                      # Existing services directory
│   ├── asr-service/              # Existing ASR service - preserved
│   ├── tts-service/              # Existing TTS service - preserved
│   ├── intent-service/           # NEW - Intent Recognition service
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── src/
│   │   │   ├── main.py
│   │   │   ├── intent_grpc_server.py
│   │   │   ├── turkish_bert_engine.py
│   │   │   └── intent_service_pb2.py
│   │   └── tests/
│   └── test-controller-service/  # NEW - Test Controller service
│       ├── Dockerfile
│       ├── requirements.txt
│       ├── src/
│       │   ├── main.py
│       │   ├── test_controller_grpc_server.py
│       │   ├── scenario_executor.py
│       │   └── test_controller_pb2.py
│       └── tests/
├── shared/                       # Existing shared protobuf
│   └── proto/                    # Protobuf definitions
│       ├── intent_service.proto  # NEW - Intent service definitions
│       └── test_controller.proto # NEW - Test Controller definitions
├── config/                       # Existing configuration
│   ├── app.ini                   # Existing - extended for IVR testing
│   └── ivr_testing.ini          # NEW - IVR-specific configuration
├── data/                         # NEW - Test data and databases
│   ├── test_scenarios.db         # SQLite database for test scenarios
│   ├── training_data/            # Intent recognition training data
│   └── test_results/             # Test execution results
└── docker-compose.yml           # Existing - modified for new services
```

### Integration Guidelines
**File Naming:** Maintain existing Python module naming conventions (snake_case), follow established pattern for service names with hyphen separation

**Folder Organization:** Preserve existing service structure, add new services following established pattern, extend core modules without disrupting existing functionality

**Import/Export Patterns:** Maintain existing relative import patterns within core, extend service registry for new gRPC services, preserve existing protobuf generation workflow
