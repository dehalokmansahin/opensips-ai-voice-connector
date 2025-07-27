#!/usr/bin/env python3
"""
Database migration utility for IVR test automation system.
Handles database schema updates and data migration.
"""

import sys
import logging
import sqlite3
from pathlib import Path
from typing import List, Tuple

# Add core module to path
core_path = Path(__file__).parent.parent / "core"
sys.path.insert(0, str(core_path))

from utils.database import get_database_manager

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DatabaseMigration:
    """Handles database schema migrations."""
    
    def __init__(self):
        self.db_manager = get_database_manager()
        
    def get_current_version(self) -> int:
        """Get current database schema version."""
        try:
            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                
                # Create schema_version table if it doesn't exist
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS schema_version (
                        version INTEGER PRIMARY KEY,
                        applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        description TEXT
                    )
                """)
                
                # Get current version
                cursor.execute("SELECT MAX(version) FROM schema_version")
                result = cursor.fetchone()
                
                return result[0] if result[0] is not None else 0
                
        except Exception as e:
            logger.error(f"Failed to get current version: {e}")
            return 0
    
    def apply_migration(self, version: int, description: str, sql_statements: List[str]) -> bool:
        """Apply a migration to the database."""
        try:
            with self.db_manager.get_connection() as conn:
                cursor = conn.cursor()
                
                # Execute migration statements
                for statement in sql_statements:
                    logger.info(f"Executing: {statement[:100]}...")
                    cursor.execute(statement)
                
                # Record migration
                cursor.execute("""
                    INSERT INTO schema_version (version, description)
                    VALUES (?, ?)
                """, (version, description))
                
                conn.commit()
                logger.info(f"Applied migration version {version}: {description}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to apply migration {version}: {e}")
            return False
    
    def run_migrations(self) -> bool:
        """Run all pending migrations."""
        current_version = self.get_current_version()
        logger.info(f"Current database version: {current_version}")
        
        # Define migrations
        migrations = [
            # Version 1: Initial schema (handled by init_database.py)
        ]
        
        # Apply pending migrations
        success = True
        for version, description, statements in migrations:
            if version > current_version:
                if not self.apply_migration(version, description, statements):
                    success = False
                    break
        
        if success:
            final_version = self.get_current_version()
            logger.info(f"Database migrations completed. Final version: {final_version}")
        
        return success
    
    def rollback_migration(self, target_version: int) -> bool:
        """Rollback to a specific version (not implemented for SQLite)."""
        logger.warning("Migration rollback not implemented for SQLite")
        logger.warning("To rollback, restore from backup or recreate database")
        return False
    
    def backup_database(self, backup_path: str = None) -> bool:
        """Create a backup of the database."""
        try:
            if backup_path is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = f"{self.db_manager.db_path}.backup_{timestamp}"
            
            # Simple file copy for SQLite
            import shutil
            shutil.copy2(self.db_manager.db_path, backup_path)
            
            logger.info(f"Database backed up to: {backup_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to backup database: {e}")
            return False

def main():
    """Main migration function."""
    logger.info("Starting database migration...")
    
    migration = DatabaseMigration()
    
    # Create backup before migration
    if not migration.backup_database():
        logger.warning("Failed to create backup, continuing anyway...")
    
    # Run migrations
    if migration.run_migrations():
        logger.info("Database migration completed successfully")
        return True
    else:
        logger.error("Database migration failed")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)