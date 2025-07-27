# Epic 2: Simple Test Framework

**Epic Goal:** Implement basic test scenario execution with intent recognition for validating IVR responses.

### Story 2.1: Turkish BERT Intent Recognition
**As a** test validator,  
**I want** intent recognition on transcribed IVR responses,  
**so that** I can validate expected behaviors.

**Acceptance Criteria:**
1. Turkish BERT model integration (dbmdz/bert-base-turkish-uncased)
2. Basic intent classification for common IVR responses
3. Pass/fail determination based on expected intents
4. Simple training data for IVR-specific responses

### Story 2.2: Test Scenario Execution
**As a** test runner,  
**I want** to execute test scenarios step-by-step,  
**so that** I can automate IVR testing workflows.

**Acceptance Criteria:**
1. Simple test scenario definition format
2. Step-by-step execution with audio prompts and responses
3. Conditional logic based on IVR responses
4. Test result reporting with pass/fail status
