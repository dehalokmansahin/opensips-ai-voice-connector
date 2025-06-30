#!/usr/bin/env python3
"""
Debug script to manually start stream for existing calls
"""
import asyncio
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from transports.call_manager import CallManager
from pipeline.manager import EnhancedPipelineManager

async def debug_start_stream():
    """Find the active call and start its stream"""
    
    # Get the call key from the logs (451458fe7e5449dcb2a189d14cb67a73)
    call_key = "451458fe7e5449dcb2a189d14cb67a73"
    
    print(f"🔧 DEBUG: Attempting to start stream for call: {call_key}")
    
    # We need to access the running application's call manager
    # Since we can't directly access it, we'll create a new connection
    # and try to find the active call
    
    # For now, let's just print the command that would work
    print(f"""
    To manually start the stream for the active call, you can:
    
    1. Add this debug endpoint to your main.py:
    
    @app.post("/debug/start_stream/{{call_key}}")
    async def debug_start_stream_endpoint(call_key: str):
        try:
            call = connector.call_manager.get_call(call_key)
            if call and call.pipeline_manager:
                await call.pipeline_manager.start_stream()
                return {{"status": "success", "message": f"Stream started for call {{call_key}}"}}
            else:
                return {{"status": "error", "message": f"Call {{call_key}} not found"}}
        except Exception as e:
            return {{"status": "error", "message": str(e)}}
    
    2. Then call:
    curl -X POST http://localhost:8000/debug/start_stream/{call_key}
    
    Or execute this Python command in the container:
    
    docker exec -it opensips-ai-voice-connector python -c "
    import asyncio
    import sys
    sys.path.append('/app/src')
    from main import connector
    async def start_stream():
        call = connector.call_manager.get_call('{call_key}')
        if call and call.pipeline_manager:
            await call.pipeline_manager.start_stream()
            print('Stream started successfully!')
        else:
            print('Call not found or no pipeline manager')
    asyncio.run(start_stream())
    "
    """)

if __name__ == "__main__":
    asyncio.run(debug_start_stream()) 