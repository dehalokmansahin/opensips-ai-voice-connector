#!/usr/bin/env python3
"""
Sample IVR Test Scenarios
Creates sample scenarios for testing the scenario execution system
"""

import sys
import os
from datetime import datetime

# Add parent directories to path for core imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from core.ivr_testing import TestStep, TestScenario, ScenarioManager

def create_bank_balance_inquiry_scenario() -> TestScenario:
    """Create a simple bank balance inquiry test scenario"""
    steps = [
        # Step 1: Wait for initial IVR greeting
        TestStep(
            step_number=1,
            step_type="asr_listen",
            expected_intent="greeting",
            confidence_threshold=0.8,
            max_duration_ms=10000,
            timeout_ms=15000
        ),
        
        # Step 2: Send DTMF "1" for balance inquiry
        TestStep(
            step_number=2,
            step_type="dtmf_send",
            dtmf_sequence="1",
            timeout_ms=5000
        ),
        
        # Step 3: Listen for balance response
        TestStep(
            step_number=3,
            step_type="asr_listen",
            max_duration_ms=8000,
            timeout_ms=12000
        ),
        
        # Step 4: Validate balance response intent
        TestStep(
            step_number=4,
            step_type="intent_validate",
            expected_intent="balance_response",
            pass_criteria="intent_match"
        )
    ]
    
    return TestScenario(
        scenario_id="bank_balance_inquiry",
        name="Bank Balance Inquiry Test",
        description="Test automated balance inquiry through Turkish banking IVR",
        target_phone="+905551234567",  # Mock Turkish phone number
        timeout_seconds=120,
        steps=steps,
        created_at=datetime.now().isoformat(),
        created_by="system",
        tags=["banking", "balance", "turkish", "automated"]
    )

def create_customer_service_transfer_scenario() -> TestScenario:
    """Create a customer service transfer test scenario"""
    steps = [
        # Step 1: Wait for initial greeting
        TestStep(
            step_number=1,
            step_type="asr_listen",
            expected_intent="greeting",
            confidence_threshold=0.8,
            max_duration_ms=10000
        ),
        
        # Step 2: Send DTMF "0" for customer service
        TestStep(
            step_number=2,
            step_type="dtmf_send",
            dtmf_sequence="0",
            timeout_ms=3000
        ),
        
        # Step 3: Listen for transfer confirmation
        TestStep(
            step_number=3,
            step_type="asr_listen",
            max_duration_ms=8000
        ),
        
        # Step 4: Validate transfer intent
        TestStep(
            step_number=4,
            step_type="intent_validate",
            expected_intent="transfer_confirmation",
            pass_criteria="intent_match"
        )
    ]
    
    return TestScenario(
        scenario_id="customer_service_transfer",
        name="Customer Service Transfer Test",
        description="Test transfer to customer service representative",
        target_phone="+905551234567",
        timeout_seconds=90,
        steps=steps,
        created_at=datetime.now().isoformat(),
        created_by="system",
        tags=["banking", "customer_service", "transfer", "turkish"]
    )

def create_multi_menu_navigation_scenario() -> TestScenario:
    """Create a complex multi-menu navigation scenario"""
    steps = [
        # Step 1: Initial greeting
        TestStep(
            step_number=1,
            step_type="asr_listen",
            expected_intent="greeting",
            max_duration_ms=10000
        ),
        
        # Step 2: Navigate to services menu (2)
        TestStep(
            step_number=2,
            step_type="dtmf_send",
            dtmf_sequence="2"
        ),
        
        # Step 3: Listen for services menu
        TestStep(
            step_number=3,
            step_type="asr_listen",
            expected_intent="menu_options",
            max_duration_ms=8000
        ),
        
        # Step 4: Navigate to card services (1)
        TestStep(
            step_number=4,
            step_type="dtmf_send",
            dtmf_sequence="1"
        ),
        
        # Step 5: Listen for card services menu
        TestStep(
            step_number=5,
            step_type="asr_listen",
            max_duration_ms=8000
        ),
        
        # Step 6: Validate card services intent
        TestStep(
            step_number=6,
            step_type="intent_validate",
            expected_intent="card_services",
            pass_criteria="intent_match"
        ),
        
        # Step 7: Go back to main menu (#)
        TestStep(
            step_number=7,
            step_type="dtmf_send",
            dtmf_sequence="#"
        ),
        
        # Step 8: Validate main menu return
        TestStep(
            step_number=8,
            step_type="intent_validate",
            expected_intent="menu_options",
            pass_criteria="intent_match"
        )
    ]
    
    return TestScenario(
        scenario_id="multi_menu_navigation",
        name="Multi-Menu Navigation Test",
        description="Test complex navigation through multiple IVR menu levels",
        target_phone="+905551234567",
        timeout_seconds=180,
        steps=steps,
        created_at=datetime.now().isoformat(),
        created_by="system",
        tags=["banking", "navigation", "complex", "menu", "turkish"]
    )

