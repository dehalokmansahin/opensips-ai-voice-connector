"""
Intent Recognition Service - Main Entry Point
Foundation service for Turkish BERT intent classification
"""

import asyncio
import logging
import os
import sys

# Setup basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def main():
    """Main entry point for Intent Recognition Service"""
    try:
        logger.info("Starting Intent Recognition Service...")
        logger.info("Environment: %s", os.environ.get('ENVIRONMENT', 'development'))
        logger.info("Port: 50054")
        logger.info("Model: Foundation Mock (Turkish BERT in Epic 2.1)")
        
        # Import and run the server
        from intent_grpc_server import serve
        asyncio.run(serve())
        
    except KeyboardInterrupt:
        logger.info("Service interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error("Service failed to start: %s", str(e))
        sys.exit(1)

if __name__ == '__main__':
    main()