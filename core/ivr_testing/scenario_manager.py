"""
IVR Test Scenario Management
Handles loading, validation, and management of test scenarios
"""

import json
import sqlite3
import logging
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class TestStep:
    """Represents a single test step in a scenario"""
    step_number: int
    step_type: str  # tts_prompt, asr_listen, dtmf_send, intent_validate
    
    # Common properties
    timeout_ms: Optional[int] = None
    conditional: Optional[Dict[str, Any]] = None
    
    # TTS prompt properties
    prompt_text: Optional[str] = None
    wait_for_response: Optional[bool] = None
    
    # ASR listen properties
    expected_intent: Optional[str] = None
    confidence_threshold: Optional[float] = None
    max_duration_ms: Optional[int] = None
    
    # DTMF send properties
    dtmf_sequence: Optional[str] = None
    
    # Intent validation properties
    pass_criteria: Optional[str] = None
    
    def validate(self) -> tuple[bool, str]:
        """Validate step configuration"""
        if not self.step_type:
            return False, "step_type is required"
        
        valid_types = ["tts_prompt", "asr_listen", "dtmf_send", "intent_validate"]
        if self.step_type not in valid_types:
            return False, f"Invalid step_type: {self.step_type}. Must be one of {valid_types}"
        
        # Type-specific validation
        if self.step_type == "tts_prompt":
            if not self.prompt_text:
                return False, "prompt_text is required for tts_prompt steps"
        
        elif self.step_type == "asr_listen":
            if self.max_duration_ms and self.max_duration_ms <= 0:
                return False, "max_duration_ms must be positive"
        
        elif self.step_type == "dtmf_send":
            if not self.dtmf_sequence:
                return False, "dtmf_sequence is required for dtmf_send steps"
            # Validate DTMF characters
            valid_dtmf = set("0123456789*#ABCD")
            if not all(c in valid_dtmf for c in self.dtmf_sequence):
                return False, f"Invalid DTMF sequence: {self.dtmf_sequence}"
        
        elif self.step_type == "intent_validate":
            if not self.expected_intent:
                return False, "expected_intent is required for intent_validate steps"
        
        return True, ""

@dataclass
class TestScenario:
    """Represents a complete test scenario"""
    scenario_id: str
    name: str
    description: str
    target_phone: str
    timeout_seconds: int
    steps: List[TestStep]
    
    # Optional metadata
    created_at: Optional[str] = None
    created_by: Optional[str] = None
    tags: Optional[List[str]] = None
    
    def validate(self) -> tuple[bool, str]:
        """Validate scenario configuration"""
        if not self.scenario_id:
            return False, "scenario_id is required"
        
        if not self.name:
            return False, "name is required"
        
        if not self.target_phone:
            return False, "target_phone is required"
        
        if self.timeout_seconds <= 0:
            return False, "timeout_seconds must be positive"
        
        if not self.steps:
            return False, "At least one step is required"
        
        # Validate step numbers are sequential
        expected_step = 1
        for step in self.steps:
            if step.step_number != expected_step:
                return False, f"Step numbers must be sequential. Expected {expected_step}, got {step.step_number}"
            expected_step += 1
        
        # Validate each step
        for step in self.steps:
            is_valid, error = step.validate()
            if not is_valid:
                return False, f"Step {step.step_number}: {error}"
        
        return True, ""
    
    def get_step(self, step_number: int) -> Optional[TestStep]:
        """Get step by number"""
        for step in self.steps:
            if step.step_number == step_number:
                return step
        return None
    
    def get_total_estimated_duration(self) -> int:
        """Estimate total scenario duration in milliseconds"""
        total_ms = 0
        
        for step in self.steps:
            if step.timeout_ms:
                total_ms += step.timeout_ms
            elif step.step_type == "tts_prompt":
                # Estimate TTS duration based on text length
                if step.prompt_text:
                    # Rough estimate: 150 words per minute, plus processing time
                    words = len(step.prompt_text.split())
                    tts_duration = (words / 150) * 60 * 1000  # Convert to ms
                    total_ms += max(tts_duration, 2000)  # Minimum 2 seconds
                else:
                    total_ms += 2000
            elif step.step_type == "asr_listen":
                total_ms += step.max_duration_ms or 5000  # Default 5 seconds
            elif step.step_type == "dtmf_send":
                # Estimate DTMF duration
                if step.dtmf_sequence:
                    # ~200ms per tone + gaps
                    total_ms += len(step.dtmf_sequence) * 400
                else:
                    total_ms += 1000
            elif step.step_type == "intent_validate":
                total_ms += 1000  # Processing time
        
        return min(total_ms, self.timeout_seconds * 1000)

