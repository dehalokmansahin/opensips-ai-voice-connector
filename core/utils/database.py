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
class DatabaseTestScenario:
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
class DatabaseTestExecution:
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
class DatabaseStepExecution:
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
class DatabaseIntentTrainingData:
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
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_execution_status ON test_executions(status)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_step_status ON step_executions(status)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_validation_status ON intent_training_data(validation_status)")
                
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
    
    def create_scenario(self, scenario: DatabaseTestScenario) -> Optional[int]:
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
    
    def get_scenario(self, scenario_id: int) -> Optional[DatabaseTestScenario]:
        """Retrieve a test scenario by ID."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM test_scenarios WHERE scenario_id = ?", (scenario_id,))
                row = cursor.fetchone()
                
                if row:
                    return DatabaseTestScenario(
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
    
    def list_scenarios(self) -> List[DatabaseTestScenario]:
        """List all test scenarios."""
        try:
            scenarios = []
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM test_scenarios ORDER BY created_at DESC")
                rows = cursor.fetchall()
                
                for row in rows:
                    scenarios.append(DatabaseTestScenario(
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
    
    def create_execution(self, execution: DatabaseTestExecution) -> Optional[int]:
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
    
    def add_training_data(self, training_data: DatabaseIntentTrainingData) -> Optional[int]:
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
    
    def get_training_data_by_intent(self, intent_label: str) -> List[DatabaseIntentTrainingData]:
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
                    training_data.append(DatabaseIntentTrainingData(
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
    
    def validate_database_integrity(self) -> Dict[str, Any]:
        """Validate database integrity and return status report."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Check table existence
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [row[0] for row in cursor.fetchall()]
                
                required_tables = ['test_scenarios', 'test_executions', 'step_executions', 'intent_training_data']
                missing_tables = [table for table in required_tables if table not in tables]
                
                # Check record counts
                record_counts = {}
                for table in required_tables:
                    if table in tables:
                        cursor.execute(f"SELECT COUNT(*) FROM {table}")
                        record_counts[table] = cursor.fetchone()[0]
                
                # Check foreign key integrity
                cursor.execute("""
                    SELECT COUNT(*) FROM test_executions 
                    WHERE scenario_id NOT IN (SELECT scenario_id FROM test_scenarios)
                """)
                orphaned_executions = cursor.fetchone()[0]
                
                cursor.execute("""
                    SELECT COUNT(*) FROM step_executions 
                    WHERE execution_id NOT IN (SELECT execution_id FROM test_executions)
                """)
                orphaned_steps = cursor.fetchone()[0]
                
                return {
                    "database_exists": True,
                    "missing_tables": missing_tables,
                    "record_counts": record_counts,
                    "integrity_issues": {
                        "orphaned_executions": orphaned_executions,
                        "orphaned_steps": orphaned_steps
                    },
                    "healthy": len(missing_tables) == 0 and orphaned_executions == 0 and orphaned_steps == 0
                }
                
        except Exception as e:
            logger.error(f"Database integrity validation failed: {e}")
            return {
                "database_exists": False,
                "error": str(e),
                "healthy": False
            }
    
    def cleanup_orphaned_records(self) -> bool:
        """Clean up orphaned records to maintain referential integrity."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Remove orphaned step executions
                cursor.execute("""
                    DELETE FROM step_executions 
                    WHERE execution_id NOT IN (SELECT execution_id FROM test_executions)
                """)
                orphaned_steps_removed = cursor.rowcount
                
                # Remove orphaned test executions
                cursor.execute("""
                    DELETE FROM test_executions 
                    WHERE scenario_id NOT IN (SELECT scenario_id FROM test_scenarios)
                """)
                orphaned_executions_removed = cursor.rowcount
                
                conn.commit()
                
                if orphaned_steps_removed > 0 or orphaned_executions_removed > 0:
                    logger.info(f"Cleaned up {orphaned_steps_removed} orphaned steps and {orphaned_executions_removed} orphaned executions")
                
                return True
                
        except Exception as e:
            logger.error(f"Failed to cleanup orphaned records: {e}")
            return False

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