"""
IVR Test Result Processing
Handles execution results, reporting, and persistence
"""

import json
import sqlite3
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)

class StepResultStatus(Enum):
    """Step execution result status"""
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    ERROR = "error"
    SKIPPED = "skipped"

class ExecutionResultStatus(Enum):
    """Overall execution result status"""
    PASS = "pass"
    FAIL = "fail"
    TIMEOUT = "timeout"
    ERROR = "error"
    CANCELLED = "cancelled"

@dataclass
class StepResult:
    """Results from executing a single test step"""
    step_number: int
    step_type: str
    status: StepResultStatus
    execution_time_ms: int
    
    # Success/failure details
    error_message: Optional[str] = None
    
    # TTS step results
    tts_text: Optional[str] = None
    tts_duration_ms: Optional[int] = None
    
    # ASR step results
    transcribed_text: Optional[str] = None
    detected_intent: Optional[str] = None
    confidence: Optional[float] = None
    
    # DTMF step results
    dtmf_sequence: Optional[str] = None
    dtmf_sent_successfully: Optional[bool] = None
    
    # Intent validation results
    expected_intent: Optional[str] = None
    actual_intent: Optional[str] = None
    intent_match: Optional[bool] = None
    validation_confidence: Optional[float] = None
    
    # Additional metadata
    timestamp: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        """Set timestamp if not provided"""
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()
    
    def is_successful(self) -> bool:
        """Check if step was successful"""
        return self.status == StepResultStatus.SUCCESS
    
    def get_summary(self) -> str:
        """Get a summary string for the step result"""
        base = f"Step {self.step_number} ({self.step_type}): {self.status.value}"
        
        if self.error_message:
            base += f" - {self.error_message}"
        elif self.step_type == "asr_listen" and self.transcribed_text:
            base += f" - '{self.transcribed_text}'"
        elif self.step_type == "intent_validate" and self.intent_match is not None:
            match_status = "MATCH" if self.intent_match else "NO MATCH"
            base += f" - {match_status} ({self.expected_intent} vs {self.actual_intent})"
        
        return base

@dataclass
class PerformanceMetrics:
    """Performance metrics for test execution"""
    total_duration_ms: int
    successful_steps: int
    failed_steps: int
    timeout_steps: int
    error_steps: int
    skipped_steps: int
    
    # Audio processing metrics
    total_tts_duration_ms: int = 0
    total_asr_duration_ms: int = 0
    
    # Call metrics
    call_setup_time_ms: Optional[int] = None
    call_duration_ms: Optional[int] = None
    
    def get_success_rate(self) -> float:
        """Calculate success rate as percentage"""
        total_executed = self.successful_steps + self.failed_steps + self.timeout_steps + self.error_steps
        if total_executed == 0:
            return 0.0
        return (self.successful_steps / total_executed) * 100

@dataclass
class ExecutionResult:
    """Complete execution result for a test scenario"""
    execution_id: str
    scenario_id: str
    scenario_name: str
    status: ExecutionResultStatus
    start_time: str
    end_time: str
    step_results: List[StepResult]
    performance_metrics: PerformanceMetrics
    
    # Call details
    call_id: Optional[str] = None
    target_phone: Optional[str] = None
    
    # Error details
    error_message: Optional[str] = None
    error_step: Optional[int] = None
    
    # Additional metadata
    executor_version: Optional[str] = None
    environment: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def get_duration_seconds(self) -> float:
        """Get total execution duration in seconds"""
        return self.performance_metrics.total_duration_ms / 1000.0
    
    def is_successful(self) -> bool:
        """Check if execution was successful"""
        return self.status == ExecutionResultStatus.PASS
    
    def get_failed_steps(self) -> List[StepResult]:
        """Get list of failed steps"""
        return [step for step in self.step_results if not step.is_successful()]
    
    def get_summary(self) -> str:
        """Get execution summary"""
        duration = self.get_duration_seconds()
        success_rate = self.performance_metrics.get_success_rate()
        
        return (f"Execution {self.execution_id}: {self.status.value} "
                f"({success_rate:.1f}% success, {duration:.1f}s)")

