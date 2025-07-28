"""
IVR Test Scenario Execution Engine
Orchestrates step-by-step IVR test execution
"""

import asyncio
import uuid
import logging
import time
from typing import Optional, Dict, Any, List
from datetime import datetime

from core.ivr_testing import TestScenario, TestStep, ScenarioManager
from core.ivr_testing.result_processor import (
    StepResult, ExecutionResult, PerformanceMetrics, 
    StepResultStatus, ExecutionResultStatus, ResultProcessor
)
from core.opensips.outbound_call_manager import OutboundCallManager, OutboundCall
from core.dtmf.generator import DTMFGenerator
from core.dtmf.timing import DTMFSequence, DTMFTiming

import structlog

# Configure structured logging
logger = structlog.get_logger(__name__)

class ExecutionContext:
    """Context for scenario execution"""
    
    def __init__(self, scenario: TestScenario, execution_id: str):
        self.scenario = scenario
        self.execution_id = execution_id
        self.start_time = datetime.now()
        self.call_id: Optional[str] = None
        self.current_step = 0
        self.step_results: List[StepResult] = []
        self.call_manager: Optional[OutboundCallManager] = None
        self.dtmf_generator: Optional[DTMFGenerator] = None
        
        # Execution state
        self.is_running = False
        self.is_cancelled = False
        self.error_message: Optional[str] = None
        
        # Services (to be injected)
        self.tts_service_url = "http://localhost:50053"
        self.asr_service_url = "http://localhost:50051" 
        self.intent_service_url = "http://localhost:50054"
    
    def add_step_result(self, result: StepResult):
        """Add step result to context"""
        self.step_results.append(result)
        logger.info("Step completed", 
                   step=result.step_number,
                   status=result.status.value,
                   duration_ms=result.execution_time_ms)
    
    def get_execution_duration_ms(self) -> int:
        """Get current execution duration in milliseconds"""
        return int((datetime.now() - self.start_time).total_seconds() * 1000)

