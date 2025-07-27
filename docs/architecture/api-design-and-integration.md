# API Design and Integration

### API Integration Strategy
**API Integration Strategy:** Extend existing gRPC microservices pattern with new Test Controller and Intent Recognition services, maintaining consistency with current ASR/TTS service APIs

**Authentication:** Leverage existing service-to-service communication patterns, no authentication between internal services (consistent with current architecture)

**Versioning:** Follow existing protobuf versioning approach, new services start at v1 with backward compatibility considerations

### New API Endpoints

#### Test Controller gRPC Service

##### StartTestExecution
- **Method:** POST
- **Endpoint:** `TestController/StartTestExecution`
- **Purpose:** Initiate automated IVR test scenario execution
- **Integration:** Creates new test execution record, initiates OpenSIPS outbound call

**Request:**
```protobuf
message StartTestExecutionRequest {
    int32 scenario_id = 1;
    map<string, string> execution_params = 2;
    int32 timeout_override_seconds = 3;
}
```

**Response:**
```protobuf
message StartTestExecutionResponse {
    int32 execution_id = 1;
    string call_id = 2;
    TestExecutionStatus status = 3;
    int64 start_timestamp = 4;
}
```

#### Intent Recognition gRPC Service

##### ClassifyIntent
- **Method:** POST
- **Endpoint:** `IntentRecognition/ClassifyIntent`
- **Purpose:** Classify single IVR response text into intent categories
- **Integration:** Receives ASR transcription, returns intent classification for test validation

**Request:**
```protobuf
message ClassifyIntentRequest {
    string text = 1;
    float confidence_threshold = 2;
    repeated string candidate_intents = 3;
}
```

**Response:**
```protobuf
message ClassifyIntentResponse {
    string intent = 1;
    float confidence = 2;
    repeated IntentScore alternative_intents = 3;
    bool meets_threshold = 4;
}
```