class ResultProcessor:
    """Processes and stores test execution results"""
    
    def __init__(self, db_path: str = "ivr_testing.db"):
        """
        Initialize result processor
        
        Args:
            db_path: Path to SQLite database
        """
        self.db_path = db_path
        self._ensure_database()
    
    def _ensure_database(self):
        """Create database tables if they don't exist"""
        with sqlite3.connect(self.db_path) as conn:
            # Execution results table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS execution_results (
                    execution_id TEXT PRIMARY KEY,
                    scenario_id TEXT NOT NULL,
                    scenario_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT NOT NULL,
                    call_id TEXT,
                    target_phone TEXT,
                    error_message TEXT,
                    error_step INTEGER,
                    result_data TEXT NOT NULL,  -- JSON blob
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (scenario_id) REFERENCES test_scenarios(scenario_id)
                )
            """)
            
            # Step results table (for easier querying)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS step_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    execution_id TEXT NOT NULL,
                    step_number INTEGER NOT NULL,
                    step_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    execution_time_ms INTEGER NOT NULL,
                    error_message TEXT,
                    result_data TEXT,  -- JSON blob
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (execution_id) REFERENCES execution_results(execution_id)
                )
            """)
            
            # Create indexes
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_execution_scenario
                ON execution_results(scenario_id)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_execution_status
                ON execution_results(status)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_execution_time
                ON execution_results(start_time)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_step_execution
                ON step_results(execution_id)
            """)
    
    def save_execution_result(self, result: ExecutionResult) -> bool:
        """
        Save execution result to database
        
        Args:
            result: Execution result to save
            
        Returns:
            True if saved successfully
        """
        try:
            # Convert to JSON
            result_dict = asdict(result)
            result_json = json.dumps(result_dict, ensure_ascii=False)
            
            with sqlite3.connect(self.db_path) as conn:
                # Save main execution result
                conn.execute("""
                    INSERT OR REPLACE INTO execution_results
                    (execution_id, scenario_id, scenario_name, status, start_time, end_time,
                     call_id, target_phone, error_message, error_step, result_data, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    result.execution_id,
                    result.scenario_id,
                    result.scenario_name,
                    result.status.value,
                    result.start_time,
                    result.end_time,
                    result.call_id,
                    result.target_phone,
                    result.error_message,
                    result.error_step,
                    result_json,
                    datetime.now().isoformat()
                ))
                
                # Save individual step results
                for step_result in result.step_results:
                    step_dict = asdict(step_result)
                    step_json = json.dumps(step_dict, ensure_ascii=False)
                    
                    conn.execute("""
                        INSERT OR REPLACE INTO step_results
                        (execution_id, step_number, step_type, status, execution_time_ms,
                         error_message, result_data, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        result.execution_id,
                        step_result.step_number,
                        step_result.step_type,
                        step_result.status.value,
                        step_result.execution_time_ms,
                        step_result.error_message,
                        step_json,
                        datetime.now().isoformat()
                    ))
            
            logger.info(f"Execution result saved: {result.execution_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save execution result: {e}")
            return False
    
    def load_execution_result(self, execution_id: str) -> Optional[ExecutionResult]:
        """
        Load execution result from database
        
        Args:
            execution_id: ID of execution to load
            
        Returns:
            ExecutionResult or None if not found
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    SELECT result_data FROM execution_results
                    WHERE execution_id = ?
                """, (execution_id,))
                
                row = cursor.fetchone()
                if not row:
                    return None
                
                # Parse JSON data
                result_dict = json.loads(row[0])
                
                # Convert step results
                step_results = []
                for step_dict in result_dict.get('step_results', []):
                    step_dict['status'] = StepResultStatus(step_dict['status'])
                    step_result = StepResult(**step_dict)
                    step_results.append(step_result)
                
                # Convert performance metrics
                metrics_dict = result_dict.get('performance_metrics', {})
                performance_metrics = PerformanceMetrics(**metrics_dict)
                
                # Create execution result
                result_dict['status'] = ExecutionResultStatus(result_dict['status'])
                result_dict['step_results'] = step_results
                result_dict['performance_metrics'] = performance_metrics
                
                execution_result = ExecutionResult(**result_dict)
                return execution_result
                
        except Exception as e:
            logger.error(f"Failed to load execution result {execution_id}: {e}")
            return None
    
    def list_execution_results(self, 
                             scenario_id: Optional[str] = None,
                             status: Optional[ExecutionResultStatus] = None,
                             limit: int = 50) -> List[Dict[str, Any]]:
        """
        List execution results with optional filtering
        
        Args:
            scenario_id: Optional scenario ID to filter by
            status: Optional status to filter by
            limit: Maximum number of results to return
            
        Returns:
            List of execution result summaries
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                query = """
                    SELECT execution_id, scenario_id, scenario_name, status,
                           start_time, end_time, call_id, target_phone
                    FROM execution_results
                    WHERE 1=1
                """
                params = []
                
                if scenario_id:
                    query += " AND scenario_id = ?"
                    params.append(scenario_id)
                
                if status:
                    query += " AND status = ?"
                    params.append(status.value)
                
                query += " ORDER BY start_time DESC LIMIT ?"
                params.append(limit)
                
                cursor = conn.execute(query, params)
                rows = cursor.fetchall()
                
                results = []
                for row in rows:
                    results.append({
                        'execution_id': row[0],
                        'scenario_id': row[1],
                        'scenario_name': row[2],
                        'status': row[3],
                        'start_time': row[4],
                        'end_time': row[5],
                        'call_id': row[6],
                        'target_phone': row[7]
                    })
                
                return results
                
        except Exception as e:
            logger.error(f"Failed to list execution results: {e}")
            return []
    
    def get_execution_statistics(self, scenario_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get execution statistics
        
        Args:
            scenario_id: Optional scenario ID to filter by
            
        Returns:
            Statistics dictionary
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Base query
                where_clause = ""
                params = []
                
                if scenario_id:
                    where_clause = "WHERE scenario_id = ?"
                    params.append(scenario_id)
                
                # Overall counts
                cursor = conn.execute(f"""
                    SELECT status, COUNT(*) as count
                    FROM execution_results
                    {where_clause}
                    GROUP BY status
                """, params)
                
                status_counts = dict(cursor.fetchall())
                
                # Average execution time
                cursor = conn.execute(f"""
                    SELECT AVG(
                        CAST((julianday(end_time) - julianday(start_time)) * 86400000 AS INTEGER)
                    ) as avg_duration_ms
                    FROM execution_results
                    {where_clause}
                """, params)
                
                avg_duration = cursor.fetchone()[0] or 0
                
                # Recent executions (last 24 hours)
                cursor = conn.execute(f"""
                    SELECT COUNT(*) as recent_count
                    FROM execution_results
                    WHERE datetime(start_time) > datetime('now', '-1 day')
                    {' AND ' + where_clause.replace('WHERE ', '') if where_clause else ''}
                """, params)
                
                recent_count = cursor.fetchone()[0]
                
                return {
                    'total_executions': sum(status_counts.values()),
                    'status_counts': status_counts,
                    'average_duration_ms': avg_duration,
                    'recent_executions_24h': recent_count,
                    'success_rate': (
                        (status_counts.get('pass', 0) / sum(status_counts.values()) * 100)
                        if sum(status_counts.values()) > 0 else 0
                    )
                }
                
        except Exception as e:
            logger.error(f"Failed to get execution statistics: {e}")
            return {}
    
    def delete_execution_results(self, execution_ids: List[str]) -> int:
        """
        Delete execution results
        
        Args:
            execution_ids: List of execution IDs to delete
            
        Returns:
            Number of results deleted
        """
        try:
            if not execution_ids:
                return 0
            
            with sqlite3.connect(self.db_path) as conn:
                placeholders = ','.join('?' * len(execution_ids))
                
                # Delete step results first
                cursor = conn.execute(f"""
                    DELETE FROM step_results
                    WHERE execution_id IN ({placeholders})
                """, execution_ids)
                
                # Delete execution results
                cursor = conn.execute(f"""
                    DELETE FROM execution_results
                    WHERE execution_id IN ({placeholders})
                """, execution_ids)
                
                deleted_count = cursor.rowcount
                logger.info(f"Deleted {deleted_count} execution results")
                return deleted_count
                
        except Exception as e:
            logger.error(f"Failed to delete execution results: {e}")
            return 0