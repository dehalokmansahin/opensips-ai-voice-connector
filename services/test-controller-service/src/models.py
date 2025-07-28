"""
Pydantic Models for Test Controller Service API
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field

class TestExecutionStatus(str, Enum):
    """Test execution status enumeration"""
    PENDING = "pending"
    INITIALIZING = "initializing"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"

class StepType(str, Enum):
    """Test step type enumeration"""
    CALL_INITIATE = "call_initiate"
    DTMF_SEND = "dtmf_send"
    TTS_SPEAK = "tts_speak"
    ASR_LISTEN = "asr_listen"
    INTENT_VALIDATE = "intent_validate"
    CALL_TERMINATE = "call_terminate"

# Test Scenario Models
class TestStep(BaseModel):
    """Individual test step definition"""
    step_id: str = Field(..., description="Unique step identifier")
    step_type: StepType = Field(..., description="Type of test step")
    description: str = Field(..., description="Human-readable step description")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Step-specific parameters")
    timeout_seconds: Optional[int] = Field(default=30, description="Step timeout")
    retry_attempts: Optional[int] = Field(default=1, description="Number of retry attempts")

class TestScenarioRequest(BaseModel):
    """Request to create a new test scenario"""
    name: str = Field(..., description="Test scenario name")
    description: str = Field(..., description="Test scenario description")
    target_number: str = Field(..., description="Phone number to call for testing")
    caller_id: str = Field(default="IVR_TEST", description="Caller ID to display")
    steps: List[TestStep] = Field(..., description="List of test steps")
    timeout_seconds: Optional[int] = Field(default=300, description="Overall scenario timeout")
    retry_policy: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Retry configuration")

class TestScenarioResponse(BaseModel):
    """Response after creating a test scenario"""
    scenario_id: str = Field(..., description="Generated scenario ID")
    name: str = Field(..., description="Test scenario name")
    description: str = Field(..., description="Test scenario description")
    target_number: str = Field(..., description="Target phone number")
    step_count: int = Field(..., description="Number of test steps")
    created_at: datetime = Field(..., description="Creation timestamp")

# Test Execution Models
class TestExecutionRequest(BaseModel):
    """Request to start a test execution"""
    scenario_id: str = Field(..., description="Test scenario to execute")
    execution_name: Optional[str] = Field(default=None, description="Custom execution name")
    parameters: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Execution parameters")
    timeout_override: Optional[int] = Field(default=None, description="Override scenario timeout")

class StepExecutionResult(BaseModel):
    """Result of a single test step execution"""
    step_id: str = Field(..., description="Step identifier")
    status: str = Field(..., description="Step execution status")
    start_time: datetime = Field(..., description="Step start time")
    end_time: Optional[datetime] = Field(default=None, description="Step end time")
    duration_ms: Optional[int] = Field(default=None, description="Step duration in milliseconds")
    output: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Step output data")
    error_message: Optional[str] = Field(default=None, description="Error message if failed")

class TestExecutionResponse(BaseModel):
    """Response with test execution status"""
    execution_id: str = Field(..., description="Unique execution ID")
    scenario_id: str = Field(..., description="Test scenario ID")
    status: TestExecutionStatus = Field(..., description="Current execution status")
    start_time: datetime = Field(..., description="Execution start time")
    end_time: Optional[datetime] = Field(default=None, description="Execution end time")
    duration_ms: Optional[int] = Field(default=None, description="Total execution duration")
    current_step: Optional[str] = Field(default=None, description="Currently executing step")
    progress: Dict[str, Any] = Field(default_factory=dict, description="Execution progress info")
    step_results: List[StepExecutionResult] = Field(default_factory=list, description="Individual step results")
    call_id: Optional[str] = Field(default=None, description="Associated call ID")
    error_message: Optional[str] = Field(default=None, description="Error message if failed")

# Call Control Models
class DTMFTiming(BaseModel):
    """DTMF timing configuration"""
    tone_duration_ms: int = Field(default=150, description="Duration of each tone")
    inter_tone_gap_ms: int = Field(default=75, description="Gap between tones")
    post_sequence_delay_ms: int = Field(default=500, description="Delay after sequence")

class CallControlRequest(BaseModel):
    """Request for call control operations"""
    action: str = Field(..., description="Control action (dtmf, hangup, etc.)")
    dtmf_sequence: Optional[str] = Field(default=None, description="DTMF sequence to send")
    timing: Optional[DTMFTiming] = Field(default_factory=DTMFTiming, description="DTMF timing configuration")
    parameters: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional parameters")

class CallControlResponse(BaseModel):
    """Response from call control operation"""
    call_id: str = Field(..., description="Call ID")
    action: str = Field(..., description="Executed action")
    status: str = Field(..., description="Operation status")
    timestamp: datetime = Field(..., description="Operation timestamp")
    details: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional details")

# Service Status Models
class ServiceHealthResponse(BaseModel):
    """Service health check response"""
    status: str = Field(..., description="Service status")
    service: str = Field(..., description="Service name")
    version: str = Field(..., description="Service version")
    timestamp: datetime = Field(default_factory=datetime.now, description="Health check timestamp")
    dependencies: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Dependency health status")

# Database Models (for internal use)
class TestScenario(BaseModel):
    """Internal test scenario model"""
    id: str = Field(..., description="Scenario ID")
    name: str = Field(..., description="Scenario name") 
    description: str = Field(..., description="Scenario description")
    target_number: str = Field(..., description="Target phone number")
    caller_id: str = Field(..., description="Caller ID")
    steps: List[Dict[str, Any]] = Field(..., description="Test steps as JSON")
    timeout_seconds: int = Field(..., description="Scenario timeout")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    is_active: bool = Field(default=True, description="Whether scenario is active")

class TestExecution(BaseModel):
    """Internal test execution model"""
    id: str = Field(..., description="Execution ID")
    scenario_id: str = Field(..., description="Associated scenario ID")
    status: str = Field(..., description="Execution status")
    start_time: datetime = Field(..., description="Start timestamp")
    end_time: Optional[datetime] = Field(default=None, description="End timestamp")
    call_id: Optional[str] = Field(default=None, description="Associated call ID")
    step_results: List[Dict[str, Any]] = Field(default_factory=list, description="Step results as JSON")
    error_message: Optional[str] = Field(default=None, description="Error message")
    execution_log: Optional[str] = Field(default=None, description="Detailed execution log")