"""
Test Execution Manager for IVR Test Automation
Central orchestration for test scenario execution
"""

import asyncio
import logging
import uuid
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime

# TODO: Fix imports when integrated with full system
# from ..config.settings import Settings
# from ..grpc_clients import ServiceRegistry
# from ..utils.database import DatabaseManager, TestScenario, TestExecution
# from ..opensips.integration import OpenSIPSIntegration
from .test_session import TestExecutionSession, SessionConfig
from .state_management import TestStateManager, TestState

logger = logging.getLogger(__name__)

class TestExecutionManager:
    """Orchestrates test scenario execution and lifecycle management"""
    
    def __init__(self, 
                 settings: Any = None,
                 service_registry: Any = None,
                 opensips_integration: Any = None,
                 db_manager: Any = None):
        self.settings = settings
        self.service_registry = service_registry
        self.opensips_integration = opensips_integration
        self.db_manager = db_manager
        
        # State management
        self.state_manager = TestStateManager()
        self.active_sessions: Dict[str, TestExecutionSession] = {}
        
        # Event callbacks
        self.on_test_start: Optional[Callable] = None
        self.on_test_complete: Optional[Callable] = None
        self.on_test_error: Optional[Callable] = None
        self.on_step_complete: Optional[Callable] = None
        
        # Configuration
        self.max_concurrent_tests = 10
        self.default_session_config = SessionConfig(
            timeout_seconds=30,
            retry_attempts=3,
            dtmf_delay_ms=500,
            response_timeout_ms=5000,
            intent_confidence_threshold=0.80
        )
        
        # Background tasks
        self._cleanup_task: Optional[asyncio.Task] = None
        self._monitor_task: Optional[asyncio.Task] = None
        
    async def initialize(self):
        """Initialize the test execution manager"""
        logger.info("Initializing Test Execution Manager")
        
        # Verify services are available
        required_services = ['asr', 'tts', 'intent']
        for service in required_services:
            if not self.service_registry.is_service_healthy(service):
                raise Exception(f"Required service '{service}' is not healthy")
        
        # Start background tasks
        self._cleanup_task = asyncio.create_task(self._cleanup_completed_sessions())
        self._monitor_task = asyncio.create_task(self._monitor_test_timeouts())
        
        logger.info("Test Execution Manager initialized successfully")
    
    async def execute_scenario(self, 
                             scenario_id: str, 
                             phone_number: str,
                             config_overrides: Optional[Dict[str, Any]] = None) -> str:
        """Execute a test scenario"""
        try:
            # Check concurrent test limit
            if len(self.active_sessions) >= self.max_concurrent_tests:
                raise Exception(f"Maximum concurrent tests ({self.max_concurrent_tests}) reached")
            
            # Load scenario from database
            scenario = await self.db_manager.get_test_scenario(scenario_id)
            if not scenario:
                raise Exception(f"Test scenario '{scenario_id}' not found")
            
            if not scenario.is_active:
                raise Exception(f"Test scenario '{scenario_id}' is not active")
            
            # Generate test execution ID
            test_id = str(uuid.uuid4())
            
            # Create test execution record
            execution = TestExecution(
                id=test_id,
                scenario_id=scenario_id,
                phone_number=phone_number,
                status="initializing",
                start_time=datetime.now(),
                metadata={
                    "scenario_name": scenario.name,
                    "total_steps": len(scenario.steps)
                }
            )
            await self.db_manager.create_test_execution(execution)
            
            # Create test state
            self.state_manager.create_test_state(test_id, scenario_id, len(scenario.steps))
            
            # Apply configuration overrides
            session_config = SessionConfig(**self.default_session_config.__dict__)
            if config_overrides:
                for key, value in config_overrides.items():
                    if hasattr(session_config, key):
                        setattr(session_config, key, value)
            
            # Create test session
            session = TestExecutionSession(
                session_id=test_id,
                scenario=scenario,
                service_registry=self.service_registry,
                state_manager=self.state_manager,
                config=session_config
            )
            
            # Set up callbacks
            session.on_step_complete = self._handle_step_complete
            session.on_session_complete = self._handle_session_complete
            session.on_error = self._handle_session_error
            
            # Store active session
            self.active_sessions[test_id] = session
            
            # Initialize session
            await session.initialize()
            
            # Initiate outbound call
            call_id = await self._initiate_call(phone_number, test_id)
            session.set_call_id(call_id)
            
            # Update execution record
            await self.db_manager.update_test_execution(test_id, {
                "status": "in_progress",
                "call_id": call_id
            })
            
            # Fire test start event
            if self.on_test_start:
                await self.on_test_start(test_id, scenario_id, phone_number)
            
            # Start test execution in background
            asyncio.create_task(self._execute_session(session))
            
            logger.info(f"Started test execution {test_id} for scenario {scenario_id}")
            return test_id
            
        except Exception as e:
            logger.error(f"Failed to start test execution: {e}")
            if test_id and test_id in self.active_sessions:
                del self.active_sessions[test_id]
            raise
    
    async def _execute_session(self, session: TestExecutionSession):
        """Execute a test session"""
        try:
            # Wait for call to be established
            # TODO: Implement call establishment check
            await asyncio.sleep(2)  # Simulate call setup
            
            # Execute the test scenario
            result = await session.execute()
            
            logger.info(f"Test session {session.session_id} completed: {result}")
            
        except Exception as e:
            logger.error(f"Test session {session.session_id} failed: {e}")
    
    async def _initiate_call(self, phone_number: str, test_id: str) -> str:
        """Initiate outbound call via OpenSIPS"""
        try:
            # Generate call ID
            call_id = f"test_{test_id[:8]}_{int(datetime.now().timestamp())}"
            
            # TODO: Implement actual OpenSIPS call initiation
            # For now, simulate call initiation
            logger.info(f"Initiating call to {phone_number} with call_id={call_id}")
            
            # Register call handler with OpenSIPS integration
            # self.opensips_integration.register_call_handler(call_id, self._handle_call_event)
            
            return call_id
            
        except Exception as e:
            logger.error(f"Failed to initiate call: {e}")
            raise
    
    async def get_test_status(self, test_id: str) -> Dict[str, Any]:
        """Get current status of a test execution"""
        # Check active sessions
        if test_id in self.active_sessions:
            state = self.state_manager.get_state(test_id)
            if state:
                return state.to_dict()
        
        # Check database for completed tests
        execution = await self.db_manager.get_test_execution(test_id)
        if execution:
            return execution.to_dict()
        
        return {"error": f"Test execution {test_id} not found"}
    
    async def cancel_test(self, test_id: str) -> bool:
        """Cancel an active test execution"""
        session = self.active_sessions.get(test_id)
        if session:
            await session.cancel()
            
            # Update database
            await self.db_manager.update_test_execution(test_id, {
                "status": "cancelled",
                "end_time": datetime.now()
            })
            
            # Clean up
            del self.active_sessions[test_id]
            logger.info(f"Cancelled test execution {test_id}")
            return True
        
        return False
    
    async def get_active_tests(self) -> List[Dict[str, Any]]:
        """Get list of currently active tests"""
        active_tests = []
        
        for test_id in self.state_manager.get_active_tests():
            state = self.state_manager.get_state(test_id)
            if state:
                active_tests.append({
                    "test_id": test_id,
                    "scenario_id": state.scenario_id,
                    "state": state.state.value,
                    "progress": f"{state.current_step}/{state.total_steps}",
                    "start_time": state.start_time.isoformat() if state.start_time else None
                })
        
        return active_tests
    
    async def _handle_step_complete(self, test_id: str, step_result: Dict[str, Any]):
        """Handle test step completion"""
        # Update database
        await self.db_manager.create_step_execution({
            "execution_id": test_id,
            "step_number": step_result["step_number"],
            "action": step_result["action"],
            "expected_intent": step_result.get("expected_intent"),
            "actual_intent": step_result.get("actual_intent"),
            "confidence": step_result.get("confidence"),
            "transcribed_text": step_result.get("transcribed_text"),
            "validation_passed": step_result["validation_passed"],
            "error_message": step_result.get("error_message"),
            "start_time": step_result.get("start_time"),
            "end_time": step_result.get("end_time"),
            "duration_ms": step_result.get("duration_ms")
        })
        
        # Fire step complete event
        if self.on_step_complete:
            await self.on_step_complete(test_id, step_result)
    
    async def _handle_session_complete(self, test_id: str, summary: Dict[str, Any]):
        """Handle test session completion"""
        # Update database
        await self.db_manager.update_test_execution(test_id, {
            "status": summary["state"],
            "end_time": datetime.now(),
            "passed_steps": summary["passed_steps"],
            "failed_steps": summary["failed_steps"],
            "total_duration_ms": summary["total_duration_ms"]
        })
        
        # Clean up active session
        if test_id in self.active_sessions:
            del self.active_sessions[test_id]
        
        # Fire test complete event
        if self.on_test_complete:
            await self.on_test_complete(test_id, summary)
    
    async def _handle_session_error(self, test_id: str, error: Exception):
        """Handle test session error"""
        # Update database
        await self.db_manager.update_test_execution(test_id, {
            "status": "failed",
            "end_time": datetime.now(),
            "error_message": str(error)
        })
        
        # Fire error event
        if self.on_test_error:
            await self.on_test_error(test_id, error)
    
    async def _cleanup_completed_sessions(self):
        """Background task to clean up completed sessions"""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                
                # Find completed sessions
                completed = []
                for test_id, session in self.active_sessions.items():
                    state = self.state_manager.get_state(test_id)
                    if state and state.state in [TestState.COMPLETED, TestState.FAILED, 
                                                TestState.CANCELLED, TestState.TIMEOUT]:
                        completed.append(test_id)
                
                # Clean up completed sessions
                for test_id in completed:
                    logger.info(f"Cleaning up completed session {test_id}")
                    self.state_manager.cleanup_test(test_id)
                    if test_id in self.active_sessions:
                        del self.active_sessions[test_id]
                        
            except Exception as e:
                logger.error(f"Error in cleanup task: {e}")
    
    async def _monitor_test_timeouts(self):
        """Background task to monitor test timeouts"""
        while True:
            try:
                await asyncio.sleep(5)  # Check every 5 seconds
                
                for test_id, session in self.active_sessions.items():
                    state = self.state_manager.get_state(test_id)
                    if state and state.start_time:
                        elapsed = (datetime.now() - state.start_time).total_seconds()
                        if elapsed > session.config.timeout_seconds:
                            logger.warning(f"Test {test_id} timed out after {elapsed:.1f}s")
                            await session.cancel()
                            self.state_manager.update_state(test_id, TestState.TIMEOUT)
                            
            except Exception as e:
                logger.error(f"Error in timeout monitor task: {e}")
    
    async def shutdown(self):
        """Shutdown the test execution manager"""
        logger.info("Shutting down Test Execution Manager")
        
        # Cancel all active tests
        for test_id in list(self.active_sessions.keys()):
            await self.cancel_test(test_id)
        
        # Cancel background tasks
        if self._cleanup_task:
            self._cleanup_task.cancel()
        if self._monitor_task:
            self._monitor_task.cancel()
        
        logger.info("Test Execution Manager shutdown complete")