"""
Database utilities for IVR test automation system.
Handles SQLite database connections, initialization, and CRUD operations.
"""

import sqlite3
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, asdict
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# Database configuration
DATABASE_DIR = Path(__file__).parent.parent.parent / "data" / "databases"
TEST_DB_PATH = DATABASE_DIR / "test_scenarios.db"

@dataclass
class TestScenario:
    """Data model for test scenarios."""
    scenario_id: Optional[int] = None
    name: str = ""
    description: str = ""
    target_phone: str = ""
    steps: List[Dict[str, Any]] = None
    timeout_seconds: int = 300
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.steps is None:
            self.steps = []

@dataclass
class TestExecution:
    """Data model for test executions."""
    execution_id: Optional[int] = None
    scenario_id: int = 0
    status: str = "running"  # running, completed, failed, timeout
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    call_id: Optional[str] = None
    final_result: Optional[str] = None  # pass, fail
    error_message: Optional[str] = None

@dataclass
class StepExecution:
    """Data model for individual step executions."""
    step_id: Optional[int] = None
    execution_id: int = 0
    step_number: int = 0
    step_type: str = ""  # prompt, dtmf, wait, validate
    expected_intent: Optional[str] = None
    actual_intent: Optional[str] = None
    confidence: Optional[float] = None
    audio_transcript: Optional[str] = None
    status: str = "pending"  # pending, running, completed, failed
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    error_message: Optional[str] = None

@dataclass
class IntentTrainingData:
    """Data model for intent training data."""
    training_id: Optional[int] = None
    text_sample: str = ""
    intent_label: str = ""
    confidence_threshold: float = 0.85
    source: str = "manual"  # manual, recorded, synthetic
    validation_status: str = "pending"  # pending, validated, rejected
    created_at: Optional[datetime] = None

