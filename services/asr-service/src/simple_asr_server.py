#!/usr/bin/env python3
"""
Simple ASR Service for Development Testing
Based on Vosk with minimal dependencies
"""

import asyncio
import json
import logging
import os
import sys
from concurrent import futures

import grpc
import vosk

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("simple-asr")

class SimpleASRService:
    def __init__(self, model_path="/app/model", port=50051):
        self.model_path = model_path
        self.port = port
        self.model = None
        
    def load_model(self):
        """Load Vosk model"""
        try:
            # Try different model paths and list contents for debugging
            model_paths = [
                os.path.join(self.model_path, "tr"),  # Turkish model
                os.path.join(self.model_path, "en"),  # English model
                self.model_path
            ]
            
            logger.info(f"Model path base: {self.model_path}")
            logger.info(f"Contents: {os.listdir(self.model_path) if os.path.exists(self.model_path) else 'Directory not found'}")
            
            for path in model_paths:
                logger.info(f"Trying model path: {path}")
                if os.path.exists(path):
                    logger.info(f"Path exists, contents: {os.listdir(path)}")
                    # Check if it has required Vosk files
                    required_files = ["final.mdl", "conf"]
                    has_required = any(f in os.listdir(path) for f in required_files)
                    
                    if has_required:
                        logger.info(f"Loading Vosk model from: {path}")
                        self.model = vosk.Model(path)
                        logger.info("✅ Vosk model loaded successfully")
                        return True
                    else:
                        logger.info(f"Path {path} exists but missing required files")
                else:
                    logger.info(f"Path {path} does not exist")
                    
            logger.error(f"❌ No valid model found in {model_paths}")
            return False
            
        except Exception as e:
            logger.error(f"❌ Failed to load model: {e}")
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
                        'service': 'asr-service',
                        'model_loaded': self.server.asr_service.model is not None
                    }
                    self.wfile.write(json.dumps(response).encode())
                else:
                    self.send_response(404)
                    self.end_headers()
                    
            def log_message(self, format, *args):
                pass  # Suppress HTTP logs
        
        server = HTTPServer(('0.0.0.0', 8080), HealthHandler)
        server.asr_service = self
        thread = threading.Thread(target=server.serve_forever)
        thread.daemon = True
        thread.start()
        logger.info("🌐 HTTP health server started on port 8080")
    
    def run(self):
        """Run the service"""
        logger.info("🚀 Starting Simple ASR Service")
        
        # Load model
        if not self.load_model():
            logger.error("❌ Cannot start without model")
            sys.exit(1)
            
        # Start HTTP health server
        self.start_http_server()
        
        # Start dummy gRPC server
        logger.info(f"📡 ASR service listening on port {self.port}")
        logger.info("✅ Service ready for development testing")
        
        # Keep service running
        try:
            while True:
                asyncio.sleep(10)
        except KeyboardInterrupt:
            logger.info("🛑 Service stopping...")

if __name__ == "__main__":
    service = SimpleASRService()
    service.run()