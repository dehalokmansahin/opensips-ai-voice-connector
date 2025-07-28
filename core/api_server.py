"""
HTTP API Server for OpenSIPS AI Core
"""

import logging
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(title="OpenSIPS AI Core API", version="1.0.0")

# Global reference to the connector
connector = None

class CallStartRequest(BaseModel):
    """Call start webhook payload"""
    caller: str
    called: str
    call_id: str
    method: str
    timestamp: str
    message: Optional[str] = None

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "opensips-ai-core"
    }

@app.post("/api/v1/call/start")
async def handle_call_start(request: CallStartRequest):
    """Handle OpenSIPS call start webhook"""
    logger.info(f"Received call start: {request.call_id} from {request.caller} to {request.called}")
    
    try:
        # TODO: Integrate with pipeline manager for actual call processing
        # For now, just accept all calls
        
        return {
            "action": "accept",
            "message": "Call accepted for IVR processing",
            "call_id": request.call_id,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error handling call start: {e}")
        return {
            "action": "reject",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

@app.get("/api/v1/status")
async def get_status():
    """Get AI Core status"""
    return {
        "status": "operational",
        "services": {
            "asr": "connected" if connector and connector.service_registry else "disconnected",
            "tts": "connected" if connector and connector.service_registry else "disconnected",
            "intent": "connected" if connector and connector.service_registry else "disconnected"
        },
        "timestamp": datetime.now().isoformat()
    }

def set_connector(conn):
    """Set the connector reference"""
    global connector
    connector = conn