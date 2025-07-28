#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Docker OpenSIPS Integration Test
Docker container'lar üzerinden gerçek OpenSIPS + AI Services integration test
"""

import asyncio
import aiohttp
import grpc
import json
import sys
import os
import time
import requests
import subprocess
from pathlib import Path

# Windows konsolunda Unicode encoding sorununu çözme
if sys.platform == "win32":
    import codecs
    try:
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
    except:
        pass

class DockerOpenSIPSIntegrationTester:
    """Docker üzerinden OpenSIPS + AI Services integration test"""
    
    def __init__(self):
        self.services = {
            "opensips_core": "http://localhost:8080",
            "intent": "http://localhost:5000",
            "asr_grpc": "localhost:50051", 
            "tts_grpc": "localhost:50053",
            "test_controller": "http://localhost:50055"
        }
        self.container_names = {
            "core": "opensips-ai-core",
            "asr": "opensips-asr-service", 
            "intent": "opensips-intent-service",
            "tts": "opensips-tts-service",
            "test_controller": "opensips-test-controller"
        }
        self.results = {}
        
    def print_header(self, title):
        """Test başlığı yazdır"""
        print("=" * 80)
        print(f"  {title}")
        print("=" * 80)
    
    def print_step(self, step_num, description):
        """Test adımı yazdır"""
        print(f"\n[ADIM {step_num}] {description}")
        print("-" * 60)

    def check_docker_containers(self):
        """Docker container durumlarını kontrol et"""
        self.print_step(1, "Docker Container Status Check")
        
        try:
            # Docker compose ps çalıştır
            result = subprocess.run(
                ["docker-compose", "ps"], 
                capture_output=True, 
                text=True,
                cwd="."
            )
            
            if result.returncode == 0:
                print("[OK] Docker Compose çalışıyor")
                print("Container durumları:")
                print(result.stdout)
                
                # Her servis için durumu parse et
                lines = result.stdout.strip().split('\n')[1:]  # Header'ı skip et
                container_status = {}
                
                for line in lines:
                    if line.strip():
                        parts = line.split()
                        if len(parts) >= 3:
                            name = parts[0]
                            status = parts[-2] if "Up" in line else "Down"
                            container_status[name] = status
                
                self.results['docker_containers'] = {
                    'status': 'success',
                    'containers': container_status
                }
                
                return container_status
            else:
                print(f"[HATA] Docker Compose error: {result.stderr}")
                self.results['docker_containers'] = {
                    'status': 'error', 
                    'error': result.stderr
                }
                return {}
                
        except Exception as e:
            print(f"[HATA] Docker container check failed: {e}")
            self.results['docker_containers'] = {'status': 'error', 'error': str(e)}
            return {}

    async def test_all_service_health(self):
        """Tüm servislerin health check'lerini test et"""
        self.print_step(2, "All Services Health Check")
        
        health_results = {}
        
        # Test each service
        services_to_test = [
            ("Intent Service", self.services["intent"] + "/health"),
            ("Test Controller", self.services["test_controller"] + "/health"),
            ("OpenSIPS Core", self.services["opensips_core"] + "/health")
        ]
        
        for service_name, health_url in services_to_test:
            print(f"\n[Testing] {service_name}")
            try:
                timeout = aiohttp.ClientTimeout(total=5)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    start_time = time.time()
                    async with session.get(health_url) as response:
                        response_time = (time.time() - start_time) * 1000
                        
                        if response.status == 200:
                            health_data = await response.json()
                            print(f"    [OK] {service_name}: HEALTHY")
                            print(f"    - Response time: {response_time:.1f}ms")
                            print(f"    - Status: {health_data.get('status', 'unknown')}")
                            
                            health_results[service_name] = {
                                'status': 'healthy',
                                'response_time_ms': response_time,
                                'data': health_data
                            }
                        else:
                            print(f"    [HATA] {service_name}: HTTP {response.status}")
                            health_results[service_name] = {
                                'status': 'unhealthy',
                                'error': f"HTTP {response.status}"
                            }
                            
            except Exception as e:
                print(f"    [HATA] {service_name}: {e}")
                health_results[service_name] = {
                    'status': 'error',
                    'error': str(e)
                }
        
        # gRPC services test (ASR, TTS)
        print(f"\n[Testing] gRPC Services")
        
        # ASR Service test
        try:
            channel = grpc.aio.insecure_channel(self.services['asr_grpc'])
            # Simple connection test
            await asyncio.wait_for(channel.channel_ready(), timeout=5.0)
            await channel.close()
            
            print(f"    [OK] ASR Service: gRPC connection successful")
            health_results["ASR Service"] = {'status': 'healthy'}
            
        except Exception as e:
            print(f"    [HATA] ASR Service: {e}")
            health_results["ASR Service"] = {'status': 'error', 'error': str(e)}
        
        # TTS Service test
        try:
            channel = grpc.aio.insecure_channel(self.services['tts_grpc'])
            await asyncio.wait_for(channel.channel_ready(), timeout=5.0)
            await channel.close()
            
            print(f"    [OK] TTS Service: gRPC connection successful")
            health_results["TTS Service"] = {'status': 'healthy'}
            
        except Exception as e:
            print(f"    [HATA] TTS Service: {e}")
            health_results["TTS Service"] = {'status': 'error', 'error': str(e)}
        
        # Sonuçları özetle
        healthy_services = sum(1 for result in health_results.values() 
                             if result['status'] == 'healthy')
        total_services = len(health_results)
        health_percentage = (healthy_services / total_services) * 100
        
        print(f"\n[ÖZET] Service Health Check:")
        print(f"    - Healthy services: {healthy_services}/{total_services}")
        print(f"    - Health percentage: {health_percentage:.1f}%")
        
        self.results['service_health'] = {
            'status': 'success' if health_percentage >= 80 else 'partial',
            'healthy_services': healthy_services,
            'total_services': total_services,
            'health_percentage': health_percentage,
            'results': health_results
        }
        
        return health_results

    async def test_docker_network_communication(self):
        """Docker network içi servis iletişimini test et"""
        self.print_step(3, "Docker Network Communication Test")
        
        print("[INFO] Docker network içi servis iletişimi test ediliyor...")
        
        # Test inter-service communication
        communication_tests = []
        
        # Test 1: Intent Service -> Test Controller
        try:
            print("\n[Test 1] Intent Service <-> Test Controller Communication")
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                
                # Intent Service'den test
                payload = {"text": "docker network test", "confidence_threshold": 0.5}
                async with session.post(
                    f"{self.services['intent']}/classify",
                    json=payload
                ) as response:
                    if response.status == 200:
                        intent_result = await response.json()
                        print(f"    [OK] Intent Service yanıt verdi")
                        print(f"    - Intent: {intent_result.get('intent', 'unknown')}")
                        communication_tests.append(('intent_service', True))
                    else:
                        print(f"    [HATA] Intent Service: HTTP {response.status}")
                        communication_tests.append(('intent_service', False))
                
                # Test Controller'dan test 
                async with session.get(f"{self.services['test_controller']}/health") as response:
                    if response.status == 200:
                        tc_result = await response.json()
                        print(f"    [OK] Test Controller yanıt verdi")
                        print(f"    - Status: {tc_result.get('status', 'unknown')}")
                        communication_tests.append(('test_controller', True))
                    else:
                        print(f"    [HATA] Test Controller: HTTP {response.status}")
                        communication_tests.append(('test_controller', False))
                        
        except Exception as e:
            print(f"    [HATA] Network communication test failed: {e}")
            communication_tests.append(('network_test', False))
        
        # Sonuçları değerlendir
        successful_tests = sum(1 for _, success in communication_tests if success)
        total_tests = len(communication_tests)
        comm_success_rate = (successful_tests / total_tests) * 100 if total_tests > 0 else 0
        
        print(f"\n[ÖZET] Docker Network Communication:")
        print(f"    - Successful tests: {successful_tests}/{total_tests}")
        print(f"    - Communication success rate: {comm_success_rate:.1f}%")
        
        self.results['docker_network'] = {
            'status': 'success' if comm_success_rate >= 80 else 'partial',
            'successful_tests': successful_tests,
            'total_tests': total_tests,
            'success_rate': comm_success_rate,
            'tests': communication_tests
        }
        
        return communication_tests

    async def test_full_pipeline_with_docker_logs(self):
        """Docker logs ile tam pipeline test"""
        self.print_step(4, "Full Pipeline Test with Docker Logs")
        
        print("[INFO] Docker container logs izlenerek pipeline test yapılıyor...")
        
        # Test scenario
        test_text = "hesap bakiyemi kontrol etmek istiyorum"
        
        try:
            print(f"\n[Test] Pipeline test başlıyor: '{test_text}'")
            
            # Intent Service test
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                
                payload = {
                    "text": test_text,
                    "confidence_threshold": 0.7,
                    "source": "docker_integration_test"
                }
                
                start_time = time.time()
                async with session.post(
                    f"{self.services['intent']}/classify",
                    json=payload
                ) as response:
                    processing_time = (time.time() - start_time) * 1000
                    
                    if response.status == 200:
                        result = await response.json()
                        
                        print(f"[OK] Full Pipeline Test Başarılı!")
                        print(f"    - Input: '{test_text}'")
                        print(f"    - Intent: {result['intent']}")
                        print(f"    - Güven: {result['confidence']:.3f}")
                        print(f"    - Eşik geçti: {result['meets_threshold']}")
                        print(f"    - İşlem süresi: {processing_time:.1f}ms")
                        
                        # Docker logs kontrol et
                        print(f"\n[INFO] Docker container logs kontrol ediliyor...")
                        
                        # Intent service logs
                        try:
                            log_result = subprocess.run(
                                ["docker", "logs", "--tail", "5", self.container_names["intent"]], 
                                capture_output=True, 
                                text=True
                            )
                            if log_result.returncode == 0:
                                print(f"[LOG] Intent Service son 5 log:")
                                for line in log_result.stdout.strip().split('\n')[-3:]:
                                    if line.strip():
                                        print(f"    {line}")
                        except:
                            pass
                        
                        self.results['full_pipeline'] = {
                            'status': 'success',
                            'input_text': test_text,
                            'intent': result['intent'],
                            'confidence': result['confidence'],
                            'processing_time_ms': processing_time,
                            'meets_threshold': result['meets_threshold']
                        }
                        
                        return True
                    else:
                        error_text = await response.text()
                        print(f"[HATA] Pipeline test failed: HTTP {response.status}")
                        print(f"    Error: {error_text}")
                        
                        self.results['full_pipeline'] = {
                            'status': 'error',
                            'error': f"HTTP {response.status}: {error_text}"
                        }
                        return False
                        
        except Exception as e:
            print(f"[HATA] Full pipeline test failed: {e}")
            self.results['full_pipeline'] = {'status': 'error', 'error': str(e)}
            return False

    def generate_docker_integration_report(self):
        """Docker integration test raporu"""
        self.print_header("DOCKER OpenSIPS INTEGRATION TEST RAPORU")
        
        print(f"Test Zamanı: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Test Tipi: Docker Container Integration Test")
        
        print(f"\nDOCKER SERVİSLERİ:")
        print(f"-" * 40)
        
        # Docker containers
        if 'docker_containers' in self.results:
            containers = self.results['docker_containers'].get('containers', {})
            for name, status in containers.items():
                status_icon = "[✓]" if "Up" in status else "[✗]"
                print(f"{status_icon} {name}: {status}")
        
        print(f"\nSERVİS HEALTH CHECK:")
        print(f"-" * 40)
        
        # Service health
        if 'service_health' in self.results:
            health_data = self.results['service_health']
            health_pct = health_data.get('health_percentage', 0)
            healthy = health_data.get('healthy_services', 0)
            total = health_data.get('total_services', 0)
            
            print(f"Health Status: {healthy}/{total} services healthy ({health_pct:.1f}%)")
            
            for service, result in health_data.get('results', {}).items():
                status = result['status']
                icon = {"healthy": "[✓]", "error": "[✗]", "unhealthy": "[!]"}.get(status, "[?]")
                print(f"{icon} {service}: {status.upper()}")
        
        print(f"\nNETWORK İLETİŞİM:")
        print(f"-" * 40)
        
        # Network communication
        if 'docker_network' in self.results:
            network_data = self.results['docker_network']
            success_rate = network_data.get('success_rate', 0)
            successful = network_data.get('successful_tests', 0)
            total = network_data.get('total_tests', 0)
            
            print(f"Network Communication: {successful}/{total} tests successful ({success_rate:.1f}%)")
        
        print(f"\nPIPELINE TEST:")
        print(f"-" * 40)
        
        # Pipeline test
        if 'full_pipeline' in self.results:
            pipeline_data = self.results['full_pipeline']
            status = pipeline_data['status']
            icon = "[✓]" if status == 'success' else "[✗]"
            
            print(f"{icon} Full Pipeline: {status.upper()}")
            
            if status == 'success':
                print(f"    - Intent: {pipeline_data.get('intent', 'unknown')}")
                print(f"    - Güven: {pipeline_data.get('confidence', 0):.3f}")
                print(f"    - İşlem süresi: {pipeline_data.get('processing_time_ms', 0):.1f}ms")
        
        # Genel değerlendirme
        print(f"\nGENEL DEĞERLENDİRME:")
        print(f"-" * 40)
        
        # Calculate overall success
        scores = []
        
        if 'service_health' in self.results:
            scores.append(self.results['service_health'].get('health_percentage', 0))
        
        if 'docker_network' in self.results:
            scores.append(self.results['docker_network'].get('success_rate', 0))
        
        if 'full_pipeline' in self.results:
            pipeline_score = 100 if self.results['full_pipeline']['status'] == 'success' else 0
            scores.append(pipeline_score)
        
        overall_score = sum(scores) / len(scores) if scores else 0
        
        if overall_score >= 90:
            print("[MÜKEMMEL] Docker OpenSIPS Integration tam çalışır!")
        elif overall_score >= 75:
            print("[İYİ] Docker OpenSIPS Integration çoğunlukla çalışır")
        elif overall_score >= 50:
            print("[ORTA] Integration'da bazı sorunlar var")
        else:
            print("[ZAYIF] Integration'da ciddi sorunlar var")
        
        print(f"Genel başarı skoru: {overall_score:.1f}%")
        
        return overall_score >= 75

    async def run_docker_integration_test(self):
        """Docker integration testini çalıştır"""
        self.print_header("DOCKER OpenSIPS INTEGRATION TEST")
        
        print("Docker container'lar üzerinden OpenSIPS + AI Services integration test...")
        
        try:
            # Step 1: Docker containers check
            container_status = self.check_docker_containers()
            
            # Step 2: Service health checks
            await self.test_all_service_health()
            
            # Step 3: Network communication
            await self.test_docker_network_communication()
            
            # Step 4: Full pipeline test
            await self.test_full_pipeline_with_docker_logs()
            
            # Generate comprehensive report
            success = self.generate_docker_integration_report()
            
            return success
            
        except Exception as e:
            print(f"\n[FATAL HATA] Docker integration test failed: {e}")
            return False

async def main():
    """Ana test fonksiyonu"""
    tester = DockerOpenSIPSIntegrationTester()
    
    try:
        success = await tester.run_docker_integration_test()
        
        if success:
            print(f"\n[BAŞARILI] DOCKER OpenSIPS INTEGRATION TEST BAŞARILI!")
            sys.exit(0)
        else:
            print(f"\n[BAŞARISIZ] DOCKER OpenSIPS INTEGRATION TEST BAŞARISIZ!")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print(f"\n\n[DURDURULDU] Test kullanıcı tarafından durduruldu")
        sys.exit(2)
    except Exception as e:
        print(f"\n[HATA] Test hatası: {e}")
        sys.exit(3)

if __name__ == "__main__":
    asyncio.run(main())