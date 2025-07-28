#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IVR Test Management Web Interface
Turkish Banking IVR Flow Automation System - Web Frontend
"""

import os
import sys
import json
import time
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

# Add core to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'core'))

try:
    from fastapi import FastAPI, Request, HTTPException, Form, Depends
    from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
    from fastapi.templating import Jinja2Templates
    from fastapi.staticfiles import StaticFiles
    from fastapi.middleware.cors import CORSMiddleware
    import uvicorn
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    FastAPI = None

import sqlite3
import asyncio
import aiohttp
from dataclasses import dataclass, asdict

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if not FASTAPI_AVAILABLE:
    raise ImportError("FastAPI required. Install with: pip install fastapi uvicorn jinja2 python-multipart")

# Web application setup
app = FastAPI(
    title="IVR Test Management System",
    description="Turkish Banking IVR Flow Automation - Web Interface",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Templates and static files
web_dir = Path(__file__).parent
templates = Jinja2Templates(directory=str(web_dir / "templates"))
app.mount("/static", StaticFiles(directory=str(web_dir / "static")), name="static")

# Services configuration
SERVICES = {
    "intent": f"http://{os.getenv('INTENT_SERVICE_URL', 'localhost:5000')}",
    "test_controller": f"http://{os.getenv('TEST_CONTROLLER_URL', 'localhost:50055')}",
    "asr": os.getenv('ASR_SERVICE_URL', 'localhost:50051'),
    "tts": os.getenv('TTS_SERVICE_URL', 'localhost:50053')
}

logger.info(f"Services configuration: {SERVICES}")

# Database setup
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "test_controller", "test_scenarios.db")

@dataclass
class TestScenario:
    """Test scenario data model"""
    id: Optional[int] = None
    name: str = ""
    description: str = ""
    target_phone: str = ""
    timeout_seconds: int = 300
    steps: List[Dict] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    status: str = "draft"
    
    def __post_init__(self):
        if self.steps is None:
            self.steps = []
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()
        if self.updated_at is None:
            self.updated_at = self.created_at

class DatabaseManager:
    """Database operations manager"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize database with required tables"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS test_scenarios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    description TEXT,
                    target_phone TEXT NOT NULL,
                    timeout_seconds INTEGER DEFAULT 300,
                    steps TEXT,  -- JSON serialized steps
                    created_at TEXT,
                    updated_at TEXT,
                    status TEXT DEFAULT 'draft'
                )
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS test_executions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scenario_id INTEGER,
                    status TEXT DEFAULT 'pending',
                    start_time TEXT,
                    end_time TEXT,
                    results TEXT,  -- JSON serialized results
                    FOREIGN KEY (scenario_id) REFERENCES test_scenarios (id)
                )
            ''')
            conn.commit()
    
    def get_scenarios(self) -> List[TestScenario]:
        """Get all test scenarios"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute('''
                SELECT * FROM test_scenarios ORDER BY updated_at DESC
            ''')
            
            scenarios = []
            for row in cursor.fetchall():
                steps = json.loads(row['steps']) if row['steps'] else []
                scenario = TestScenario(
                    id=row['id'],
                    name=row['name'],
                    description=row['description'],
                    target_phone=row['target_phone'],
                    timeout_seconds=row['timeout_seconds'],
                    steps=steps,
                    created_at=row['created_at'],
                    updated_at=row['updated_at'],
                    status=row['status']
                )
                scenarios.append(scenario)
            
            return scenarios
    
    def get_scenario(self, scenario_id: int) -> Optional[TestScenario]:
        """Get specific test scenario"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute('''
                SELECT * FROM test_scenarios WHERE id = ?
            ''', (scenario_id,))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            steps = json.loads(row['steps']) if row['steps'] else []
            return TestScenario(
                id=row['id'],
                name=row['name'],
                description=row['description'],
                target_phone=row['target_phone'],
                timeout_seconds=row['timeout_seconds'],
                steps=steps,
                created_at=row['created_at'],
                updated_at=row['updated_at'],
                status=row['status']
            )
    
    def create_scenario(self, scenario: TestScenario) -> int:
        """Create new test scenario"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                INSERT INTO test_scenarios 
                (name, description, target_phone, timeout_seconds, steps, created_at, updated_at, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                scenario.name,
                scenario.description,
                scenario.target_phone,
                scenario.timeout_seconds,
                json.dumps(scenario.steps),
                scenario.created_at,
                scenario.updated_at,
                scenario.status
            ))
            conn.commit()
            return cursor.lastrowid
    
    def update_scenario(self, scenario_id: int, scenario: TestScenario) -> bool:
        """Update existing test scenario"""
        scenario.updated_at = datetime.now().isoformat()
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                UPDATE test_scenarios SET
                name = ?, description = ?, target_phone = ?, timeout_seconds = ?,
                steps = ?, updated_at = ?, status = ?
                WHERE id = ?
            ''', (
                scenario.name,
                scenario.description,
                scenario.target_phone,
                scenario.timeout_seconds,
                json.dumps(scenario.steps),
                scenario.updated_at,
                scenario.status,
                scenario_id
            ))
            conn.commit()
            return cursor.rowcount > 0
    
    def delete_scenario(self, scenario_id: int) -> bool:
        """Delete test scenario"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('DELETE FROM test_scenarios WHERE id = ?', (scenario_id,))
            conn.commit()
            return cursor.rowcount > 0

# Initialize database manager
db_manager = DatabaseManager(DB_PATH)

# Web Routes

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard page"""
    scenarios = db_manager.get_scenarios()
    recent_scenarios = scenarios[:5]  # Show last 5 scenarios
    
    # System status check
    system_status = await check_system_health()
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "recent_scenarios": recent_scenarios,
        "total_scenarios": len(scenarios),
        "system_status": system_status,
        "page_title": "IVR Test Management Dashboard"
    })

