#!/usr/bin/env python3
"""
OpenSIPS Health Check Script
Verifies OpenSIPS service availability and basic functionality
"""

import asyncio
import socket
import json
import logging
import sys
from typing import Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class HealthCheckResult:
    """Health check result container"""
    service: str
    status: str  # 'healthy', 'unhealthy', 'degraded'
    response_time_ms: Optional[int]
    details: Dict[str, Any]
    timestamp: datetime


class OpenSIPSHealthChecker:
    """OpenSIPS health checker implementation"""
    
    def __init__(self, host: str = "localhost", 
                 mi_port: int = 8087, 
                 sip_port: int = 5060,
                 timeout: int = 5):
        self.host = host
        self.mi_port = mi_port
        self.sip_port = sip_port
        self.timeout = timeout
        self.logger = self._setup_logging()
    
    def _setup_logging(self) -> logging.Logger:
        """Setup logging configuration"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        return logging.getLogger(__name__)
    
    async def check_sip_port(self) -> HealthCheckResult:
        """Check if SIP port is listening"""
        start_time = datetime.now()
        
        try:
            # Create socket and connect to SIP port
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(self.timeout)
            
            # Try to bind/connect to SIP port
            result = sock.connect_ex((self.host, self.sip_port))
            sock.close()
            
            end_time = datetime.now()
            response_time = int((end_time - start_time).total_seconds() * 1000)
            
            if result == 0:
                return HealthCheckResult(
                    service="opensips-sip",
                    status="healthy",
                    response_time_ms=response_time,
                    details={"port": self.sip_port, "protocol": "UDP"},
                    timestamp=end_time
                )
            else:
                return HealthCheckResult(
                    service="opensips-sip",
                    status="unhealthy",
                    response_time_ms=None,
                    details={"error": f"Connection failed with code {result}"},
                    timestamp=end_time
                )
                
        except Exception as e:
            end_time = datetime.now()
            self.logger.error(f"SIP port check failed: {str(e)}")
            return HealthCheckResult(
                service="opensips-sip",
                status="unhealthy",
                response_time_ms=None,
                details={"error": str(e)},
                timestamp=end_time
            )
    
    async def check_mi_interface(self) -> HealthCheckResult:
        """Check Management Interface availability"""
        start_time = datetime.now()
        
        try:
            # Create UDP socket for MI datagram interface
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(self.timeout)
            
            # Send ps command to get process status
            mi_command = "ps\n"
            sock.sendto(mi_command.encode(), (self.host, self.mi_port))
            
            # Receive response
            response, _ = sock.recvfrom(4096)
            sock.close()
            
            end_time = datetime.now()
            response_time = int((end_time - start_time).total_seconds() * 1000)
            
            # Parse response
            response_text = response.decode().strip()
            
            if "Process" in response_text or "opensips" in response_text.lower():
                # Extract process information
                processes = self._parse_ps_output(response_text)
                
                return HealthCheckResult(
                    service="opensips-mi",
                    status="healthy",
                    response_time_ms=response_time,
                    details={
                        "processes": processes,
                        "command": "ps",
                        "response_size": len(response_text)
                    },
                    timestamp=end_time
                )
            else:
                return HealthCheckResult(
                    service="opensips-mi",
                    status="degraded",
                    response_time_ms=response_time,
                    details={"warning": "Unexpected response format"},
                    timestamp=end_time
                )
                
        except socket.timeout:
            end_time = datetime.now()
            return HealthCheckResult(
                service="opensips-mi",
                status="unhealthy",
                response_time_ms=None,
                details={"error": "MI interface timeout"},
                timestamp=end_time
            )
        except Exception as e:
            end_time = datetime.now()
            self.logger.error(f"MI interface check failed: {str(e)}")
            return HealthCheckResult(
                service="opensips-mi",
                status="unhealthy",
                response_time_ms=None,
                details={"error": str(e)},
                timestamp=end_time
            )
    
    def _parse_ps_output(self, output: str) -> Dict[str, Any]:
        """Parse OpenSIPS ps command output"""
        try:
            lines = output.strip().split('\n')
            processes = []
            
            for line in lines:
                if "Process" in line and ":" in line:
                    # Parse process line format: "Process:: id=X pid=Y"
                    parts = line.split()
                    process_info = {}
                    
                    for part in parts:
                        if "=" in part:
                            key, value = part.split("=", 1)
                            process_info[key] = value
                    
                    if process_info:
                        processes.append(process_info)
            
            return {
                "count": len(processes),
                "details": processes[:5]  # Limit details to first 5 processes
            }
            
        except Exception as e:
            self.logger.warning(f"Failed to parse ps output: {str(e)}")
            return {"count": 0, "parse_error": str(e)}
    
    async def check_dialog_status(self) -> HealthCheckResult:
        """Check active dialogs/calls"""
        start_time = datetime.now()
        
        try:
            # Create UDP socket for MI datagram interface
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(self.timeout)
            
            # Send dlg_list command to get dialog status
            mi_command = "dlg_list\n"
            sock.sendto(mi_command.encode(), (self.host, self.mi_port))
            
            # Receive response
            response, _ = sock.recvfrom(8192)
            sock.close()
            
            end_time = datetime.now()
            response_time = int((end_time - start_time).total_seconds() * 1000)
            
            response_text = response.decode().strip()
            
            # Parse dialog count
            dialog_count = self._parse_dialog_count(response_text)
            
            return HealthCheckResult(
                service="opensips-dialogs",
                status="healthy",
                response_time_ms=response_time,
                details={
                    "active_dialogs": dialog_count,
                    "command": "dlg_list"
                },
                timestamp=end_time
            )
            
        except Exception as e:
            end_time = datetime.now()
            self.logger.error(f"Dialog status check failed: {str(e)}")
            return HealthCheckResult(
                service="opensips-dialogs",
                status="degraded",
                response_time_ms=None,
                details={"error": str(e)},
                timestamp=end_time
            )
    
    def _parse_dialog_count(self, output: str) -> int:
        """Parse dialog count from dlg_list output"""
        try:
            # Look for dialog entries or count indicators
            lines = output.strip().split('\n')
            dialog_count = 0
            
            for line in lines:
                if "dialog::" in line.lower() or "call-id" in line.lower():
                    dialog_count += 1
            
            return dialog_count
            
        except Exception:
            return 0
    
    async def run_all_checks(self) -> Dict[str, HealthCheckResult]:
        """Run all health checks concurrently"""
        self.logger.info("Starting OpenSIPS health checks...")
        
        # Run all checks concurrently
        tasks = [
            self.check_sip_port(),
            self.check_mi_interface(),
            self.check_dialog_status()
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        health_results = {}
        for result in results:
            if isinstance(result, HealthCheckResult):
                health_results[result.service] = result
            elif isinstance(result, Exception):
                self.logger.error(f"Health check failed with exception: {str(result)}")
        
        return health_results
    
    def get_overall_status(self, results: Dict[str, HealthCheckResult]) -> str:
        """Determine overall system health"""
        if not results:
            return "unhealthy"
        
        statuses = [result.status for result in results.values()]
        
        if all(status == "healthy" for status in statuses):
            return "healthy"
        elif any(status == "unhealthy" for status in statuses):
            return "unhealthy"
        else:
            return "degraded"


async def main():
    """Main health check execution"""
    checker = OpenSIPSHealthChecker()
    
    try:
        # Run health checks
        results = await checker.run_all_checks()
        
        # Determine overall status
        overall_status = checker.get_overall_status(results)
        
        # Prepare output
        output = {
            "timestamp": datetime.now().isoformat(),
            "overall_status": overall_status,
            "services": {}
        }
        
        for service, result in results.items():
            output["services"][service] = {
                "status": result.status,
                "response_time_ms": result.response_time_ms,
                "details": result.details,
                "timestamp": result.timestamp.isoformat()
            }
        
        # Output JSON for programmatic use
        print(json.dumps(output, indent=2))
        
        # Exit with appropriate code
        if overall_status == "healthy":
            sys.exit(0)
        elif overall_status == "degraded":
            sys.exit(1)
        else:
            sys.exit(2)
            
    except Exception as e:
        error_output = {
            "timestamp": datetime.now().isoformat(),
            "overall_status": "unhealthy",
            "error": str(e)
        }
        print(json.dumps(error_output, indent=2))
        sys.exit(2)


if __name__ == "__main__":
    asyncio.run(main())