class DatabaseManager:
    """Manages SQLite database connections and operations."""
    
    def __init__(self, db_path: Union[str, Path] = None):
        """Initialize database manager with optional custom path."""
        self.db_path = Path(db_path) if db_path else TEST_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
    @contextmanager
    def get_connection(self):
        """Context manager for database connections."""
        conn = None
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row  # Enable dict-like access
            yield conn
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            if conn:
                conn.close()
    
    def initialize_database(self) -> bool:
        """Initialize database schema with all required tables."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Create test_scenarios table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS test_scenarios (
                        scenario_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        description TEXT,
                        target_phone TEXT NOT NULL,
                        steps TEXT,  -- JSON string
                        timeout_seconds INTEGER DEFAULT 300,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Create test_executions table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS test_executions (
                        execution_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        scenario_id INTEGER NOT NULL,
                        status TEXT CHECK (status IN ('running', 'completed', 'failed', 'timeout')) DEFAULT 'running',
                        start_time TIMESTAMP,
                        end_time TIMESTAMP,
                        call_id TEXT,
                        final_result TEXT CHECK (final_result IN ('pass', 'fail')),
                        error_message TEXT,
                        FOREIGN KEY (scenario_id) REFERENCES test_scenarios (scenario_id)
                    )
                """)
                
                # Create step_executions table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS step_executions (
                        step_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        execution_id INTEGER NOT NULL,
                        step_number INTEGER NOT NULL,
                        step_type TEXT NOT NULL,
                        expected_intent TEXT,
                        actual_intent TEXT,
                        confidence REAL,
                        audio_transcript TEXT,
                        status TEXT CHECK (status IN ('pending', 'running', 'completed', 'failed')) DEFAULT 'pending',
                        start_time TIMESTAMP,
                        end_time TIMESTAMP,
                        error_message TEXT,
                        FOREIGN KEY (execution_id) REFERENCES test_executions (execution_id)
                    )
                """)
                
                # Create intent_training_data table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS intent_training_data (
                        training_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        text_sample TEXT NOT NULL,
                        intent_label TEXT NOT NULL,
                        confidence_threshold REAL DEFAULT 0.85,
                        source TEXT DEFAULT 'manual',
                        validation_status TEXT CHECK (validation_status IN ('pending', 'validated', 'rejected')) DEFAULT 'pending',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Create indexes for performance
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_scenario_id ON test_executions(scenario_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_execution_id ON step_executions(execution_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_call_id ON test_executions(call_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_intent_label ON intent_training_data(intent_label)")
                
                # Create trigger to update updated_at timestamp
                cursor.execute("""
                    CREATE TRIGGER IF NOT EXISTS update_test_scenarios_timestamp
                    AFTER UPDATE ON test_scenarios
                    BEGIN
                        UPDATE test_scenarios SET updated_at = CURRENT_TIMESTAMP WHERE scenario_id = NEW.scenario_id;
                    END
                """)
                
                conn.commit()
                logger.info(f"Database initialized successfully at {self.db_path}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            return False
    
    def create_scenario(self, scenario: TestScenario) -> Optional[int]:
        """Create a new test scenario and return its ID."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    INSERT INTO test_scenarios (name, description, target_phone, steps, timeout_seconds)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    scenario.name,
                    scenario.description,
                    scenario.target_phone,
                    json.dumps(scenario.steps) if scenario.steps else "[]",
                    scenario.timeout_seconds
                ))
                
                scenario_id = cursor.lastrowid
                conn.commit()
                logger.info(f"Created test scenario with ID: {scenario_id}")
                return scenario_id
                
        except Exception as e:
            logger.error(f"Failed to create scenario: {e}")
            return None
    
    def get_scenario(self, scenario_id: int) -> Optional[TestScenario]:
        """Retrieve a test scenario by ID."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM test_scenarios WHERE scenario_id = ?", (scenario_id,))
                row = cursor.fetchone()
                
                if row:
                    return TestScenario(
                        scenario_id=row['scenario_id'],
                        name=row['name'],
                        description=row['description'],
                        target_phone=row['target_phone'],
                        steps=json.loads(row['steps']) if row['steps'] else [],
                        timeout_seconds=row['timeout_seconds'],
                        created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None,
                        updated_at=datetime.fromisoformat(row['updated_at']) if row['updated_at'] else None
                    )
                return None
                
        except Exception as e:
            logger.error(f"Failed to get scenario {scenario_id}: {e}")
            return None
    
    def list_scenarios(self) -> List[TestScenario]:
        """List all test scenarios."""
        try:
            scenarios = []
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM test_scenarios ORDER BY created_at DESC")
                rows = cursor.fetchall()
                
                for row in rows:
                    scenarios.append(TestScenario(
                        scenario_id=row['scenario_id'],
                        name=row['name'],
                        description=row['description'],
                        target_phone=row['target_phone'],
                        steps=json.loads(row['steps']) if row['steps'] else [],
                        timeout_seconds=row['timeout_seconds'],
                        created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None,
                        updated_at=datetime.fromisoformat(row['updated_at']) if row['updated_at'] else None
                    ))
                
                return scenarios
                
        except Exception as e:
            logger.error(f"Failed to list scenarios: {e}")
            return []
    
    def create_execution(self, execution: TestExecution) -> Optional[int]:
        """Create a new test execution and return its ID."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    INSERT INTO test_executions (scenario_id, status, start_time, call_id)
                    VALUES (?, ?, ?, ?)
                """, (
                    execution.scenario_id,
                    execution.status,
                    execution.start_time or datetime.now(),
                    execution.call_id
                ))
                
                execution_id = cursor.lastrowid
                conn.commit()
                logger.info(f"Created test execution with ID: {execution_id}")
                return execution_id
                
        except Exception as e:
            logger.error(f"Failed to create execution: {e}")
            return None
    
    def update_execution_status(self, execution_id: int, status: str, 
                              final_result: Optional[str] = None, 
                              error_message: Optional[str] = None) -> bool:
        """Update execution status and optionally set final result."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                if status in ['completed', 'failed', 'timeout']:
                    cursor.execute("""
                        UPDATE test_executions 
                        SET status = ?, end_time = ?, final_result = ?, error_message = ?
                        WHERE execution_id = ?
                    """, (status, datetime.now(), final_result, error_message, execution_id))
                else:
                    cursor.execute("""
                        UPDATE test_executions 
                        SET status = ?, error_message = ?
                        WHERE execution_id = ?
                    """, (status, error_message, execution_id))
                
                conn.commit()
                return True
                
        except Exception as e:
            logger.error(f"Failed to update execution {execution_id}: {e}")
            return False
    
    def add_training_data(self, training_data: IntentTrainingData) -> Optional[int]:
        """Add intent training data and return its ID."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    INSERT INTO intent_training_data 
                    (text_sample, intent_label, confidence_threshold, source, validation_status)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    training_data.text_sample,
                    training_data.intent_label,
                    training_data.confidence_threshold,
                    training_data.source,
                    training_data.validation_status
                ))
                
                training_id = cursor.lastrowid
                conn.commit()
                logger.info(f"Added training data with ID: {training_id}")
                return training_id
                
        except Exception as e:
            logger.error(f"Failed to add training data: {e}")
            return None
    
    def get_training_data_by_intent(self, intent_label: str) -> List[IntentTrainingData]:
        """Get all training data for a specific intent."""
        try:
            training_data = []
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM intent_training_data 
                    WHERE intent_label = ? AND validation_status = 'validated'
                    ORDER BY created_at DESC
                """, (intent_label,))
                rows = cursor.fetchall()
                
                for row in rows:
                    training_data.append(IntentTrainingData(
                        training_id=row['training_id'],
                        text_sample=row['text_sample'],
                        intent_label=row['intent_label'],
                        confidence_threshold=row['confidence_threshold'],
                        source=row['source'],
                        validation_status=row['validation_status'],
                        created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None
                    ))
                
                return training_data
                
        except Exception as e:
            logger.error(f"Failed to get training data for intent {intent_label}: {e}")
            return []

# Singleton database manager instance
_db_manager = None

def get_database_manager() -> DatabaseManager:
    """Get singleton database manager instance."""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager

def initialize_database() -> bool:
    """Initialize the database with required schema."""
    return get_database_manager().initialize_database()