@app.get("/scenarios", response_class=HTMLResponse)
async def scenarios_list(request: Request):
    """Test scenarios list page"""
    scenarios = db_manager.get_scenarios()
    
    return templates.TemplateResponse("scenarios/list.html", {
        "request": request,
        "scenarios": scenarios,
        "page_title": "Test Scenarios"
    })

@app.get("/scenarios/create", response_class=HTMLResponse)
async def scenarios_create_page(request: Request):
    """Scenario creation page"""
    return templates.TemplateResponse("scenarios/create.html", {
        "request": request,
        "page_title": "Create Test Scenario"
    })

@app.post("/scenarios/create")
async def scenarios_create(
    name: str = Form(...),
    description: str = Form(""),
    target_phone: str = Form(...),
    timeout_seconds: int = Form(300),
    steps_data: str = Form("[]")
):
    """Create new test scenario"""
    try:
        steps = json.loads(steps_data) if steps_data else []
        
        scenario = TestScenario(
            name=name,
            description=description,
            target_phone=target_phone,
            timeout_seconds=timeout_seconds,
            steps=steps,
            status="draft"
        )
        
        scenario_id = db_manager.create_scenario(scenario)
        logger.info(f"Created new scenario: {name} (ID: {scenario_id})")
        
        return RedirectResponse(url="/scenarios", status_code=303)
        
    except Exception as e:
        logger.error(f"Failed to create scenario: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/scenarios/{scenario_id}", response_class=HTMLResponse)
