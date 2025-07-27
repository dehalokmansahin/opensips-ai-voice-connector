"""
Health monitoring and check management for AI Voice Connector service
Provides comprehensive health checking capabilities for all service components
"""

import asyncio
import time
from datetime import datetime, timezone
from typing import Dict, Any, Callable, Awaitable, Optional
from dataclasses import dataclass, asdict
from enum import Enum

import structlog

logger = structlog.get_logger(__name__)


class HealthStatus(Enum):
    """Health status enumeration"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class HealthCheckResult:
    """Individual health check result"""
    name: str
    status: HealthStatus
    message: str
    details: Dict[str, Any]
    response_time_ms: Optional[float]
    timestamp: datetime
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        result = asdict(self)
        result["status"] = self.status.value
        result["timestamp"] = self.timestamp.isoformat()
        return result


class HealthManager:
    """Manages health checks for all service components"""
    
    def __init__(self, default_timeout: float = 5.0):
        self.default_timeout = default_timeout
        self.health_checks: Dict[str, Callable[[], Awaitable[Dict[str, Any]]]] = {}
        self.last_results: Dict[str, HealthCheckResult] = {}
        self._check_lock = asyncio.Lock()
    
    def add_check(self, name: str, check_func: Callable[[], Awaitable[Dict[str, Any]]]):
        """Add a health check function"""
        self.health_checks[name] = check_func
        logger.info("Added health check", check_name=name)
    
    def remove_check(self, name: str):
        """Remove a health check"""
        if name in self.health_checks:
            del self.health_checks[name]
            if name in self.last_results:
                del self.last_results[name]
            logger.info("Removed health check", check_name=name)
    
    async def run_single_check(self, name: str) -> HealthCheckResult:
        """Run a single health check with timeout and error handling"""
        if name not in self.health_checks:
            return HealthCheckResult(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message="Health check not found",
                details={"error": f"No health check registered for {name}"},
                response_time_ms=None,
                timestamp=datetime.now(timezone.utc)
            )
        
        start_time = time.time()
        
        try:
            # Run health check with timeout
            check_func = self.health_checks[name]
            result = await asyncio.wait_for(check_func(), timeout=self.default_timeout)
            
            end_time = time.time()
            response_time_ms = (end_time - start_time) * 1000
            
            # Parse result
            status_str = result.get("status", "unknown").lower()
            if status_str == "healthy":
                status = HealthStatus.HEALTHY
            elif status_str == "degraded":
                status = HealthStatus.DEGRADED
            else:
                status = HealthStatus.UNHEALTHY
            
            return HealthCheckResult(
                name=name,
                status=status,
                message=result.get("message", "Health check completed"),
                details=result.get("details", {}),
                response_time_ms=response_time_ms,
                timestamp=datetime.now(timezone.utc)
            )
            
        except asyncio.TimeoutError:
            end_time = time.time()
            response_time_ms = (end_time - start_time) * 1000
            
            logger.warning("Health check timed out", 
                         check_name=name, 
                         timeout=self.default_timeout)
            
            return HealthCheckResult(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message="Health check timed out",
                details={"timeout_seconds": self.default_timeout},
                response_time_ms=response_time_ms,
                timestamp=datetime.now(timezone.utc)
            )
            
        except Exception as e:
            end_time = time.time()
            response_time_ms = (end_time - start_time) * 1000
            
            logger.error("Health check failed", 
                        check_name=name, 
                        error=str(e))
            
            return HealthCheckResult(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message=f"Health check failed: {str(e)}",
                details={"error": str(e), "error_type": type(e).__name__},
                response_time_ms=response_time_ms,
                timestamp=datetime.now(timezone.utc)
            )
    
    async def check_all(self, parallel: bool = True) -> Dict[str, Any]:
        """Run all health checks and return aggregated results"""
        async with self._check_lock:
            if not self.health_checks:
                return {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "overall_status": HealthStatus.HEALTHY.value,
                    "checks": {},
                    "summary": {
                        "total": 0,
                        "healthy": 0,
                        "degraded": 0,
                        "unhealthy": 0
                    }
                }
            
            if parallel:
                # Run all checks concurrently
                tasks = [
                    self.run_single_check(name) 
                    for name in self.health_checks.keys()
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)
            else:
                # Run checks sequentially
                results = []
                for name in self.health_checks.keys():
                    result = await self.run_single_check(name)
                    results.append(result)
            
            # Process results
            check_results = {}
            summary = {"total": 0, "healthy": 0, "degraded": 0, "unhealthy": 0}
            
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    # Handle exception in gather
                    name = list(self.health_checks.keys())[i]
                    result = HealthCheckResult(
                        name=name,
                        status=HealthStatus.UNHEALTHY,
                        message=f"Health check exception: {str(result)}",
                        details={"error": str(result)},
                        response_time_ms=None,
                        timestamp=datetime.now(timezone.utc)
                    )
                
                # Store result
                self.last_results[result.name] = result
                check_results[result.name] = result.to_dict()
                
                # Update summary
                summary["total"] += 1
                if result.status == HealthStatus.HEALTHY:
                    summary["healthy"] += 1
                elif result.status == HealthStatus.DEGRADED:
                    summary["degraded"] += 1
                else:
                    summary["unhealthy"] += 1
            
            # Determine overall status
            if summary["unhealthy"] > 0:
                overall_status = HealthStatus.UNHEALTHY
            elif summary["degraded"] > 0:
                overall_status = HealthStatus.DEGRADED
            else:
                overall_status = HealthStatus.HEALTHY
            
            return {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "overall_status": overall_status.value,
                "checks": check_results,
                "summary": summary
            }
    
    async def get_last_results(self) -> Dict[str, Any]:
        """Get the last health check results without running new checks"""
        if not self.last_results:
            return await self.check_all()
        
        check_results = {
            name: result.to_dict() 
            for name, result in self.last_results.items()
        }
        
        # Calculate summary from last results
        summary = {"total": 0, "healthy": 0, "degraded": 0, "unhealthy": 0}
        for result in self.last_results.values():
            summary["total"] += 1
            if result.status == HealthStatus.HEALTHY:
                summary["healthy"] += 1
            elif result.status == HealthStatus.DEGRADED:
                summary["degraded"] += 1
            else:
                summary["unhealthy"] += 1
        
        # Determine overall status
        if summary["unhealthy"] > 0:
            overall_status = HealthStatus.UNHEALTHY
        elif summary["degraded"] > 0:
            overall_status = HealthStatus.DEGRADED
        else:
            overall_status = HealthStatus.HEALTHY
        
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "overall_status": overall_status.value,
            "checks": check_results,
            "summary": summary
        }
    
    def is_healthy(self) -> bool:
        """Quick check if the service is considered healthy overall"""
        if not self.last_results:
            return False
        
        return all(
            result.status == HealthStatus.HEALTHY 
            for result in self.last_results.values()
        )
    
    def get_unhealthy_services(self) -> Dict[str, HealthCheckResult]:
        """Get list of unhealthy services"""
        return {
            name: result 
            for name, result in self.last_results.items()
            if result.status == HealthStatus.UNHEALTHY
        }