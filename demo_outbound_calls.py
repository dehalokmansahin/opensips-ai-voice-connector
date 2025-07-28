#!/usr/bin/env python3
"""
Demo script for OpenSIPS Outbound Call Manager
Shows how to initiate and manage outbound calls for IVR testing
"""

import asyncio
import logging
import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import directly from the module file to avoid core dependencies
import importlib.util
spec = importlib.util.spec_from_file_location(
    "outbound_call_manager", 
    "core/opensips/outbound_call_manager.py"
)
outbound_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(outbound_module)

OutboundCallManager = outbound_module.OutboundCallManager
CallState = outbound_module.CallState

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def demo_outbound_calls():
    """Demonstrate outbound call functionality"""
    
    print("=== OpenSIPS Outbound Call Manager Demo ===\n")
    
    # Initialize call manager
    manager = OutboundCallManager(mi_host="127.0.0.1", mi_port=8080)
    print(f"Initialized OutboundCallManager: {manager.mi_url}")
    
    try:
        # Check OpenSIPS availability
        print("\n1. Checking OpenSIPS MI interface availability...")
        health = await manager.health_check()
        print(f"Health Status: {health['status']}")
        if health['status'] == 'unhealthy':
            print(f"Note: OpenSIPS not running - will use fallback simulation")
            print(f"Error: {health.get('error', 'Unknown')}")
        
        # Initiate test calls
        print("\n2. Initiating outbound calls...")
        
        call_id1 = await manager.initiate_call(
            target_number="+90555123456", 
            caller_id="IVR_TEST_BANK"
        )
        print(f"Call 1 initiated: {call_id1}")
        
        call_id2 = await manager.initiate_call(
            target_number="+90555654321",
            caller_id="IVR_TEST_SUPPORT" 
        )
        print(f"Call 2 initiated: {call_id2}")
        
        # Wait a moment for calls to establish
        await asyncio.sleep(1)
        
        # Check call status
        print("\n3. Checking call status...")
        for call_id in [call_id1, call_id2]:
            status = await manager.get_call_status(call_id)
            if status:
                print(f"Call {call_id}: {status['state']} to {status['target_number']}")
                print(f"  - RTP Port: {status['rtp_local_port']}")
                print(f"  - Started: {status['start_time']}")
        
        # Get active calls
        print("\n4. Active calls summary...")
        active_calls = await manager.get_active_calls()
        print(f"Total active calls: {len(active_calls)}")
        
        # Simulate call events (normally these would come from OpenSIPS)
        print("\n5. Simulating call events...")
        
        # Simulate call 1 ringing
        await manager.handle_call_event({
            "callid": call_id1,
            "event": "ringing"
        })
        print(f"Call {call_id1}: Ringing")
        
        # Simulate call 1 answered
        await manager.handle_call_event({
            "callid": call_id1,
            "event": "answered",
            "rtp_remote_ip": "192.168.1.100",
            "rtp_remote_port": "20000"
        })
        print(f"Call {call_id1}: Answered")
        
        # Check updated status
        status = await manager.get_call_status(call_id1)
        if status:
            print(f"  - State: {status['state']}")
            print(f"  - Connected: {status['connect_time']}")
            print(f"  - Remote RTP: {status['rtp_remote_ip']}:{status['rtp_remote_port']}")
        
        # Wait a bit more
        await asyncio.sleep(2)
        
        # Terminate calls
        print("\n6. Terminating calls...")
        
        success1 = await manager.terminate_call(call_id1, "Demo completed")
        print(f"Call {call_id1} termination: {'Success' if success1 else 'Failed'}")
        
        success2 = await manager.terminate_call(call_id2, "Demo completed") 
        print(f"Call {call_id2} termination: {'Success' if success2 else 'Failed'}")
        
        # Final status check
        print("\n7. Final status...")
        active_calls = await manager.get_active_calls()
        print(f"Remaining active calls: {len(active_calls)}")
        
        print("\n8. Call history...")
        for call_id in [call_id1, call_id2]:
            status = await manager.get_call_status(call_id)
            if status:
                print(f"Call {call_id}: {status['state']}")
                if status['end_time']:
                    print(f"  - Duration: {status['end_time']} - {status['start_time']}")
        
    except Exception as e:
        logger.error(f"Demo error: {e}")
        
    finally:
        # Cleanup
        print("\n9. Shutting down...")
        await manager.shutdown()
        print("Demo complete!")

async def demo_rtp_allocation():
    """Demonstrate RTP port allocation"""
    print("\n=== RTP Port Allocation Demo ===")
    
    manager = OutboundCallManager()
    
    print("Allocating RTP ports:")
    for i in range(5):
        port = manager._allocate_rtp_port()
        print(f"  Port {i+1}: {port}")
    
    print("\nRTP port range: {} - {}".format(
        manager.rtp_min_port, manager.rtp_max_port
    ))

def main():
    """Main demo function"""
    print("OpenSIPS Outbound Call Manager Demo")
    print("===================================")
    
    try:
        # Run the outbound calls demo
        asyncio.run(demo_outbound_calls())
        
        # Run the RTP allocation demo
        asyncio.run(demo_rtp_allocation())
        
    except KeyboardInterrupt:
        print("\nDemo interrupted by user")
    except Exception as e:
        print(f"\nDemo failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()