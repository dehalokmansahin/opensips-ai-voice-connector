#!/usr/bin/env python3
"""
Test Controller Service - Main Entry Point
FastAPI REST API service for IVR test orchestration
"""

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware

# Add parent directories to path for core imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from core.test_controller import TestExecutionManager, TestStateManager
from core.opensips import OpenSIPSIntegration
from core.config.settings import Settings
from core.ivr_testing import ScenarioManager
from core.ivr_testing.result_processor import ResultProcessor
try:
    from test_controller_api import TestControllerAPI
except ImportError:
    TestControllerAPI = None

try:
    from scenario_executor import ScenarioExecutor
except ImportError:
    ScenarioExecutor = None

try:
    from models import (
        TestExecutionRequest, TestExecutionResponse,
        TestScenarioRequest, TestScenarioResponse,
        CallControlRequest, CallControlResponse
    )
except ImportError:
    # Create simple fallback models
    from pydantic import BaseModel
    class TestExecutionRequest(BaseModel):
        scenario_id: str
    class TestExecutionResponse(BaseModel):
        execution_id: str
        status: str
    class TestScenarioRequest(BaseModel):
        name: str
    class TestScenarioResponse(BaseModel):
        scenario_id: str
    class CallControlRequest(BaseModel):
        dtmf_sequence: str
    class CallControlResponse(BaseModel):
        success: bool

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global service instances
test_execution_manager: TestExecutionManager = None
opensips_integration: OpenSIPSIntegration = None
test_controller_api: TestControllerAPI = None
scenario_manager: ScenarioManager = None
result_processor: ResultProcessor = None
scenario_executor: ScenarioExecutor = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager"""
    # Startup
    logger.info("Starting Test Controller Service")
    
    global test_execution_manager, opensips_integration, test_controller_api
    global scenario_manager, result_processor, scenario_executor
    
    try:
        # Initialize lightweight scenario management without full OpenSIPS dependencies
        # This allows the Test Controller to work independently for IVR testing
        
        # Initialize scenario management
        db_path = os.getenv("DATABASE_PATH", "/app/data/test_scenarios.db")
        scenario_manager = ScenarioManager(db_path=db_path)
        result_processor = ResultProcessor()
        
        if ScenarioExecutor:
            scenario_executor = ScenarioExecutor(scenario_manager, result_processor)
        else:
            logger.warning("ScenarioExecutor not available, some endpoints will be disabled")
        
        logger.info("Test Controller Service initialized successfully")
        
        yield
        
    except Exception as e:
        logger.error(f"Failed to initialize Test Controller Service: {e}")
        raise
    
    # Shutdown
    logger.info("Shutting down Test Controller Service")
    
    try:
        if test_execution_manager:
            await test_execution_manager.shutdown()
        
        if opensips_integration:
            await opensips_integration.stop()
            
        logger.info("Test Controller Service shutdown complete")
        
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")

# Create FastAPI app
app = FastAPI(
    title="Test Controller Service",
    description="IVR Test Orchestration and Control Service",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        health_status = {
            "status": "healthy",
            "service": "test-controller",
            "version": "1.0.0"
        }
        
        # Check scenario management
        if scenario_manager:
            health_status["scenario_manager"] = "available"
        
        if result_processor:
            health_status["result_processor"] = "available"
            
        if scenario_executor:
            health_status["scenario_executor"] = "available"
        
        return health_status
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")

# Test execution endpoints
@app.post("/api/v1/test-executions/start", response_model=TestExecutionResponse)
async def start_test_execution(request: TestExecutionRequest):
    """Start a new test execution"""
    try:
        if not test_controller_api:
            raise HTTPException(status_code=501, detail="Test controller API not available - service running in limited mode")
        
        response = await test_controller_api.start_test_execution(request)
        return response
        
    except Exception as e:
        logger.error(f"Failed to start test execution: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/test-executions/{execution_id}", response_model=TestExecutionResponse)
async def get_test_execution(execution_id: str):
    """Get test execution status"""
    try:
        if not test_controller_api:
            raise HTTPException(status_code=501, detail="Test controller API not available - service running in limited mode")
        
        response = await test_controller_api.get_test_execution(execution_id)
        if not response:
            raise HTTPException(status_code=404, detail="Test execution not found")
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get test execution: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/test-executions/{execution_id}/stop")
async def stop_test_execution(execution_id: str):
    """Stop a running test execution"""
    try:
        if not test_controller_api:
            raise HTTPException(status_code=501, detail="Test controller API not available - service running in limited mode")
        
        success = await test_controller_api.stop_test_execution(execution_id)
        if not success:
            raise HTTPException(status_code=404, detail="Test execution not found")
        
        return {"status": "stopped", "execution_id": execution_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to stop test execution: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Test scenario endpoints
@app.get("/api/v1/test-scenarios")
async def list_test_scenarios():
    """List available test scenarios"""
    try:
        if not test_controller_api:
            raise HTTPException(status_code=501, detail="Test controller API not available - service running in limited mode")
        
        scenarios = await test_controller_api.list_test_scenarios()
        return {"scenarios": scenarios}
        
    except Exception as e:
        logger.error(f"Failed to list test scenarios: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/test-scenarios", response_model=TestScenarioResponse)
async def create_test_scenario(request: TestScenarioRequest):
    """Create a new test scenario"""
    try:
        if not test_controller_api:
            raise HTTPException(status_code=501, detail="Test controller API not available - service running in limited mode")
        
        response = await test_controller_api.create_test_scenario(request)
        return response
        
    except Exception as e:
        logger.error(f"Failed to create test scenario: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Call control endpoints
@app.post("/api/v1/calls/{call_id}/dtmf")
async def send_dtmf(call_id: str, request: CallControlRequest):
    """Send DTMF tones to an active call"""
    try:
        if not test_controller_api:
            raise HTTPException(status_code=501, detail="Test controller API not available - service running in limited mode")
        
        response = await test_controller_api.send_dtmf(call_id, request)
        return response
        
    except Exception as e:
        logger.error(f"Failed to send DTMF: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/calls")
async def list_active_calls():
    """List all active calls"""
    try:
        if not opensips_integration:
            raise HTTPException(status_code=501, detail="OpenSIPS integration not available - service running in limited mode")
        
        calls = await opensips_integration.get_active_outbound_calls()
        return {"calls": calls}
        
    except Exception as e:
        logger.error(f"Failed to list active calls: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Scenario execution endpoints (Story 2.2)
@app.post("/api/v1/scenarios/{scenario_id}/execute")
async def execute_scenario(scenario_id: str):
    """Execute a test scenario"""
    try:
        if not scenario_executor:
            raise HTTPException(status_code=500, detail="Scenario executor not initialized")
        
        execution_id = await scenario_executor.execute_scenario(scenario_id)
        
        return {
            "execution_id": execution_id,
            "scenario_id": scenario_id,
            "status": "started"
        }
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to execute scenario: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/scenarios/{scenario_id}/executions")
async def list_scenario_executions(scenario_id: str, limit: int = 20):
    """List executions for a scenario"""
    try:
        if not result_processor:
            raise HTTPException(status_code=500, detail="Result processor not initialized")
        
        executions = result_processor.list_execution_results(
            scenario_id=scenario_id,
            limit=limit
        )
        
        return {"executions": executions}
        
    except Exception as e:
        logger.error(f"Failed to list scenario executions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/executions/{execution_id}/status")
async def get_execution_status(execution_id: str):
    """Get execution status"""
    try:
        if not scenario_executor:
            raise HTTPException(status_code=500, detail="Scenario executor not initialized")
        
        status = scenario_executor.get_execution_status(execution_id)
        if not status:
            # Check if execution exists in database
            if result_processor:
                result = result_processor.load_execution_result(execution_id)
                if result:
                    return {
                        "execution_id": execution_id,
                        "status": "completed",
                        "final_status": result.status.value,
                        "duration_ms": result.performance_metrics.total_duration_ms,
                        "success_rate": result.performance_metrics.get_success_rate()
                    }
            
            raise HTTPException(status_code=404, detail="Execution not found")
        
        return status
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get execution status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/executions/{execution_id}/results")
async def get_execution_results(execution_id: str):
    """Get detailed execution results"""
    try:
        if not result_processor:
            raise HTTPException(status_code=500, detail="Result processor not initialized")
        
        result = result_processor.load_execution_result(execution_id)
        if not result:
            raise HTTPException(status_code=404, detail="Execution results not found")
        
        return {
            "execution_id": result.execution_id,
            "scenario_id": result.scenario_id,
            "scenario_name": result.scenario_name,
            "status": result.status.value,
            "start_time": result.start_time,
            "end_time": result.end_time,
            "duration_seconds": result.get_duration_seconds(),
            "success_rate": result.performance_metrics.get_success_rate(),
            "step_results": [
                {
                    "step_number": step.step_number,
                    "step_type": step.step_type,
                    "status": step.status.value,
                    "execution_time_ms": step.execution_time_ms,
                    "summary": step.get_summary(),
                    "error_message": step.error_message
                }
                for step in result.step_results
            ],
            "performance_metrics": {
                "total_duration_ms": result.performance_metrics.total_duration_ms,
                "successful_steps": result.performance_metrics.successful_steps,
                "failed_steps": result.performance_metrics.failed_steps,
                "success_rate": result.performance_metrics.get_success_rate()
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get execution results: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/executions/{execution_id}/cancel")
async def cancel_execution(execution_id: str):
    """Cancel a running execution"""
    try:
        if not scenario_executor:
            raise HTTPException(status_code=500, detail="Scenario executor not initialized")
        
        success = await scenario_executor.cancel_execution(execution_id)
        if not success:
            raise HTTPException(status_code=404, detail="Execution not found or not running")
        
        return {"status": "cancelled", "execution_id": execution_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel execution: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/test-debug")
async def test_debug():
    """Debug test endpoint"""
    logger.error("DEBUG: Test endpoint called!")
    return {"debug": "endpoint working", "scenarios_available": True}

@app.get("/api/v1/scenarios")
async def list_scenarios(tags: str = None):
    """List all scenarios"""
    try:
        # Create new ScenarioManager each time to ensure fresh connection
        db_path = os.getenv("DATABASE_PATH", "/app/data/test_scenarios.db")
        current_scenario_manager = ScenarioManager(db_path=db_path)
        
        # Simple call without tags first
        scenarios = current_scenario_manager.list_scenarios()
        
        import sys
        print(f"DEBUG: Found {len(scenarios)} scenarios from {db_path}", file=sys.stderr)
        logger.error(f"DEBUG: Found {len(scenarios)} scenarios from {db_path}")
        
        return {"scenarios": scenarios}
        
    except Exception as e:
        print(f"DEBUG ERROR: {e}")
        logger.error(f"Failed to list scenarios: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/executions")
async def list_active_executions():
    """List all active executions"""
    try:
        if not scenario_executor:
            raise HTTPException(status_code=500, detail="Scenario executor not initialized")
        
        executions = scenario_executor.list_active_executions()
        
        return {"active_executions": executions}
        
    except Exception as e:
        logger.error(f"Failed to list active executions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def main():
    """Main entry point"""
    # Configuration from environment
    host = os.getenv("TEST_CONTROLLER_HOST", "0.0.0.0")
    port = int(os.getenv("TEST_CONTROLLER_PORT", "50055"))
    log_level = os.getenv("LOG_LEVEL", "info").lower()
    
    logger.info(f"Starting Test Controller Service on {host}:{port}")
    
    # Run the server
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level=log_level,
        reload=False  # Set to True for development
    )

if __name__ == "__main__":
    main()