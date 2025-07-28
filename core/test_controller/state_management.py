"""
Test State Management for IVR Test Execution
Tracks test scenario progress and step execution state
"""

import logging
from enum import Enum
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

class TestState(Enum):
    """Overall test execution state"""
    PENDING = "pending"
    INITIALIZING = "initializing"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"

class StepState(Enum):
    """Individual test step state"""
    PENDING = "pending"
    EXECUTING = "executing"
    WAITING_RESPONSE = "waiting_response"
    VALIDATING = "validating"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"

@dataclass
class TestStepResult:
    """Result of a single test step execution"""
    step_id: str
    step_number: int
    action: str
    expected_intent: Optional[str] = None
    actual_intent: Optional[str] = None
    confidence: Optional[float] = None
    transcribed_text: Optional[str] = None
    validation_passed: bool = False
    error_message: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_ms: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage"""
        return {
            "step_id": self.step_id,
            "step_number": self.step_number,
            "action": self.action,
            "expected_intent": self.expected_intent,
            "actual_intent": self.actual_intent,
            "confidence": self.confidence,
            "transcribed_text": self.transcribed_text,
            "validation_passed": self.validation_passed,
            "error_message": self.error_message,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_ms": self.duration_ms
        }

@dataclass
class TestExecutionState:
    """Complete test execution state"""
    test_id: str
    scenario_id: str
    call_id: Optional[str] = None
    state: TestState = TestState.PENDING
    current_step: int = 0
    total_steps: int = 0
    step_results: List[TestStepResult] = field(default_factory=list)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage"""
        return {
            "test_id": self.test_id,
            "scenario_id": self.scenario_id,
            "call_id": self.call_id,
            "state": self.state.value,
            "current_step": self.current_step,
            "total_steps": self.total_steps,
            "step_results": [r.to_dict() for r in self.step_results],
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "error_message": self.error_message,
            "metadata": self.metadata
        }

class TestStateManager:
    """Manages test execution state throughout the test lifecycle"""
    
    def __init__(self):
        self._states: Dict[str, TestExecutionState] = {}
        self._active_tests: Dict[str, str] = {}  # call_id -> test_id mapping
        
    def create_test_state(self, test_id: str, scenario_id: str, total_steps: int) -> TestExecutionState:
        """Create a new test execution state"""
        state = TestExecutionState(
            test_id=test_id,
            scenario_id=scenario_id,
            total_steps=total_steps,
            start_time=datetime.now()
        )
        self._states[test_id] = state
        logger.info(f"Created test state for test_id={test_id}, scenario_id={scenario_id}")
        return state
    
    def get_state(self, test_id: str) -> Optional[TestExecutionState]:
        """Get test execution state by test ID"""
        return self._states.get(test_id)
    
    def get_state_by_call_id(self, call_id: str) -> Optional[TestExecutionState]:
        """Get test execution state by call ID"""
        test_id = self._active_tests.get(call_id)
        if test_id:
            return self._states.get(test_id)
        return None
    
    def update_state(self, test_id: str, state: TestState, error_message: Optional[str] = None):
        """Update test execution state"""
        test_state = self._states.get(test_id)
        if test_state:
            test_state.state = state
            if error_message:
                test_state.error_message = error_message
            if state in [TestState.COMPLETED, TestState.FAILED, TestState.CANCELLED, TestState.TIMEOUT]:
                test_state.end_time = datetime.now()
            logger.info(f"Updated test state for test_id={test_id}: {state.value}")
    
    def associate_call(self, test_id: str, call_id: str):
        """Associate a call ID with a test execution"""
        test_state = self._states.get(test_id)
        if test_state:
            test_state.call_id = call_id
            self._active_tests[call_id] = test_id
            logger.info(f"Associated call_id={call_id} with test_id={test_id}")
    
    def advance_step(self, test_id: str) -> int:
        """Advance to the next test step"""
        test_state = self._states.get(test_id)
        if test_state and test_state.current_step < test_state.total_steps:
            test_state.current_step += 1
            logger.info(f"Advanced test_id={test_id} to step {test_state.current_step}/{test_state.total_steps}")
            return test_state.current_step
        return -1
    
    def add_step_result(self, test_id: str, step_result: TestStepResult):
        """Add a step execution result"""
        test_state = self._states.get(test_id)
        if test_state:
            # Calculate duration if times are set
            if step_result.start_time and step_result.end_time:
                delta = step_result.end_time - step_result.start_time
                step_result.duration_ms = int(delta.total_seconds() * 1000)
            
            test_state.step_results.append(step_result)
            logger.info(f"Added step result for test_id={test_id}, step={step_result.step_number}")
    
    def get_current_step_number(self, test_id: str) -> int:
        """Get the current step number for a test"""
        test_state = self._states.get(test_id)
        return test_state.current_step if test_state else 0
    
    def is_test_complete(self, test_id: str) -> bool:
        """Check if all steps have been executed"""
        test_state = self._states.get(test_id)
        if test_state:
            return test_state.current_step >= test_state.total_steps
        return False
    
    def cleanup_test(self, test_id: str):
        """Clean up test state after completion"""
        test_state = self._states.get(test_id)
        if test_state and test_state.call_id:
            self._active_tests.pop(test_state.call_id, None)
        self._states.pop(test_id, None)
        logger.info(f"Cleaned up test state for test_id={test_id}")
    
    def get_active_tests(self) -> List[str]:
        """Get list of active test IDs"""
        return [
            test_id for test_id, state in self._states.items()
            if state.state in [TestState.INITIALIZING, TestState.IN_PROGRESS]
        ]
    
    def get_test_summary(self, test_id: str) -> Dict[str, Any]:
        """Get summary of test execution"""
        test_state = self._states.get(test_id)
        if not test_state:
            return {}
        
        passed_steps = sum(1 for r in test_state.step_results if r.validation_passed)
        failed_steps = sum(1 for r in test_state.step_results if not r.validation_passed and r.error_message)
        
        return {
            "test_id": test_id,
            "scenario_id": test_state.scenario_id,
            "state": test_state.state.value,
            "progress": f"{test_state.current_step}/{test_state.total_steps}",
            "passed_steps": passed_steps,
            "failed_steps": failed_steps,
            "total_duration_ms": sum(r.duration_ms or 0 for r in test_state.step_results),
            "start_time": test_state.start_time.isoformat() if test_state.start_time else None,
            "end_time": test_state.end_time.isoformat() if test_state.end_time else None
        }