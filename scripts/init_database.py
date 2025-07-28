#!/usr/bin/env python3
"""
Database initialization script for IVR test automation system.
Creates the SQLite database schema and populates with sample data.
"""

import sys
import logging
from pathlib import Path

# Add core module to path
core_path = Path(__file__).parent.parent / "core"
sys.path.insert(0, str(core_path))

from utils.database import (
    DatabaseManager, DatabaseTestScenario, DatabaseTestExecution, DatabaseIntentTrainingData,
    initialize_database, get_database_manager
)

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def create_sample_scenarios():
    """Create sample test scenarios for development and testing."""
    db = get_database_manager()
    
    # Sample scenario 1: Banking IVR main menu test
    banking_scenario = DatabaseTestScenario(
        name="Banking IVR Main Menu Test",
        description="Test navigation through main banking IVR menu options",
        target_phone="+1234567890",
        steps=[
            {
                "step_number": 1,
                "type": "wait",
                "description": "Wait for IVR greeting",
                "timeout_seconds": 10
            },
            {
                "step_number": 2,
                "type": "prompt",
                "text": "Merhaba, hesap bakiyemi öğrenmek istiyorum",
                "expected_intent": "account_balance_inquiry"
            },
            {
                "step_number": 3,
                "type": "dtmf",
                "sequence": "1",
                "description": "Press 1 for account balance"
            },
            {
                "step_number": 4,
                "type": "validate",
                "expected_intent": "balance_menu",
                "timeout_seconds": 15
            }
        ],
        timeout_seconds=300
    )
    
    scenario_id = db.create_scenario(banking_scenario)
    if scenario_id:
        logger.info(f"Created banking scenario with ID: {scenario_id}")
    
    # Sample scenario 2: Customer service routing test
    customer_service_scenario = DatabaseTestScenario(
        name="Customer Service Routing Test",
        description="Test routing to customer service representative",
        target_phone="+1234567891",
        steps=[
            {
                "step_number": 1,
                "type": "wait",
                "description": "Wait for IVR greeting",
                "timeout_seconds": 10
            },
            {
                "step_number": 2,
                "type": "prompt",
                "text": "Müşteri hizmetleriyle konuşmak istiyorum",
                "expected_intent": "customer_service_request"
            },
            {
                "step_number": 3,
                "type": "dtmf",
                "sequence": "0",
                "description": "Press 0 for customer service"
            },
            {
                "step_number": 4,
                "type": "validate",
                "expected_intent": "agent_transfer",
                "timeout_seconds": 30
            }
        ],
        timeout_seconds=180
    )
    
    scenario_id = db.create_scenario(customer_service_scenario)
    if scenario_id:
        logger.info(f"Created customer service scenario with ID: {scenario_id}")

def create_sample_training_data():
    """Create sample intent training data."""
    db = get_database_manager()
    
    # Account balance inquiry training data
    balance_samples = [
        "hesap bakiyemi öğrenmek istiyorum",
        "bakiyemi kontrol etmek istiyorum", 
        "hesabımda ne kadar param var",
        "bakiye sorgulama",
        "hesap durumu",
        "paramı görmek istiyorum"
    ]
    
    for sample in balance_samples:
        training_data = DatabaseIntentTrainingData(
            text_sample=sample,
            intent_label="account_balance_inquiry",
            confidence_threshold=0.85,
            source="manual",
            validation_status="validated"
        )
        training_id = db.add_training_data(training_data)
        if training_id:
            logger.info(f"Added balance inquiry training data: ID {training_id}")
    
    # Customer service request training data
    service_samples = [
        "müşteri hizmetleriyle konuşmak istiyorum",
        "temsilciyle görüşmek istiyorum",
        "operatöre bağlanmak istiyorum",
        "canlı destek",
        "insan operatör",
        "yardım almak istiyorum"
    ]
    
    for sample in service_samples:
        training_data = DatabaseIntentTrainingData(
            text_sample=sample,
            intent_label="customer_service_request",
            confidence_threshold=0.80,
            source="manual",
            validation_status="validated"
        )
        training_id = db.add_training_data(training_data)
        if training_id:
            logger.info(f"Added customer service training data: ID {training_id}")
    
    # Balance menu confirmation training data
    balance_menu_samples = [
        "hesap bakiyeniz",
        "bakiyeniz şu anda",
        "mevcut bakiye",
        "hesap durumunuz",
        "kullanılabilir bakiye"
    ]
    
    for sample in balance_menu_samples:
        training_data = DatabaseIntentTrainingData(
            text_sample=sample,
            intent_label="balance_menu",
            confidence_threshold=0.90,
            source="manual",
            validation_status="validated"
        )
        training_id = db.add_training_data(training_data)
        if training_id:
            logger.info(f"Added balance menu training data: ID {training_id}")

def main():
    """Main initialization function."""
    logger.info("Starting database initialization...")
    
    # Initialize database schema
    if not initialize_database():
        logger.error("Failed to initialize database schema")
        return False
    
    logger.info("Database schema initialized successfully")
    
    # Create sample data
    try:
        create_sample_scenarios()
        create_sample_training_data()
        logger.info("Sample data created successfully")
        return True
        
    except Exception as e:
        logger.error(f"Failed to create sample data: {e}")
        return False

if __name__ == "__main__":
    success = main()
    if success:
        logger.info("Database initialization completed successfully")
        sys.exit(0)
    else:
        logger.error("Database initialization failed")
        sys.exit(1)