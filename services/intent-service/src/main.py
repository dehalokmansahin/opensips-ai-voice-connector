#!/usr/bin/env python3
"""
Turkish Bank Intent Recognition Service - Main Entry Point
Mock REST API service for Turkish banking IVR automation testing
"""

import os
import sys
import logging

# Add paths for imports
sys.path.insert(0, os.path.dirname(__file__))

# Use mock implementation for development/testing
from intent_rest_server import app, run_server

def main():
    """Main entry point for Turkish Bank Intent Recognition Service"""
    print("Starting Turkish Bank Intent Recognition Service (Mock Implementation)")
    
    # Start the mock REST server
    run_server()

if __name__ == '__main__':
    main()