class ScenarioManager:
    """Manages test scenarios - loading, validation, storage"""
    
    def __init__(self, db_path: str = "ivr_testing.db"):
        """
        Initialize scenario manager
        
        Args:
            db_path: Path to SQLite database
        """
        self.db_path = db_path
        self._ensure_database()
    
    def _ensure_database(self):
        """Create database tables if they don't exist"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS test_scenarios (
                    scenario_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    target_phone TEXT NOT NULL,
                    timeout_seconds INTEGER NOT NULL,
                    scenario_data TEXT NOT NULL,  -- JSON blob
                    created_at TEXT NOT NULL,
                    created_by TEXT,
                    tags TEXT,  -- JSON array
                    last_modified TEXT,
                    is_active BOOLEAN DEFAULT 1
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_scenarios_name 
                ON test_scenarios(name)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_scenarios_tags
                ON test_scenarios(tags)
            """)
    
    def save_scenario(self, scenario: TestScenario) -> bool:
        """
        Save scenario to database
        
        Args:
            scenario: Test scenario to save
            
        Returns:
            True if saved successfully
        """
        try:
            # Validate scenario first
            is_valid, error = scenario.validate()
            if not is_valid:
                logger.error(f"Invalid scenario: {error}")
                return False
            
            # Set timestamps
            now = datetime.now().isoformat()
            if not scenario.created_at:
                scenario.created_at = now
            
            # Convert to JSON
            scenario_dict = asdict(scenario)
            scenario_json = json.dumps(scenario_dict, ensure_ascii=False)
            tags_json = json.dumps(scenario.tags or [])
            
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO test_scenarios 
                    (scenario_id, name, description, target_phone, timeout_seconds,
                     scenario_data, created_at, created_by, tags, last_modified)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    scenario.scenario_id,
                    scenario.name,
                    scenario.description,
                    scenario.target_phone,
                    scenario.timeout_seconds,
                    scenario_json,
                    scenario.created_at,
                    scenario.created_by,
                    tags_json,
                    now
                ))
            
            logger.info(f"Scenario saved: {scenario.scenario_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save scenario: {e}")
            return False
    
    def load_scenario(self, scenario_id: str) -> Optional[TestScenario]:
        """
        Load scenario from database
        
        Args:
            scenario_id: ID of scenario to load
            
        Returns:
            TestScenario or None if not found
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    SELECT scenario_data FROM test_scenarios 
                    WHERE scenario_id = ? AND is_active = 1
                """, (scenario_id,))
                
                row = cursor.fetchone()
                if not row:
                    return None
                
                # Parse JSON data
                scenario_dict = json.loads(row[0])
                
                # Convert steps
                steps = []
                for step_dict in scenario_dict.get('steps', []):
                    step = TestStep(**step_dict)
                    steps.append(step)
                
                # Create scenario
                scenario_dict['steps'] = steps
                scenario = TestScenario(**scenario_dict)
                
                return scenario
                
        except Exception as e:
            logger.error(f"Failed to load scenario {scenario_id}: {e}")
            return None
    
    def list_scenarios(self, tags: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        List all active scenarios
        
        Args:
            tags: Optional tags to filter by
            
        Returns:
            List of scenario metadata
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                query = """
                    SELECT scenario_id, name, description, target_phone, 
                           timeout_seconds, created_at, tags
                    FROM test_scenarios 
                    WHERE is_active = 1
                """
                
                if tags:
                    # Simple tag filtering (could be improved with proper JSON queries)
                    query += " AND ("
                    tag_conditions = []
                    for tag in tags:
                        tag_conditions.append("tags LIKE ?")
                    query += " OR ".join(tag_conditions) + ")"
                    
                    params = [f'%"{tag}"%' for tag in tags]
                else:
                    params = []
                
                query += " ORDER BY name"
                
                cursor = conn.execute(query, params)
                rows = cursor.fetchall()
                
                scenarios = []
                for row in rows:
                    scenarios.append({
                        'scenario_id': row[0],
                        'name': row[1],
                        'description': row[2],
                        'target_phone': row[3],
                        'timeout_seconds': row[4],
                        'created_at': row[5],
                        'tags': json.loads(row[6] or '[]')
                    })
                
                return scenarios
                
        except Exception as e:
            logger.error(f"Failed to list scenarios: {e}")
            return []
    
    def delete_scenario(self, scenario_id: str) -> bool:
        """
        Soft delete scenario (mark as inactive)
        
        Args:
            scenario_id: ID of scenario to delete
            
        Returns:
            True if deleted successfully
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    UPDATE test_scenarios 
                    SET is_active = 0, last_modified = ?
                    WHERE scenario_id = ?
                """, (datetime.now().isoformat(), scenario_id))
                
                if cursor.rowcount > 0:
                    logger.info(f"Scenario deleted: {scenario_id}")
                    return True
                else:
                    logger.warning(f"Scenario not found for deletion: {scenario_id}")
                    return False
                
        except Exception as e:
            logger.error(f"Failed to delete scenario {scenario_id}: {e}")
            return False
    
    def load_scenario_from_file(self, file_path: Union[str, Path]) -> Optional[TestScenario]:
        """
        Load scenario from JSON file
        
        Args:
            file_path: Path to JSON file
            
        Returns:
            TestScenario or None if failed
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Convert steps
            steps = []
            for step_dict in data.get('steps', []):
                step = TestStep(**step_dict)
                steps.append(step)
            
            # Create scenario
            data['steps'] = steps
            scenario = TestScenario(**data)
            
            # Validate
            is_valid, error = scenario.validate()
            if not is_valid:
                logger.error(f"Invalid scenario in file {file_path}: {error}")
                return None
            
            return scenario
            
        except Exception as e:
            logger.error(f"Failed to load scenario from file {file_path}: {e}")
            return None
    
    def export_scenario_to_file(self, scenario_id: str, file_path: Union[str, Path]) -> bool:
        """
        Export scenario to JSON file
        
        Args:
            scenario_id: ID of scenario to export
            file_path: Path where to save the file
            
        Returns:
            True if exported successfully
        """
        try:
            scenario = self.load_scenario(scenario_id)
            if not scenario:
                logger.error(f"Scenario not found: {scenario_id}")
                return False
            
            # Convert to dictionary
            scenario_dict = asdict(scenario)
            
            # Save to file
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(scenario_dict, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Scenario exported to {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to export scenario {scenario_id}: {e}")
            return False