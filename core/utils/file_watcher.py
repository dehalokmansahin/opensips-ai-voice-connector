"""
File Watcher Utility for Development Hot-Reload
Monitors source code changes and triggers application restart
"""

import asyncio
import logging
import os
import sys
import time
from pathlib import Path
from typing import Set, Callable, Optional
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

logger = logging.getLogger(__name__)

class CodeChangeHandler(FileSystemEventHandler):
    """Handler for code file changes"""
    
    def __init__(self, callback: Callable, extensions: Set[str] = None):
        self.callback = callback
        self.extensions = extensions or {'.py'}
        self.last_modified = {}
        self.debounce_seconds = 2  # Prevent rapid-fire restarts
        
    def on_modified(self, event):
        """Handle file modification events"""
        if event.is_directory:
            return
            
        file_path = Path(event.src_path)
        
        # Only watch specified extensions
        if file_path.suffix not in self.extensions:
            return
            
        # Skip __pycache__ and other temp files
        if '__pycache__' in str(file_path) or file_path.name.startswith('.'):
            return
            
        # Debounce rapid changes
        now = time.time()
        if file_path in self.last_modified:
            if now - self.last_modified[file_path] < self.debounce_seconds:
                return
        
        self.last_modified[file_path] = now
        
        logger.info(f"Code change detected: {file_path}")
        if self.callback:
            self.callback(file_path)

class HotReloadWatcher:
    """Hot-reload file watcher for development"""
    
    def __init__(self, watch_paths: list, restart_callback: Callable = None):
        self.watch_paths = [Path(p) for p in watch_paths]
        self.restart_callback = restart_callback
        self.observer = Observer()
        self.handler = CodeChangeHandler(self._on_code_change)
        self.enabled = os.getenv('DEVELOPMENT_MODE', '0') == '1'
        
    def _on_code_change(self, changed_file: Path):
        """Handle code change events"""
        if not self.enabled:
            return
            
        logger.info(f"Hot-reload triggered by: {changed_file}")
        
        if self.restart_callback:
            try:
                self.restart_callback(changed_file)
            except Exception as e:
                logger.error(f"Hot-reload callback failed: {e}")
        else:
            logger.info("Hot-reload: restarting application...")
            self._restart_process()
    
    def _restart_process(self):
        """Restart the current process"""
        # In containerized environment, exit gracefully 
        # Docker will restart the container
        logger.info("Triggering process restart for hot-reload")
        os._exit(0)
    
    def start(self):
        """Start watching for file changes"""
        if not self.enabled:
            logger.info("Hot-reload disabled (not in development mode)")
            return
            
        for watch_path in self.watch_paths:
            if watch_path.exists():
                self.observer.schedule(self.handler, str(watch_path), recursive=True)
                logger.info(f"Hot-reload watching: {watch_path}")
            else:
                logger.warning(f"Hot-reload path not found: {watch_path}")
        
        self.observer.start()
        logger.info("Hot-reload watcher started")
    
    def stop(self):
        """Stop watching for file changes"""
        if self.observer.is_alive():
            self.observer.stop()
            self.observer.join()
            logger.info("Hot-reload watcher stopped")

def setup_hot_reload(app_root: Path, restart_callback: Callable = None) -> Optional[HotReloadWatcher]:
    """Setup hot-reload for development"""
    if os.getenv('DEVELOPMENT_MODE', '0') != '1':
        return None
        
    # Define paths to watch
    watch_paths = [
        app_root / "core",
        app_root / "services" / "common",
        app_root / "shared" / "proto_generated"
    ]
    
    # Filter existing paths
    watch_paths = [p for p in watch_paths if p.exists()]
    
    if not watch_paths:
        logger.warning("No valid paths found for hot-reload watching")
        return None
    
    try:
        watcher = HotReloadWatcher(watch_paths, restart_callback)
        watcher.start()
        return watcher
    except Exception as e:
        logger.error(f"Failed to setup hot-reload: {e}")
        return None

def enable_hot_reload_for_service(service_name: str, service_root: Path) -> Optional[HotReloadWatcher]:
    """Enable hot-reload for a specific service"""
    if os.getenv('DEVELOPMENT_MODE', '0') != '1':
        return None
        
    watch_paths = [
        service_root / "src",
        service_root.parent / "common",
        service_root.parent.parent / "shared" / "proto_generated"
    ]
    
    # Filter existing paths
    watch_paths = [p for p in watch_paths if p.exists()]
    
    if not watch_paths:
        logger.warning(f"No valid paths found for {service_name} hot-reload")
        return None
    
    try:
        watcher = HotReloadWatcher(watch_paths)
        watcher.start()
        logger.info(f"Hot-reload enabled for {service_name}")
        return watcher
    except Exception as e:
        logger.error(f"Failed to setup hot-reload for {service_name}: {e}")
        return None