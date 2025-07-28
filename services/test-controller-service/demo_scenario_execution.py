#!/usr/bin/env python3
"""
Scenario Execution Demo
Tests the complete scenario execution workflow
"""

import asyncio
import sys
import os
import time
from datetime import datetime

# Add parent directories to path for core imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from core.ivr_testing import ScenarioManager, TestStep, TestScenario
from core.ivr_testing.result_processor import ResultProcessor
from src.scenario_executor import ScenarioExecutor

def print_banner():
    """Print demo banner"""
    print("=" * 70)
    print("  IVR SCENARIO EXECUTION DEMO")
    print("  End-to-End Test Automation Workflow")
    print("=" * 70)
    print()

def create_simple_test_scenario() -> TestScenario:
    """Create a simple test scenario for demo"""
    steps = [
        TestStep(
            step_number=1,
            step_type="asr_listen",
            expected_intent="greeting",
            max_duration_ms=5000
        ),
        TestStep(
            step_number=2,
            step_type="dtmf_send",
            dtmf_sequence="1"
        ),
        TestStep(
            step_number=3,
            step_type="asr_listen",
            max_duration_ms=5000
        ),
        TestStep(
            step_number=4,
            step_type="intent_validate",
            expected_intent="balance_response",
            pass_criteria="intent_match"
        )
    ]
    
    return TestScenario(
        scenario_id="demo_scenario",
        name="Demo Balance Inquiry",
        description="Simple demo scenario for testing execution engine",
        target_phone="+905551234567",
        timeout_seconds=60,
        steps=steps,
        created_at=datetime.now().isoformat(),
        created_by="demo",
        tags=["demo", "test"]
    )

async def demo_scenario_management():
    """Demo scenario management functionality"""
    print("[SCENARIO MANAGEMENT] Testing scenario operations")
    print("-" * 50)
    
    try:
        # Initialize scenario manager
        scenario_manager = ScenarioManager()
        
        # Create demo scenario
        scenario = create_simple_test_scenario()
        print(f"Created scenario: {scenario.name}")
        print(f"  ID: {scenario.scenario_id}")
        print(f"  Steps: {len(scenario.steps)}")
        print(f"  Target: {scenario.target_phone}")
        
        # Validate scenario
        is_valid, error = scenario.validate()
        if not is_valid:
            print(f"  [ERROR] Validation failed: {error}")
            return False
        
        print("  [OK] Scenario validation passed")
        
        # Save scenario
        success = scenario_manager.save_scenario(scenario)
        if not success:
            print("  [ERROR] Failed to save scenario")
            return False
        
        print("  [OK] Scenario saved to database")
        
        # Load scenario back
        loaded_scenario = scenario_manager.load_scenario(scenario.scenario_id)
        if not loaded_scenario:
            print("  [ERROR] Failed to load scenario")
            return False
        
        print("  [OK] Scenario loaded from database")
        
        # List scenarios
        scenarios = scenario_manager.list_scenarios()
        print(f"  [OK] Found {len(scenarios)} scenarios in database")
        
        return True
        
    except Exception as e:
        print(f"  [ERROR] Scenario management demo failed: {e}")
        return False

async def demo_scenario_execution():
    """Demo scenario execution functionality"""
    print("\n[SCENARIO EXECUTION] Testing execution engine")
    print("-" * 50)
    
    try:
        # Initialize components
        scenario_manager = ScenarioManager()
        result_processor = ResultProcessor()
        scenario_executor = ScenarioExecutor(scenario_manager, result_processor)
        
        # Execute demo scenario
        print("Starting scenario execution...")
        execution_id = await scenario_executor.execute_scenario("demo_scenario")
        print(f"  [OK] Execution started: {execution_id}")
        
        # Monitor execution
        print("Monitoring execution progress...")
        execution_completed = False
        max_wait = 30  # seconds
        wait_time = 0
        
        while not execution_completed and wait_time < max_wait:
            # Check status
            status = scenario_executor.get_execution_status(execution_id)
            
            if status:
                print(f"  Status: {status['status']}")
                print(f"  Current step: {status['current_step']}/{status['total_steps']}")
                print(f"  Duration: {status['duration_ms']}ms")
                print(f"  Completed steps: {status['completed_steps']}")
                
                if status['status'] != 'running':
                    execution_completed = True
                    break
            else:
                execution_completed = True
                break
            
            await asyncio.sleep(2)
            wait_time += 2
        
        if execution_completed:
            print("  [OK] Execution completed")
        else:
            print("  [WARNING] Execution still running after timeout")
        
        # Wait a bit more for finalization
        await asyncio.sleep(3)
        
        return execution_id
        
    except Exception as e:
        print(f"  [ERROR] Scenario execution demo failed: {e}")
        return None