class ScenarioExecutor:
    """Executes IVR test scenarios step by step"""
    
    def __init__(self, scenario_manager: ScenarioManager, result_processor: ResultProcessor):
        """
        Initialize scenario executor
        
        Args:
            scenario_manager: Scenario management instance
            result_processor: Result processing instance
        """
        self.scenario_manager = scenario_manager
        self.result_processor = result_processor
        self.dtmf_generator = DTMFGenerator()
        
        # Active executions
        self.active_executions: Dict[str, ExecutionContext] = {}
        
        logger.info("Scenario executor initialized")
    
    async def execute_scenario(self, scenario_id: str, 
                             execution_options: Optional[Dict[str, Any]] = None) -> str:
        """
        Start scenario execution
        
        Args:
            scenario_id: ID of scenario to execute
            execution_options: Optional execution configuration
            
        Returns:
            Execution ID for tracking
        """
        try:
            # Load scenario
            scenario = self.scenario_manager.load_scenario(scenario_id)
            if not scenario:
                raise ValueError(f"Scenario not found: {scenario_id}")
            
            # Create execution context
            execution_id = str(uuid.uuid4())
            context = ExecutionContext(scenario, execution_id)
            self.active_executions[execution_id] = context
            
            logger.info("Starting scenario execution",
                       execution_id=execution_id,
                       scenario_id=scenario_id,
                       scenario_name=scenario.name)
            
            # Execute scenario asynchronously
            asyncio.create_task(self._execute_scenario_async(context))
            
            return execution_id
            
        except Exception as e:
            logger.error("Failed to start scenario execution", error=str(e))
            raise
    
    async def _execute_scenario_async(self, context: ExecutionContext):
        """
        Execute scenario asynchronously
        
        Args:
            context: Execution context
        """
        try:
            context.is_running = True
            
            # Initialize call manager
            context.call_manager = OutboundCallManager()
            
            # Execute scenario steps
            await self._execute_steps(context)
            
            # Generate final result
            await self._finalize_execution(context, ExecutionResultStatus.PASS)
            
        except asyncio.CancelledError:
            logger.info("Scenario execution cancelled", execution_id=context.execution_id)
            await self._finalize_execution(context, ExecutionResultStatus.CANCELLED)
            
        except Exception as e:
            logger.error("Scenario execution failed", 
                        execution_id=context.execution_id,
                        error=str(e))
            context.error_message = str(e)
            await self._finalize_execution(context, ExecutionResultStatus.ERROR)
            
        finally:
            context.is_running = False
            # Clean up
            if context.call_manager and context.call_id:
                try:
                    await context.call_manager.hang_up_call(context.call_id)
                except Exception as e:
                    logger.warning("Failed to hang up call", error=str(e))
            
            # Remove from active executions
            self.active_executions.pop(context.execution_id, None)
    
    async def _execute_steps(self, context: ExecutionContext):
        """
        Execute all scenario steps
        
        Args:
            context: Execution context
        """
        scenario = context.scenario
        
        # Start call first
        await self._initiate_call(context)
        
        # Execute each step
        for step in scenario.steps:
            if context.is_cancelled:
                break
            
            context.current_step = step.step_number
            
            logger.info("Executing step",
                       execution_id=context.execution_id,
                       step_number=step.step_number,
                       step_type=step.step_type)
            
            step_start_time = time.time()
            
            try:
                # Execute step based on type
                if step.step_type == "tts_prompt":
                    await self._execute_tts_step(context, step)
                elif step.step_type == "asr_listen":
                    await self._execute_asr_step(context, step)
                elif step.step_type == "dtmf_send":
                    await self._execute_dtmf_step(context, step)
                elif step.step_type == "intent_validate":
                    await self._execute_intent_validation_step(context, step)
                else:
                    raise ValueError(f"Unknown step type: {step.step_type}")
                
                # Check if step passed or failed
                last_result = context.step_results[-1] if context.step_results else None
                if last_result and not last_result.is_successful():
                    # Handle step failure
                    if step.conditional:
                        # Check conditional logic
                        should_continue = await self._evaluate_conditional(context, step, last_result)
                        if not should_continue:
                            break
                    else:
                        # No conditional logic, fail scenario
                        raise ValueError(f"Step {step.step_number} failed: {last_result.error_message}")
                        
            except asyncio.TimeoutError:
                # Step timeout
                execution_time = int((time.time() - step_start_time) * 1000)
                result = StepResult(
                    step_number=step.step_number,
                    step_type=step.step_type,
                    status=StepResultStatus.TIMEOUT,
                    execution_time_ms=execution_time,
                    error_message="Step execution timeout"
                )
                context.add_step_result(result)
                
                # Check if we should continue
                if not step.conditional:
                    raise ValueError(f"Step {step.step_number} timed out")
                    
            except Exception as e:
                # Step error
                execution_time = int((time.time() - step_start_time) * 1000)
                result = StepResult(
                    step_number=step.step_number,
                    step_type=step.step_type,
                    status=StepResultStatus.ERROR,
                    execution_time_ms=execution_time,
                    error_message=str(e)
                )
                context.add_step_result(result)
                raise
    
    async def _initiate_call(self, context: ExecutionContext):
        """
        Initiate outbound call
        
        Args:
            context: Execution context
        """
        try:
            if not context.call_manager:
                raise ValueError("Call manager not initialized")
            
            scenario = context.scenario
            
            # Create outbound call
            call = OutboundCall(
                destination_number=scenario.target_phone,
                caller_id="IVR_TEST_SYSTEM",
                timeout_seconds=scenario.timeout_seconds
            )
            
            # Initiate call
            success = await context.call_manager.start_call(call)
            if not success:
                raise ValueError("Failed to initiate outbound call")
            
            context.call_id = call.call_id
            
            logger.info("Call initiated",
                       execution_id=context.execution_id,
                       call_id=context.call_id,
                       target_phone=scenario.target_phone)
            
            # Wait for call to be established
            await asyncio.sleep(2)
            
        except Exception as e:
            logger.error("Failed to initiate call", error=str(e))
            raise
    
    async def _execute_tts_step(self, context: ExecutionContext, step: TestStep):
        """
        Execute TTS prompt step
        
        Args:
            context: Execution context
            step: TTS step to execute
        """
        step_start_time = time.time()
        
        try:
            if not step.prompt_text:
                raise ValueError("TTS step requires prompt_text")
            
            # Simulate TTS processing (replace with actual TTS service call)
            logger.info("Generating TTS audio",
                       text=step.prompt_text[:50] + "..." if len(step.prompt_text) > 50 else step.prompt_text)
            
            # Simulate TTS generation time
            tts_duration = max(len(step.prompt_text) * 50, 1000)  # ~50ms per character, min 1s
            await asyncio.sleep(tts_duration / 1000)
            
            # TODO: Integrate with actual TTS service
            # tts_response = await self._call_tts_service(step.prompt_text)
            # await self._play_audio_to_call(context.call_id, tts_response.audio_data)
            
            execution_time = int((time.time() - step_start_time) * 1000)
            
            result = StepResult(
                step_number=step.step_number,
                step_type=step.step_type,
                status=StepResultStatus.SUCCESS,
                execution_time_ms=execution_time,
                tts_text=step.prompt_text,
                tts_duration_ms=tts_duration
            )
            
            context.add_step_result(result)
            
            # Wait for response if requested
            if step.wait_for_response:
                await asyncio.sleep(1)  # Give IVR time to respond
            
        except Exception as e:
            execution_time = int((time.time() - step_start_time) * 1000)
            result = StepResult(
                step_number=step.step_number,
                step_type=step.step_type,
                status=StepResultStatus.ERROR,
                execution_time_ms=execution_time,
                error_message=str(e)
            )
            context.add_step_result(result)
            raise
    
    async def _execute_asr_step(self, context: ExecutionContext, step: TestStep):
        """
        Execute ASR listening step
        
        Args:
            context: Execution context
            step: ASR step to execute
        """
        step_start_time = time.time()
        
        try:
            max_duration = step.max_duration_ms or 5000
            
            logger.info("Starting ASR capture", max_duration_ms=max_duration)
            
            # Simulate ASR processing (replace with actual ASR service call)
            await asyncio.sleep(max_duration / 1000)
            
            # Mock ASR result (replace with actual ASR service call)
            # TODO: Integrate with actual ASR service
            # asr_response = await self._call_asr_service(context.call_id, max_duration)
            
            # Simulate typical Turkish IVR responses
            mock_responses = [
                "Merhaba, bankamıza hoş geldiniz. Hesap bakiye sorgusu için 1'e basınız.",
                "Hesap bakiyeniz 2500 lira 45 kuruştur.",
                "Başka bir işlem yapmak ister misiniz?",
                "İyi günler dileriz."
            ]
            
            # Pick response based on step number
            transcribed_text = mock_responses[min(step.step_number - 1, len(mock_responses) - 1)]
            
            execution_time = int((time.time() - step_start_time) * 1000)
            
            result = StepResult(
                step_number=step.step_number,
                step_type=step.step_type,
                status=StepResultStatus.SUCCESS,
                execution_time_ms=execution_time,
                transcribed_text=transcribed_text
            )
            
            context.add_step_result(result)
            
        except Exception as e:
            execution_time = int((time.time() - step_start_time) * 1000)
            result = StepResult(
                step_number=step.step_number,
                step_type=step.step_type,
                status=StepResultStatus.ERROR,
                execution_time_ms=execution_time,
                error_message=str(e)
            )
            context.add_step_result(result)
            raise
    
    async def _execute_dtmf_step(self, context: ExecutionContext, step: TestStep):
        """
        Execute DTMF sending step
        
        Args:
            context: Execution context
            step: DTMF step to execute
        """
        step_start_time = time.time()
        
        try:
            if not step.dtmf_sequence:
                raise ValueError("DTMF step requires dtmf_sequence")
            
            logger.info("Sending DTMF sequence", sequence=step.dtmf_sequence)
            
            # Create DTMF sequence
            timing = DTMFTiming(
                tone_duration_ms=150,
                pause_duration_ms=100
            )
            
            dtmf_sequence = DTMFSequence(
                tones=step.dtmf_sequence,
                timing=timing
            )
            
            # Generate DTMF tones
            duration_ms = await self._send_dtmf_sequence(context, dtmf_sequence)
            
            execution_time = int((time.time() - step_start_time) * 1000)
            
            result = StepResult(
                step_number=step.step_number,
                step_type=step.step_type,
                status=StepResultStatus.SUCCESS,
                execution_time_ms=execution_time,
                dtmf_sequence=step.dtmf_sequence,
                dtmf_sent_successfully=True
            )
            
            context.add_step_result(result)
            
        except Exception as e:
            execution_time = int((time.time() - step_start_time) * 1000)
            result = StepResult(
                step_number=step.step_number,
                step_type=step.step_type,
                status=StepResultStatus.ERROR,
                execution_time_ms=execution_time,
                error_message=str(e),
                dtmf_sent_successfully=False
            )
            context.add_step_result(result)
            raise
    
    async def _execute_intent_validation_step(self, context: ExecutionContext, step: TestStep):
        """
        Execute intent validation step
        
        Args:
            context: Execution context
            step: Intent validation step to execute
        """
        step_start_time = time.time()
        
        try:
            if not step.expected_intent:
                raise ValueError("Intent validation step requires expected_intent")
            
            # Get last ASR result
            last_asr_result = None
            for result in reversed(context.step_results):
                if result.step_type == "asr_listen" and result.transcribed_text:
                    last_asr_result = result
                    break
            
            if not last_asr_result:
                raise ValueError("No ASR text available for intent validation")
            
            logger.info("Validating intent",
                       expected_intent=step.expected_intent,
                       text=last_asr_result.transcribed_text)
            
            # Call intent service
            # TODO: Integrate with actual intent service
            # intent_response = await self._call_intent_service(last_asr_result.transcribed_text)
            
            # Mock intent classification
            detected_intent = self._mock_intent_classification(last_asr_result.transcribed_text)
            confidence = 0.85  # Mock confidence
            
            # Check if intent matches
            intent_match = detected_intent == step.expected_intent
            
            execution_time = int((time.time() - step_start_time) * 1000)
            
            status = StepResultStatus.SUCCESS if intent_match else StepResultStatus.FAILED
            
            result = StepResult(
                step_number=step.step_number,
                step_type=step.step_type,
                status=status,
                execution_time_ms=execution_time,
                expected_intent=step.expected_intent,
                actual_intent=detected_intent,
                intent_match=intent_match,
                validation_confidence=confidence
            )
            
            if not intent_match:
                result.error_message = f"Intent mismatch: expected {step.expected_intent}, got {detected_intent}"
            
            context.add_step_result(result)
            
        except Exception as e:
            execution_time = int((time.time() - step_start_time) * 1000)
            result = StepResult(
                step_number=step.step_number,
                step_type=step.step_type,
                status=StepResultStatus.ERROR,
                execution_time_ms=execution_time,
                error_message=str(e)
            )
            context.add_step_result(result)
            raise
    
    def _mock_intent_classification(self, text: str) -> str:
        """
        Mock intent classification for testing
        
        Args:
            text: Text to classify
            
        Returns:
            Predicted intent
        """
        text_lower = text.lower()
        
        if "hoş geldiniz" in text_lower or "merhaba" in text_lower:
            return "greeting"
        elif "bakiye" in text_lower:
            return "balance_inquiry"
        elif "işlem" in text_lower or "basınız" in text_lower:
            return "menu_options"
        elif "lira" in text_lower or "kuruş" in text_lower:
            return "balance_response"
        elif "iyi günler" in text_lower:
            return "goodbye"
        else:
            return "unknown"
    
    async def _send_dtmf_sequence(self, context: ExecutionContext, sequence: DTMFSequence) -> int:
        """
        Send DTMF sequence
        
        Args:
            context: Execution context
            sequence: DTMF sequence to send
            
        Returns:
            Duration in milliseconds
        """
        try:
            # Generate DTMF audio
            audio_data = await self.dtmf_generator.generate_sequence_async(sequence)
            
            # TODO: Integrate with call audio stream
            # await self._inject_audio_to_call(context.call_id, audio_data)
            
            # Simulate DTMF transmission time
            duration_ms = sequence.timing.get_sequence_duration(len(sequence.tones))
            await asyncio.sleep(duration_ms / 1000)
            
            return duration_ms
            
        except Exception as e:
            logger.error("Failed to send DTMF sequence", error=str(e))
            raise
    
    async def _evaluate_conditional(self, context: ExecutionContext, 
                                  step: TestStep, step_result: StepResult) -> bool:
        """
        Evaluate conditional logic for step
        
        Args:
            context: Execution context
            step: Step with conditional logic
            step_result: Result of step execution
            
        Returns:
            True if execution should continue
        """
        if not step.conditional:
            return True
        
        # Simple conditional logic implementation
        # TODO: Implement more sophisticated conditional logic
        
        condition_type = step.conditional.get("condition_type", "intent_match")
        
        if condition_type == "intent_match":
            expected_intent = step.conditional.get("expected_intent")
            actual_intent = getattr(step_result, 'actual_intent', None)
            
            if actual_intent == expected_intent:
                # Condition met
                if_true = step.conditional.get("if_true", {})
                action = if_true.get("action", "continue")
                return action == "continue"
            else:
                # Condition not met
                if_false = step.conditional.get("if_false", {})
                action = if_false.get("action", "fail_scenario")
                return action == "continue"
        
        return True
    
    async def _finalize_execution(self, context: ExecutionContext, status: ExecutionResultStatus):
        """
        Finalize execution and generate results
        
        Args:
            context: Execution context
            status: Final execution status
        """
        try:
            end_time = datetime.now()
            total_duration_ms = context.get_execution_duration_ms()
            
            # Calculate performance metrics
            successful_steps = sum(1 for r in context.step_results if r.is_successful())
            failed_steps = sum(1 for r in context.step_results if r.status == StepResultStatus.FAILED)
            timeout_steps = sum(1 for r in context.step_results if r.status == StepResultStatus.TIMEOUT)
            error_steps = sum(1 for r in context.step_results if r.status == StepResultStatus.ERROR)
            skipped_steps = sum(1 for r in context.step_results if r.status == StepResultStatus.SKIPPED)
            
            # Calculate TTS/ASR durations
            total_tts_duration = sum(
                r.tts_duration_ms or 0 
                for r in context.step_results 
                if r.step_type == "tts_prompt"
            )
            
            total_asr_duration = sum(
                r.execution_time_ms 
                for r in context.step_results 
                if r.step_type == "asr_listen"
            )
            
            performance_metrics = PerformanceMetrics(
                total_duration_ms=total_duration_ms,
                successful_steps=successful_steps,
                failed_steps=failed_steps,
                timeout_steps=timeout_steps,
                error_steps=error_steps,
                skipped_steps=skipped_steps,
                total_tts_duration_ms=total_tts_duration,
                total_asr_duration_ms=total_asr_duration,
                call_duration_ms=total_duration_ms  # Approximate
            )
            
            # Create execution result
            execution_result = ExecutionResult(
                execution_id=context.execution_id,
                scenario_id=context.scenario.scenario_id,
                scenario_name=context.scenario.name,
                status=status,
                start_time=context.start_time.isoformat(),
                end_time=end_time.isoformat(),
                step_results=context.step_results,
                performance_metrics=performance_metrics,
                call_id=context.call_id,
                target_phone=context.scenario.target_phone,
                error_message=context.error_message,
                executor_version="1.0.0",
                environment="development"
            )
            
            # Save result
            success = self.result_processor.save_execution_result(execution_result)
            
            if success:
                logger.info("Execution completed and saved",
                           execution_id=context.execution_id,
                           status=status.value,
                           duration_ms=total_duration_ms,
                           success_rate=performance_metrics.get_success_rate())
            else:
                logger.error("Failed to save execution result",
                            execution_id=context.execution_id)
            
        except Exception as e:
            logger.error("Failed to finalize execution", error=str(e))
    
    def get_execution_status(self, execution_id: str) -> Optional[Dict[str, Any]]:
        """
        Get current execution status
        
        Args:
            execution_id: Execution ID to check
            
        Returns:
            Status information or None if not found
        """
        context = self.active_executions.get(execution_id)
        if not context:
            return None
        
        return {
            "execution_id": execution_id,
            "scenario_id": context.scenario.scenario_id,
            "scenario_name": context.scenario.name,
            "status": "running" if context.is_running else "completed",
            "current_step": context.current_step,
            "total_steps": len(context.scenario.steps),
            "duration_ms": context.get_execution_duration_ms(),
            "call_id": context.call_id,
            "completed_steps": len(context.step_results),
            "successful_steps": sum(1 for r in context.step_results if r.is_successful())
        }
    
    async def cancel_execution(self, execution_id: str) -> bool:
        """
        Cancel running execution
        
        Args:
            execution_id: Execution ID to cancel
            
        Returns:
            True if cancelled successfully
        """
        context = self.active_executions.get(execution_id)
        if not context or not context.is_running:
            return False
        
        context.is_cancelled = True
        logger.info("Execution cancelled", execution_id=execution_id)
        return True
    
    def list_active_executions(self) -> List[Dict[str, Any]]:
        """
        List all active executions
        
        Returns:
            List of active execution summaries
        """
        return [
            self.get_execution_status(execution_id)
            for execution_id in self.active_executions.keys()
        ]