async def scenarios_view(request: Request, scenario_id: int):
    """View specific test scenario"""
    scenario = db_manager.get_scenario(scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    
    return templates.TemplateResponse("scenarios/view.html", {
        "request": request,
        "scenario": scenario,
        "page_title": f"Scenario: {scenario.name}"
    })

@app.get("/scenarios/{scenario_id}/edit", response_class=HTMLResponse)
async def scenarios_edit_page(request: Request, scenario_id: int):
    """Scenario editing page"""
    scenario = db_manager.get_scenario(scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    
    return templates.TemplateResponse("scenarios/edit.html", {
        "request": request,
        "scenario": scenario,
        "page_title": f"Edit Scenario: {scenario.name}"
    })

@app.post("/scenarios/{scenario_id}/edit")
async def scenarios_update(
    scenario_id: int,
    name: str = Form(...),
    description: str = Form(""),
    target_phone: str = Form(...),
    timeout_seconds: int = Form(300),
    steps_data: str = Form("[]"),
    status: str = Form("draft")
):
    """Update existing test scenario"""
    try:
        steps = json.loads(steps_data) if steps_data else []
        
        scenario = TestScenario(
            name=name,
            description=description,
            target_phone=target_phone,
            timeout_seconds=timeout_seconds,
            steps=steps,
            status=status
        )
        
        success = db_manager.update_scenario(scenario_id, scenario)
        if not success:
            raise HTTPException(status_code=404, detail="Scenario not found")
        
        logger.info(f"Updated scenario: {name} (ID: {scenario_id})")
        return RedirectResponse(url=f"/scenarios/{scenario_id}", status_code=303)
        
    except Exception as e:
        logger.error(f"Failed to update scenario: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/scenarios/{scenario_id}/delete")
async def scenarios_delete(scenario_id: int):
    """Delete test scenario"""
    try:
        success = db_manager.delete_scenario(scenario_id)
        if not success:
            raise HTTPException(status_code=404, detail="Scenario not found")
        
        logger.info(f"Deleted scenario ID: {scenario_id}")
        return RedirectResponse(url="/scenarios", status_code=303)
        
    except Exception as e:
        logger.error(f"Failed to delete scenario: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/scenarios/{scenario_id}/duplicate")
async def scenarios_duplicate(scenario_id: int):
    """Duplicate existing test scenario"""
    try:
        original = db_manager.get_scenario(scenario_id)
        if not original:
            raise HTTPException(status_code=404, detail="Scenario not found")
        
        # Create duplicate with new name
        duplicate = TestScenario(
            name=f"{original.name} (Copy)",
            description=original.description,
            target_phone=original.target_phone,
            timeout_seconds=original.timeout_seconds,
            steps=original.steps.copy(),
            status="draft"
        )
        
        new_id = db_manager.create_scenario(duplicate)
        logger.info(f"Duplicated scenario {scenario_id} as {new_id}")
        
        return RedirectResponse(url=f"/scenarios/{new_id}/edit", status_code=303)
        
    except Exception as e:
        logger.error(f"Failed to duplicate scenario: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# API Routes

@app.get("/api/v1/scenarios")
async def api_get_scenarios():
    """Get all test scenarios (API)"""
    scenarios = db_manager.get_scenarios()
    return [asdict(scenario) for scenario in scenarios]

@app.get("/api/v1/scenarios/{scenario_id}")
async def api_get_scenario(scenario_id: int):
    """Get specific test scenario (API)"""
    scenario = db_manager.get_scenario(scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return asdict(scenario)

@app.get("/api/v1/system/health")
async def api_system_health():
    """System health check (API)"""
    return await check_system_health()

async def check_system_health() -> Dict[str, Any]:
    """Check health of all system services"""
    health_status = {
        "overall": "healthy",
        "services": {},
        "timestamp": datetime.now().isoformat()
    }
    
    # Check Intent Service
    try:
        timeout = aiohttp.ClientTimeout(total=3)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"{SERVICES['intent']}/health") as response:
                if response.status == 200:
                    health_status["services"]["intent"] = {"status": "healthy", "response_time": "< 3s"}
                else:
                    health_status["services"]["intent"] = {"status": "unhealthy", "error": f"HTTP {response.status}"}
                    health_status["overall"] = "partial"
    except Exception as e:
        health_status["services"]["intent"] = {"status": "error", "error": str(e)}
        health_status["overall"] = "partial"
    
    # Check Test Controller Service
    try:
        timeout = aiohttp.ClientTimeout(total=3)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"{SERVICES['test_controller']}/health") as response:
                if response.status == 200:
                    health_status["services"]["test_controller"] = {"status": "healthy", "response_time": "< 3s"}
                else:
                    health_status["services"]["test_controller"] = {"status": "unhealthy", "error": f"HTTP {response.status}"}
                    health_status["overall"] = "partial"
    except Exception as e:
        health_status["services"]["test_controller"] = {"status": "error", "error": str(e)}
        health_status["overall"] = "partial"
    
    # Database check
    try:
        scenarios = db_manager.get_scenarios()
        health_status["services"]["database"] = {"status": "healthy", "scenarios_count": len(scenarios)}
    except Exception as e:
        health_status["services"]["database"] = {"status": "error", "error": str(e)}
        health_status["overall"] = "unhealthy"
    
    return health_status

# Test execution endpoint (for Epic 3.2)
@app.post("/api/v1/scenarios/{scenario_id}/execute")
async def api_execute_scenario(scenario_id: int):
    """Execute test scenario (future implementation)"""
    scenario = db_manager.get_scenario(scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    
    # TODO: Integrate with Test Controller Service for actual execution
    return {
        "execution_id": f"exec_{scenario_id}_{int(time.time())}",
        "status": "started",
        "scenario_id": scenario_id,
        "message": "Test execution started (mock implementation)"
    }


# OpenSIPS Integration Endpoints

@app.get("/api/v1/opensips/status")
async def get_opensips_status():
    """Get OpenSIPS server status and statistics"""
    try:
        # Try to get statistics from OpenSIPS HTTP MI
        async with aiohttp.ClientSession() as session:
            async with session.get("http://opensips-server:8888/mi/get_statistics?params=core:") as response:
                if response.status == 200:
                    stats_data = await response.text()
                    return {
                        "status": "healthy",
                        "statistics": stats_data,
                        "timestamp": datetime.now().isoformat()
                    }
                else:
                    return {
                        "status": "unhealthy",
                        "error": f"HTTP {response.status}",
                        "timestamp": datetime.now().isoformat()
                    }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

@app.post("/api/v1/opensips/call/start")
async def start_opensips_call(request: Request):
    """Handle OpenSIPS call start webhook"""
    try:
        call_data = await request.json()
        logger.info(f"OpenSIPS call started: {call_data}")
        
        # Here you would integrate with your IVR logic
        # For now, just return a basic response
        
        return {
            "action": "accept",
            "message": "Call accepted for IVR processing",
            "call_id": call_data.get("call_id"),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error handling OpenSIPS call start: {e}")
        return {
            "action": "reject",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

@app.get("/opensips", response_class=HTMLResponse)  
async def opensips_dashboard(request: Request):
    """OpenSIPS monitoring and management dashboard"""
    
    # Get OpenSIPS status
    opensips_status = await get_opensips_status()
    
    context = {
        "request": request,
        "title": "OpenSIPS Management",
        "opensips_status": opensips_status,
        "current_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    return templates.TemplateResponse("opensips/dashboard.html", context)


def run_web_server():
    """Start the web server"""
    logger.info("Starting IVR Test Management Web Interface")
    logger.info(f"Database: {DB_PATH}")
    logger.info("Web interface available at: http://localhost:8000")
    
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info"
    )

if __name__ == "__main__":
    run_web_server()