async def demo_result_processing(execution_id: str):
    """Demo result processing functionality"""
    print("\n[RESULT PROCESSING] Testing result analysis")
    print("-" * 50)
    
    try:
        # Initialize result processor
        result_processor = ResultProcessor()
        
        # Load execution result
        result = result_processor.load_execution_result(execution_id)
        if not result:
            print("  [WARNING] Execution result not found in database")
            print("  This is expected if execution is still finalizing")
            return True
        
        print(f"Loaded execution result: {execution_id}")
        print(f"  Scenario: {result.scenario_name}")
        print(f"  Status: {result.status.value}")
        print(f"  Duration: {result.get_duration_seconds():.1f}s")
        print(f"  Success rate: {result.performance_metrics.get_success_rate():.1f}%")
        
        # Analyze step results
        print(f"Step Results ({len(result.step_results)} steps):")
        for step in result.step_results:
            print(f"  {step.get_summary()}")
        
        # Performance metrics
        metrics = result.performance_metrics
        print(f"Performance Metrics:")
        print(f"  Successful steps: {metrics.successful_steps}")
        print(f"  Failed steps: {metrics.failed_steps}")
        print(f"  Total duration: {metrics.total_duration_ms}ms")
        print(f"  TTS duration: {metrics.total_tts_duration_ms}ms")
        print(f"  ASR duration: {metrics.total_asr_duration_ms}ms")
        
        print("  [OK] Result processing completed")
        return True
        
    except Exception as e:
        print(f"  [ERROR] Result processing demo failed: {e}")
        return False

async def demo_execution_monitoring():
    """Demo execution monitoring functionality"""
    print("\n[EXECUTION MONITORING] Testing monitoring capabilities")
    print("-" * 50)
    
    try:
        # Initialize components
        scenario_manager = ScenarioManager()
        result_processor = ResultProcessor()
        scenario_executor = ScenarioExecutor(scenario_manager, result_processor)
        
        # List active executions
        active_executions = scenario_executor.list_active_executions()
        print(f"Active executions: {len(active_executions)}")
        
        for execution in active_executions:
            print(f"  - {execution['execution_id']}: {execution['scenario_name']}")
            print(f"    Status: {execution['status']}")
            print(f"    Progress: {execution['completed_steps']}/{execution['total_steps']}")
        
        # List execution history
        execution_history = result_processor.list_execution_results(limit=5)
        print(f"Recent executions: {len(execution_history)}")
        
        for execution in execution_history:
            print(f"  - {execution['execution_id']}: {execution['scenario_name']}")
            print(f"    Status: {execution['status']}")
            print(f"    Time: {execution['start_time']}")
        
        # Get execution statistics
        stats = result_processor.get_execution_statistics()
        print(f"Execution Statistics:")
        print(f"  Total executions: {stats.get('total_executions', 0)}")
        print(f"  Success rate: {stats.get('success_rate', 0):.1f}%")
        print(f"  Average duration: {stats.get('average_duration_ms', 0):.0f}ms")
        print(f"  Recent executions (24h): {stats.get('recent_executions_24h', 0)}")
        
        print("  [OK] Execution monitoring completed")
        return True
        
    except Exception as e:
        print(f"  [ERROR] Execution monitoring demo failed: {e}")
        return False

async def main():
    """Run the complete demo"""
    print_banner()
    
    demo_results = []
    
    # Run demo sections
    print("Running scenario execution demo sections...")
    print()
    
    # 1. Scenario Management
    result1 = await demo_scenario_management()
    demo_results.append(("Scenario Management", result1))
    
    # 2. Scenario Execution
    execution_id = await demo_scenario_execution()
    result2 = execution_id is not None
    demo_results.append(("Scenario Execution", result2))
    
    # 3. Result Processing (if we have an execution ID)
    result3 = True
    if execution_id:
        result3 = await demo_result_processing(execution_id)
    demo_results.append(("Result Processing", result3))
    
    # 4. Execution Monitoring
    result4 = await demo_execution_monitoring()
    demo_results.append(("Execution Monitoring", result4))
    
    # Summary
    print("\n" + "=" * 70)
    print("DEMO SUMMARY")
    print("=" * 70)
    
    passed = 0
    total = len(demo_results)
    
    for section_name, result in demo_results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status} {section_name}")
        if result:
            passed += 1
    
    print()
    print(f"Completed: {passed}/{total} demo sections")
    
    if passed == total:
        print()
        print("[SUCCESS] SCENARIO EXECUTION DEMO COMPLETED SUCCESSFULLY!")
        print()
        print("Ready for production IVR testing with:")
        print("  - Complete scenario definition and management")
        print("  - Step-by-step test execution with audio processing")
        print("  - Real-time execution monitoring and control")
        print("  - Comprehensive result analysis and reporting")
        print("  - Turkish BERT intent recognition integration")
        print("  - DTMF tone generation for IVR navigation")
        print()
        print("Next Steps:")
        print("  1. Start test controller: python src/main.py")
        print("  2. Create scenarios: python sample_scenarios.py")
        print("  3. Execute scenarios: POST /api/v1/scenarios/{id}/execute")
        print("  4. Monitor progress: GET /api/v1/executions/{id}/status")
        print("  5. View results: GET /api/v1/executions/{id}/results")
    else:
        print(f"[WARNING] {total - passed} demo sections had issues. Check implementation.")
    
    return passed == total

if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\nDemo cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nDemo failed: {e}")
        sys.exit(1)