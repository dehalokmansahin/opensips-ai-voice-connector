# Data Models and Schema Changes

### New Data Models

#### Test Scenario Model
**Purpose:** Define automated IVR test scenarios with step-by-step execution plans  
**Integration:** Independent from existing voice assistant data, stored in new SQLite database

**Key Attributes:**
- `scenario_id`: INTEGER PRIMARY KEY - Unique test scenario identifier
- `name`: TEXT NOT NULL - Human-readable scenario name
- `description`: TEXT - Detailed scenario description
- `target_phone`: TEXT NOT NULL - IVR system phone number to test
- `steps`: JSON - Array of test steps with prompts, expected intents, DTMF sequences
- `timeout_seconds`: INTEGER DEFAULT 300 - Scenario execution timeout
- `created_at`: TIMESTAMP - Creation timestamp
- `updated_at`: TIMESTAMP - Last modification timestamp

**Relationships:**
- **With Existing:** None (completely independent from current voice assistant data)
- **With New:** One-to-many with TestExecution, one-to-many with TestStep

#### Test Execution Model
**Purpose:** Track individual test scenario execution instances and results  
**Integration:** Links test scenarios to actual execution outcomes

**Key Attributes:**
- `execution_id`: INTEGER PRIMARY KEY - Unique execution identifier  
- `scenario_id`: INTEGER FOREIGN KEY - References test scenario
- `status`: TEXT CHECK (status IN ('running', 'completed', 'failed', 'timeout')) - Execution status
- `start_time`: TIMESTAMP - Execution start time
- `end_time`: TIMESTAMP - Execution completion time
- `call_id`: TEXT - OpenSIPS call identifier for correlation
- `final_result`: TEXT CHECK (final_result IN ('pass', 'fail')) - Overall test result
- `error_message`: TEXT - Error details if execution failed

#### Intent Training Data Model
**Purpose:** Store and manage Turkish BERT training data for IVR-specific intents
**Integration:** Supports intent recognition service training and validation

**Key Attributes:**
- `training_id`: INTEGER PRIMARY KEY - Training data identifier
- `text_sample`: TEXT NOT NULL - IVR response text sample
- `intent_label`: TEXT NOT NULL - Assigned intent classification
- `confidence_threshold`: REAL DEFAULT 0.85 - Minimum confidence for this intent
- `source`: TEXT - Data source (manual, recorded, synthetic)
- `validation_status`: TEXT CHECK (validation_status IN ('pending', 'validated', 'rejected')) - Training data quality
- `created_at`: TIMESTAMP - Data creation timestamp

### Schema Integration Strategy
**Database Changes Required:**
- **New Tables:** test_scenarios, test_executions, step_executions, intent_training_data
- **Modified Tables:** None (completely isolated from existing system)
- **New Indexes:** scenario_id, execution_id, call_id, intent_label for performance
- **Migration Strategy:** New SQLite database file(s), no impact on existing data

**Backward Compatibility:**
- No changes to existing voice assistant data structures
- Complete isolation of test-related data from conversation data
- Existing services (ASR, TTS) continue operating without schema awareness
- New services operate on new database schemas only