def create_error_handling_scenario() -> TestScenario:
    """Create a scenario to test error handling and fallbacks"""
    steps = [
        # Step 1: Initial greeting
        TestStep(
            step_number=1,
            step_type="asr_listen",
            expected_intent="greeting",
            max_duration_ms=10000
        ),
        
        # Step 2: Send invalid DTMF sequence
        TestStep(
            step_number=2,
            step_type="dtmf_send",
            dtmf_sequence="99"  # Likely invalid option
        ),
        
        # Step 3: Listen for error message
        TestStep(
            step_number=3,
            step_type="asr_listen",
            max_duration_ms=8000
        ),
        
        # Step 4: Validate error handling
        TestStep(
            step_number=4,
            step_type="intent_validate",
            expected_intent="error_invalid_option",
            pass_criteria="intent_match",
            conditional={
                "condition_type": "intent_match",
                "expected_intent": "error_invalid_option",
                "if_true": {
                    "next_step": 5,
                    "action": "continue"
                },
                "if_false": {
                    "next_step": 7,
                    "action": "continue"  # Continue even if error intent not detected
                }
            }
        ),
        
        # Step 5: Send valid DTMF to recover
        TestStep(
            step_number=5,
            step_type="dtmf_send",
            dtmf_sequence="1"
        ),
        
        # Step 6: Validate recovery
        TestStep(
            step_number=6,
            step_type="intent_validate",
            expected_intent="balance_inquiry",
            pass_criteria="intent_match"
        )
    ]
    
    return TestScenario(
        scenario_id="error_handling_test",
        name="Error Handling and Recovery Test",
        description="Test IVR error handling and recovery from invalid inputs",
        target_phone="+905551234567",
        timeout_seconds=150,
        steps=steps,
        created_at=datetime.now().isoformat(),
        created_by="system",
        tags=["banking", "error_handling", "recovery", "validation", "turkish"]
    )

def create_sample_scenarios():
    """Create and save all sample scenarios"""
    print("Creating sample IVR test scenarios...")
    
    # Initialize scenario manager
    scenario_manager = ScenarioManager()
    
    # Create scenarios
    scenarios = [
        create_bank_balance_inquiry_scenario(),
        create_customer_service_transfer_scenario(),
        create_multi_menu_navigation_scenario(),
        create_error_handling_scenario()
    ]
    
    # Save scenarios
    saved_count = 0
    for scenario in scenarios:
        print(f"\nCreating scenario: {scenario.name}")
        print(f"  ID: {scenario.scenario_id}")
        print(f"  Steps: {len(scenario.steps)}")
        print(f"  Timeout: {scenario.timeout_seconds}s")
        print(f"  Tags: {', '.join(scenario.tags or [])}")
        
        # Validate scenario
        is_valid, error = scenario.validate()
        if not is_valid:
            print(f"  [ERROR] Validation failed: {error}")
            continue
        
        # Save scenario
        success = scenario_manager.save_scenario(scenario)
        if success:
            print("  [OK] Scenario saved successfully")
            saved_count += 1
        else:
            print("  [ERROR] Failed to save scenario")
    
    print(f"\n=== Summary ===")
    print(f"Total scenarios created: {len(scenarios)}")
    print(f"Successfully saved: {saved_count}")
    print(f"Failed: {len(scenarios) - saved_count}")
    
    if saved_count > 0:
        print(f"\nSample scenarios are ready for testing!")
        print(f"Use the Test Controller API to execute them:")
        print(f"  POST /api/v1/scenarios/{{scenario_id}}/execute")
        print(f"  GET  /api/v1/scenarios")
        print(f"  GET  /api/v1/executions/{{execution_id}}/status")
    
    return saved_count == len(scenarios)

def main():
    """Main entry point"""
    print("=== IVR Test Scenario Creator ===")
    
    try:
        success = create_sample_scenarios()
        
        if success:
            print("\n[SUCCESS] All sample scenarios created successfully!")
            return 0
        else:
            print("\n[WARNING] Some scenarios failed to create. Check the errors above.")
            return 1
            
    except Exception as e:
        print(f"\n[ERROR] Failed to create scenarios: {e}")
        return 1

if __name__ == "__main__":
    import sys
    sys.exit(main())