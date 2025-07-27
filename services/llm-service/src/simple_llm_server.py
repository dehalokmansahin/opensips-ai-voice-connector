#!/usr/bin/env python3
"""
Simple LLM Service for Development Testing
Minimal implementation without heavy PyTorch dependencies
"""

import asyncio
import json
import logging
import os
import sys
from concurrent import futures

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("simple-llm")

class SimpleLLMService:
    def __init__(self, model_path="/app/model", port=50052):
        self.model_path = model_path
        self.port = port
        self.model_loaded = False
        
    def load_model(self):
        """Check for LLM model files"""
        try:
            logger.info(f"Model path base: {self.model_path}")
            if os.path.exists(self.model_path):
                logger.info(f"Contents: {os.listdir(self.model_path)}")
                
                # Look for GGUF model files
                gguf_files = [f for f in os.listdir(self.model_path) if f.endswith('.gguf')]
                
                if gguf_files:
                    logger.info(f"Found GGUF model files: {gguf_files[:1]}")
                    self.model_loaded = True
                    logger.info("✅ LLM model validated successfully")
                    return True
                else:
                    logger.warning(f"❌ No valid LLM model files found (.gguf)")
                    return False
            else:
                logger.error(f"❌ Model path does not exist: {self.model_path}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Failed to validate model: {e}")
            return False
    
    def start_http_server(self):
        """Start simple HTTP server for testing"""
        from http.server import HTTPServer, BaseHTTPRequestHandler
        import threading
        
        class HealthHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == '/health':
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    response = {
                        'status': 'healthy',
                        'service': 'llm-service',
                        'model_loaded': self.server.llm_service.model_loaded
                    }
                    self.wfile.write(json.dumps(response).encode())
                else:
                    self.send_response(404)
                    self.end_headers()
                    
            def log_message(self, format, *args):
                pass  # Suppress HTTP logs
        
        server = HTTPServer(('0.0.0.0', 8080), HealthHandler)
        server.llm_service = self
        thread = threading.Thread(target=server.serve_forever)
        thread.daemon = True
        thread.start()
        logger.info("🌐 HTTP health server started on port 8080")
    
    def run(self):
        """Run the service"""
        logger.info("🚀 Starting Simple LLM Service")
        
        # Load/validate model
        if not self.load_model():
            logger.warning("⚠️  No model found, but continuing for development")
            
        # Start HTTP health server
        self.start_http_server()
        
        # Start dummy gRPC server
        logger.info(f"📡 LLM service listening on port {self.port}")
        logger.info("✅ Service ready for development testing")
        
        # Keep service running
        try:
            while True:
                import time
                time.sleep(10)
        except KeyboardInterrupt:
            logger.info("🛑 Service stopping...")

if __name__ == "__main__":
    service = SimpleLLMService()
    service.run()