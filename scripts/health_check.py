#!/usr/bin/env python3
"""
IVR Flow Automation System - Comprehensive Health Check
Checks all services and provides detailed system status
"""

import asyncio
import aiohttp
import json
import sys
import subprocess
from datetime import datetime
from typing import Dict, Any, List

class ServiceHealthChecker:
    """Comprehensive service health checker"""
    
    def __init__(self):
        self.services = {
            "intent-service": {
                "url": "http://localhost:5000/health",
                "name": "Turkish Bank Intent Recognition Service",
                "critical": True
            },
            "tts-service": {
                "url": "http://localhost:50053/health",
                "name": "Text-to-Speech Service", 
                "critical": True,
                "protocol": "grpc",
                "note": "gRPC service - health check via docker status"
            },
            "test-controller-service": {
                "url": "http://localhost:50055/health",
                "name": "Test Controller Service",
                "critical": True
            },
            "asr-service": {
                "url": "http://localhost:50051/health",
                "name": "Automatic Speech Recognition Service",
                "critical": False,
                "protocol": "grpc"
            }
        }
        
    async def check_http_service(self, service_name: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Check HTTP service health"""
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(config["url"]) as response:
                    if response.status == 200:
                        try:
                            data = await response.json()
                            return {
                                "status": "healthy",
                                "response_time_ms": 0,  # Could add timing
                                "details": data
                            }
                        except:
                            return {
                                "status": "healthy",
                                "response_time_ms": 0,
                                "details": {"message": "OK"}
                            }
                    else:
                        return {
                            "status": "unhealthy",
                            "error": f"HTTP {response.status}",
                            "details": {}
                        }
                        
        except Exception as e:
            return {
                "status": "unreachable",
                "error": str(e),
                "details": {}
            }
    
    def check_docker_service(self, service_name: str) -> Dict[str, Any]:
        """Check if Docker service is running and healthy"""
        try:
            # Map service names to Docker container names
            container_map = {
                "tts-service": "opensips-tts-service",
                "asr-service": "opensips-asr-service"
            }
            
            container_name = container_map.get(service_name, service_name)
            
            # Check container status
            result = subprocess.run(
                ["docker", "inspect", container_name, "--format", "{{.State.Status}}"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                status = result.stdout.strip()
                if status == "running":
                    return {
                        "status": "healthy",
                        "details": {"docker_status": status}
                    }
                else:
                    return {
                        "status": "unhealthy", 
                        "details": {"docker_status": status}
                    }
            else:
                return {
                    "status": "unreachable",
                    "error": "Container not found",
                    "details": {}
                }
                
        except Exception as e:
            return {
                "status": "unreachable",
                "error": str(e),
                "details": {}
            }

    async def check_all_services(self) -> Dict[str, Any]:
        """Check health of all services"""
        results = {}
        
        for service_name, config in self.services.items():
            if config.get("protocol") == "grpc":
                # For gRPC services, check Docker status
                results[service_name] = self.check_docker_service(service_name)
            else:
                results[service_name] = await self.check_http_service(service_name, config)
                
        return results
    
    async def test_intent_service(self) -> Dict[str, Any]:
        """Test Intent Service functionality"""
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                # Test simple English text to avoid encoding issues
                test_data = {"text": "I want to check my balance"}
                
                async with session.post(
                    "http://localhost:5000/classify",
                    json=test_data
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {
                            "status": "functional",
                            "test_result": data
                        }
                    else:
                        return {
                            "status": "non_functional",
                            "error": f"HTTP {response.status}"
                        }
                        
        except Exception as e:
            return {
                "status": "test_failed",
                "error": str(e)
            }
    
    async def test_test_controller(self) -> Dict[str, Any]:
        """Test Test Controller Service functionality"""
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                
                # Test scenarios endpoint
                async with session.get("http://localhost:50055/api/v1/scenarios") as response:
                    if response.status == 200:
                        scenarios_data = await response.json()
                        
                        # Test executions endpoint
                        async with session.get("http://localhost:50055/api/v1/executions") as response:
                            if response.status == 200:
                                executions_data = await response.json()
                                return {
                                    "status": "functional",
                                    "scenarios_count": len(scenarios_data.get("scenarios", [])),
                                    "active_executions": len(executions_data.get("active_executions", []))
                                }
                    
                    return {
                        "status": "non_functional",
                        "error": f"HTTP {response.status}"
                    }
                        
        except Exception as e:
            return {
                "status": "test_failed",
                "error": str(e)
            }
    
    def print_health_report(self, health_results: Dict[str, Any], 
                           intent_test: Dict[str, Any], 
                           controller_test: Dict[str, Any]):
        """Print comprehensive health report"""
        
        print("=" * 80)
        print("IVR FLOW AUTOMATION SYSTEM - HEALTH REPORT")
        print("=" * 80)
        print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()
        
        # Service Health Status
        print("SERVICE HEALTH STATUS:")
        print("-" * 40)
        
        critical_healthy = 0
        critical_total = 0
        
        for service_name, result in health_results.items():
            config = self.services[service_name]
            status_icon = {
                "healthy": "[OK]",
                "unhealthy": "[FAIL]", 
                "unreachable": "[DOWN]",
                "skipped": "[SKIP]"
            }.get(result["status"], "[?]")
            
            critical_marker = " [CRITICAL]" if config["critical"] else ""
            
            print(f"{status_icon} {config['name']}: {result['status'].upper()}{critical_marker}")
            
            if result.get("error"):
                print(f"    Error: {result['error']}")
                
            if config["critical"]:
                critical_total += 1
                if result["status"] == "healthy":
                    critical_healthy += 1
        
        print()
        
        # Functional Tests
        print("FUNCTIONAL TESTS:")
        print("-" * 40)
        
        intent_icon = "[OK]" if intent_test["status"] == "functional" else "[FAIL]"
        print(f"{intent_icon} Intent Service Classification: {intent_test['status'].upper()}")
        if intent_test.get("error"):
            print(f"    Error: {intent_test['error']}")
        
        controller_icon = "[OK]" if controller_test["status"] == "functional" else "[FAIL]"
        print(f"{controller_icon} Test Controller Service: {controller_test['status'].upper()}")
        if controller_test.get("error"):
            print(f"    Error: {controller_test['error']}")
        else:
            print(f"    Available scenarios: {controller_test.get('scenarios_count', 0)}")
            print(f"    Active executions: {controller_test.get('active_executions', 0)}")
        
        print()
        
        # Overall System Status
        print("OVERALL SYSTEM STATUS:")
        print("-" * 40)
        
        if critical_healthy == critical_total:
            if intent_test["status"] == "functional" and controller_test["status"] == "functional":
                print("[READY] SYSTEM READY - All critical services operational")
                system_status = "READY"
            else:
                print("[WARN] SYSTEM DEGRADED - Services running but functionality limited")
                system_status = "DEGRADED"
        else:
            print("[DOWN] SYSTEM DOWN - Critical services unavailable")
            system_status = "DOWN"
        
        print(f"Critical services: {critical_healthy}/{critical_total} healthy")
        print()
        
        # Recommendations
        if system_status != "READY":
            print("RECOMMENDATIONS:")
            print("-" * 40)
            
            for service_name, result in health_results.items():
                if result["status"] in ["unhealthy", "unreachable"] and self.services[service_name]["critical"]:
                    print(f"• Restart {self.services[service_name]['name']}")
            
            if intent_test["status"] != "functional":
                print("• Check Intent Service configuration and logs")
                
            if controller_test["status"] != "functional":
                print("• Check Test Controller Service configuration and logs")
            
            print()
        
        return system_status

async def main():
    """Main health check execution"""
    print("Starting comprehensive health check...")
    
    checker = ServiceHealthChecker()
    
    # Run all health checks
    health_results = await checker.check_all_services()
    intent_test = await checker.test_intent_service()
    controller_test = await checker.test_test_controller()
    
    # Print comprehensive report
    system_status = checker.print_health_report(health_results, intent_test, controller_test)
    
    # Exit with appropriate code
    if system_status == "READY":
        sys.exit(0)
    elif system_status == "DEGRADED": 
        sys.exit(1)
    else:
        sys.exit(2)

if __name__ == "__main__":
    asyncio.run(main())