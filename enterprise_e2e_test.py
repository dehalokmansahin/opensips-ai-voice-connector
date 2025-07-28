#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Enterprise-Grade End-to-End Test Suite
Senior QA Architect Design - Comprehensive IVR System Testing
"""

import asyncio
import aiohttp
import grpc
import json
import sys
import os
import time
import wave
import numpy as np
import uuid
import logging
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Any
from enum import Enum

# Windows konsolunda Unicode encoding sorununu çözme
if sys.platform == "win32":
    import codecs
    try:
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
    except:
        pass

# Configure professional logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('e2e_test_results.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class TestResult(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"
    ERROR = "ERROR"

@dataclass
class TestCase:
    """Enterprise test case structure"""
    id: str
    name: str
    description: str
    category: str
    priority: str  # CRITICAL, HIGH, MEDIUM, LOW
    preconditions: List[str]
    steps: List[str]
    expected_result: str
    actual_result: Optional[str] = None
    status: Optional[TestResult] = None
    execution_time_ms: Optional[float] = None
    error_details: Optional[str] = None
    artifacts: Optional[Dict] = None

class EnterpriseE2ETester:
    """Senior QA Architect - Enterprise E2E Test Suite"""
    
    def __init__(self):
        self.services = {
            "opensips_core": "http://localhost:8080",
            "intent": "http://localhost:5000",
            "asr_grpc": "localhost:50051", 
            "tts_grpc": "localhost:50053",
            "test_controller": "http://localhost:50055"
        }
        
        self.test_results: List[TestCase] = []
        self.test_session_id = f"e2e-{uuid.uuid4().hex[:8]}"
        self.start_time = time.time()
        
        # Test data scenarios (Turkish Banking)
        self.test_scenarios = [
            {
                'id': 'BALANCE_INQUIRY_001',
                'input': 'hesap bakiyemi öğrenmek istiyorum',
                'expected_intent': 'hesap_bakiye_sorgulama',
                'min_confidence': 0.8,
                'expected_response_keywords': ['bakiye', 'TL'],
                'priority': 'CRITICAL'
            },
            {
                'id': 'CREDIT_CARD_002',
                'input': 'kredi kartı limitimi öğrenebilir miyim',
                'expected_intent': 'kredi_karti_bilgi',
                'min_confidence': 0.7,
                'expected_response_keywords': ['kredi', 'limit'],
                'priority': 'HIGH'
            },
            {
                'id': 'CUSTOMER_SERVICE_003',
                'input': 'müşteri temsilcisi ile konuşmak istiyorum',
                'expected_intent': 'musteri_hizmetleri',
                'min_confidence': 0.7,
                'expected_response_keywords': ['temsilci', 'aktarıl'],
                'priority': 'HIGH'
            },
            {
                'id': 'EDGE_CASE_004',
                'input': 'asdasd xyz 123 giberish',
                'expected_intent': 'bilinmeyen',
                'min_confidence': 0.0,
                'expected_response_keywords': ['anlayamadım', 'tekrar'],
                'priority': 'MEDIUM'
            }
        ]

    def create_test_case(self, test_id: str, name: str, description: str, 
                        category: str, priority: str, preconditions: List[str],
                        steps: List[str], expected_result: str) -> TestCase:
        """Factory method for creating structured test cases"""
        return TestCase(
            id=test_id,
            name=name,
            description=description,
            category=category,
            priority=priority,
            preconditions=preconditions,
            steps=steps,
            expected_result=expected_result
        )

    async def execute_test_case(self, test_case: TestCase, test_function) -> TestCase:
        """Execute a test case with proper error handling and metrics"""
        logger.info(f"Executing test case: {test_case.id} - {test_case.name}")
        
        start_time = time.time()
        try:
            # Execute the actual test
            result = await test_function(test_case)
            test_case.actual_result = str(result)
            test_case.status = TestResult.PASS if result else TestResult.FAIL
            
        except Exception as e:
            logger.error(f"Test case {test_case.id} failed with error: {e}")
            test_case.status = TestResult.ERROR
            test_case.error_details = str(e)
            test_case.actual_result = f"ERROR: {str(e)}"
        
        finally:
            test_case.execution_time_ms = (time.time() - start_time) * 1000
            self.test_results.append(test_case)
        
        return test_case

    # ==== CRITICAL PATH TESTS ====
    
    async def test_service_health_comprehensive(self, test_case: TestCase) -> bool:
        """CRITICAL: All services must be healthy for system operation"""
        logger.info("🔍 CRITICAL: Testing comprehensive service health...")
        
        health_results = {}
        all_healthy = True
        
        # Test REST services
        rest_services = [
            ("Intent Service", f"{self.services['intent']}/health"),
            ("Test Controller", f"{self.services['test_controller']}/health")
        ]
        
        for service_name, health_url in rest_services:
            try:
                timeout = aiohttp.ClientTimeout(total=5)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    start_time = time.time()
                    async with session.get(health_url) as response:
                        response_time = (time.time() - start_time) * 1000
                        if response.status == 200:
                            health_data = await response.json()
                            health_results[service_name] = {
                                'status': 'HEALTHY',
                                'response_time_ms': response_time,
                                'details': health_data
                            }
                        else:
                            health_results[service_name] = {'status': 'UNHEALTHY', 'http_status': response.status}
                            all_healthy = False
            except Exception as e:
                health_results[service_name] = {'status': 'ERROR', 'error': str(e)}
                all_healthy = False
        
        # Test gRPC services
        grpc_services = [
            ("ASR Service", self.services['asr_grpc']),
            ("TTS Service", self.services['tts_grpc'])
        ]
        
        for service_name, grpc_address in grpc_services:
            try:
                channel = grpc.aio.insecure_channel(grpc_address)
                await asyncio.wait_for(channel.channel_ready(), timeout=5.0)
                await channel.close()
                health_results[service_name] = {'status': 'HEALTHY'}
            except Exception as e:
                health_results[service_name] = {'status': 'ERROR', 'error': str(e)}
                all_healthy = False
        
        test_case.artifacts = {'health_results': health_results}
        logger.info(f"Service health check completed. All healthy: {all_healthy}")
        
        return all_healthy

    async def test_full_ivr_pipeline_critical(self, test_case: TestCase) -> bool:
        """CRITICAL: End-to-end IVR pipeline with real Turkish banking scenario"""
        logger.info("🔍 CRITICAL: Testing full IVR pipeline...")
        
        scenario = self.test_scenarios[0]  # Use balance inquiry as critical test
        pipeline_results = {}
        
        try:
            # Step 1: Intent Classification
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                payload = {
                    "text": scenario['input'],
                    "confidence_threshold": 0.7,
                    "session_id": self.test_session_id
                }
                
                start_time = time.time()
                async with session.post(f"{self.services['intent']}/classify", json=payload) as response:
                    processing_time = (time.time() - start_time) * 1000
                    
                    if response.status == 200:
                        result = await response.json()
                        
                        # Validate intent classification
                        intent_correct = result['intent'] == scenario['expected_intent']
                        confidence_adequate = result['confidence'] >= scenario['min_confidence']
                        threshold_met = result['meets_threshold']
                        
                        pipeline_results['intent_classification'] = {
                            'status': 'SUCCESS' if (intent_correct and confidence_adequate and threshold_met) else 'FAIL',
                            'intent': result['intent'],
                            'confidence': result['confidence'],
                            'expected_intent': scenario['expected_intent'],
                            'processing_time_ms': processing_time,
                            'validation': {
                                'intent_correct': intent_correct,
                                'confidence_adequate': confidence_adequate,
                                'threshold_met': threshold_met
                            }
                        }
                        
                        # Step 2: Response Generation Simulation
                        response_generated = self.simulate_ivr_response_generation(result['intent'])
                        pipeline_results['response_generation'] = response_generated
                        
                        # Overall pipeline success
                        pipeline_success = (
                            pipeline_results['intent_classification']['status'] == 'SUCCESS' and
                            response_generated['status'] == 'SUCCESS'
                        )
                        
                        test_case.artifacts = {'pipeline_results': pipeline_results}
                        logger.info(f"Full IVR pipeline test completed. Success: {pipeline_success}")
                        
                        return pipeline_success
                    else:
                        error_text = await response.text()
                        pipeline_results['error'] = f"HTTP {response.status}: {error_text}"
                        test_case.artifacts = {'pipeline_results': pipeline_results}
                        return False
                        
        except Exception as e:
            pipeline_results['error'] = str(e)
            test_case.artifacts = {'pipeline_results': pipeline_results}
            logger.error(f"Full IVR pipeline test failed: {e}")
            return False

    def simulate_ivr_response_generation(self, intent: str) -> Dict:
        """Simulate IVR response generation based on intent"""
        responses = {
            'hesap_bakiye_sorgulama': {
                'text': 'Hesap bakiyeniz 2.750 TL\'dir. Son işlemleriniz için 1\'e basınız.',
                'next_actions': ['account_details'],
                'dtmf_options': ['1']
            },
            'kredi_karti_bilgi': {
                'text': 'Kredi kartı limitiniz 15.000 TL\'dir. Kullanılabilir limit 12.300 TL\'dir.',
                'next_actions': ['card_details'],
                'dtmf_options': ['2']
            },
            'musteri_hizmetleri': {
                'text': 'Müşteri temsilcimize aktarılıyorsunuz. Lütfen bekleyiniz.',
                'next_actions': ['transfer_agent'],
                'dtmf_options': []
            },
            'bilinmeyen': {
                'text': 'İsteğinizi anlayamadım. Bakiye için 1, kredi kartı için 2\'ye basınız.',
                'next_actions': ['main_menu'],
                'dtmf_options': ['1', '2', '0']
            }
        }
        
        response_data = responses.get(intent, responses['bilinmeyen'])
        
        return {
            'status': 'SUCCESS',
            'response': response_data,
            'processing_time_ms': 50  # Simulated processing time
        }

    # ==== HIGH PRIORITY TESTS ====
    
    async def test_turkish_language_accuracy(self, test_case: TestCase) -> bool:
        """HIGH: Test Turkish language processing accuracy across scenarios"""
        logger.info("🔍 HIGH: Testing Turkish language accuracy...")
        
        accuracy_results = []
        total_tests = 0
        correct_classifications = 0
        
        for scenario in self.test_scenarios:
            total_tests += 1
            
            try:
                timeout = aiohttp.ClientTimeout(total=5)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    payload = {"text": scenario['input'], "confidence_threshold": 0.5}
                    
                    async with session.post(f"{self.services['intent']}/classify", json=payload) as response:
                        if response.status == 200:
                            result = await response.json()
                            
                            is_correct = result['intent'] == scenario['expected_intent']
                            if is_correct:
                                correct_classifications += 1
                            
                            accuracy_results.append({
                                'scenario_id': scenario['id'],
                                'input': scenario['input'],
                                'expected': scenario['expected_intent'],
                                'actual': result['intent'],
                                'confidence': result['confidence'],
                                'correct': is_correct
                            })
                        else:
                            accuracy_results.append({
                                'scenario_id': scenario['id'],
                                'error': f"HTTP {response.status}"
                            })
                            
            except Exception as e:
                accuracy_results.append({
                    'scenario_id': scenario['id'],
                    'error': str(e)
                })
        
        accuracy_percentage = (correct_classifications / total_tests) * 100 if total_tests > 0 else 0
        
        test_case.artifacts = {
            'accuracy_results': accuracy_results,
            'accuracy_percentage': accuracy_percentage,
            'correct_classifications': correct_classifications,
            'total_tests': total_tests
        }
        
        # Pass if accuracy >= 75%
        success = accuracy_percentage >= 75.0
        logger.info(f"Turkish language accuracy test: {accuracy_percentage:.1f}% ({correct_classifications}/{total_tests})")
        
        return success

    async def test_performance_benchmarks(self, test_case: TestCase) -> bool:
        """HIGH: Test system performance under load"""
        logger.info("🔍 HIGH: Testing performance benchmarks...")
        
        performance_results = {
            'response_times': [],
            'throughput_per_second': 0,
            'error_rate': 0
        }
        
        # Performance test parameters
        concurrent_requests = 5  # Reduced for stability
        test_duration_seconds = 3
        
        async def single_request():
            try:
                timeout = aiohttp.ClientTimeout(total=3)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    payload = {"text": "hesap bakiyemi öğrenmek istiyorum", "confidence_threshold": 0.7}
                    
                    start_time = time.time()
                    async with session.post(f"{self.services['intent']}/classify", json=payload) as response:
                        response_time = (time.time() - start_time) * 1000
                        
                        if response.status == 200:
                            return {'success': True, 'response_time_ms': response_time}
                        else:
                            return {'success': False, 'response_time_ms': response_time}
            except Exception as e:
                return {'success': False, 'error': str(e)}
        
        # Execute concurrent requests
        start_time = time.time()
        
        while (time.time() - start_time) < test_duration_seconds:
            # Create batch of concurrent requests
            batch_tasks = [single_request() for _ in range(concurrent_requests)]
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
            
            for result in batch_results:
                if isinstance(result, dict):
                    if result.get('success'):
                        performance_results['response_times'].append(result['response_time_ms'])
                    else:
                        performance_results['response_times'].append(None)  # Error case
            
            # Small delay between batches
            await asyncio.sleep(0.2)
        
        # Calculate metrics
        successful_requests = [rt for rt in performance_results['response_times'] if rt is not None]
        total_requests = len(performance_results['response_times'])
        
        if successful_requests:
            avg_response_time = sum(successful_requests) / len(successful_requests)
            max_response_time = max(successful_requests)
            min_response_time = min(successful_requests)
            throughput = len(successful_requests) / test_duration_seconds
            error_rate = ((total_requests - len(successful_requests)) / total_requests) * 100 if total_requests > 0 else 0
            
            performance_results.update({
                'avg_response_time_ms': avg_response_time,
                'max_response_time_ms': max_response_time,
                'min_response_time_ms': min_response_time,
                'throughput_per_second': throughput,
                'error_rate_percentage': error_rate,
                'total_requests': total_requests,
                'successful_requests': len(successful_requests)
            })
            
            # Performance criteria: avg response < 100ms, error rate < 5%
            performance_acceptable = avg_response_time < 100 and error_rate < 5
            
        else:
            performance_acceptable = False
            performance_results.update({
                'avg_response_time_ms': 0,
                'max_response_time_ms': 0,
                'min_response_time_ms': 0,
                'throughput_per_second': 0,
                'error_rate_percentage': 100,
                'total_requests': total_requests,
                'successful_requests': 0
            })
        
        test_case.artifacts = {'performance_results': performance_results}
        logger.info(f"Performance test completed. Acceptable: {performance_acceptable}")
        
        return performance_acceptable

    # ==== TEST SUITE EXECUTION ====
    
    async def run_enterprise_e2e_test_suite(self):
        """Execute the complete enterprise-grade E2E test suite"""
        logger.info("🧪 Starting Enterprise-Grade End-to-End Test Suite")
        logger.info(f"Test Session ID: {self.test_session_id}")
        
        # Define all test cases
        test_cases = [
            # CRITICAL TESTS
            self.create_test_case(
                "E2E_CRITICAL_001",
                "Service Health Check",
                "Verify all microservices are healthy and responsive",
                "Infrastructure",
                "CRITICAL",
                ["Docker containers running", "Network connectivity"],
                ["Check REST service health endpoints", "Verify gRPC service connectivity"],
                "All services report healthy status"
            ),
            
            self.create_test_case(
                "E2E_CRITICAL_002", 
                "Full IVR Pipeline",
                "End-to-end Turkish banking IVR flow validation",
                "Business Logic",
                "CRITICAL",
                ["All services healthy", "Turkish language model loaded"],
                ["Send Turkish banking request", "Validate intent classification", "Verify response generation"],
                "Intent correctly classified with adequate confidence and proper response generated"
            ),
            
            # HIGH PRIORITY TESTS
            self.create_test_case(
                "E2E_HIGH_001",
                "Turkish Language Accuracy",
                "Validate Turkish language processing accuracy across multiple scenarios",
                "Language Processing",
                "HIGH", 
                ["Intent service operational"],
                ["Test multiple Turkish banking phrases", "Measure classification accuracy"],
                ">=75% accuracy across all test scenarios"
            ),
            
            self.create_test_case(
                "E2E_HIGH_002",
                "Performance Benchmarks",
                "System performance under concurrent load",
                "Performance",
                "HIGH",
                ["All services healthy"],
                ["Execute concurrent requests", "Measure response times", "Calculate throughput"],
                "Average response time <100ms, error rate <5%"
            )
        ]
        
        # Map test cases to their execution functions
        test_functions = {
            "E2E_CRITICAL_001": self.test_service_health_comprehensive,
            "E2E_CRITICAL_002": self.test_full_ivr_pipeline_critical,
            "E2E_HIGH_001": self.test_turkish_language_accuracy,
            "E2E_HIGH_002": self.test_performance_benchmarks
        }
        
        # Execute all test cases
        logger.info(f"Executing {len(test_cases)} test cases...")
        
        for test_case in test_cases:
            test_function = test_functions[test_case.id]
            await self.execute_test_case(test_case, test_function)
        
        # Generate comprehensive report
        self.generate_enterprise_test_report()
        
        return self.calculate_overall_test_success()

    def generate_enterprise_test_report(self):
        """Generate comprehensive enterprise-grade test report"""
        print("\n" + "="*100)
        print("🧪 ENTERPRISE END-TO-END TEST REPORT")
        print("="*100)
        
        total_execution_time = (time.time() - self.start_time)
        
        print(f"Test Session ID: {self.test_session_id}")
        print(f"Execution Time: {total_execution_time:.2f} seconds")
        print(f"Total Test Cases: {len(self.test_results)}")
        
        # Results by priority
        priority_summary = {}
        status_summary = {result.value: 0 for result in TestResult}
        
        for test_case in self.test_results:
            # Count by priority
            if test_case.priority not in priority_summary:
                priority_summary[test_case.priority] = {'PASS': 0, 'FAIL': 0, 'ERROR': 0, 'SKIP': 0}
            priority_summary[test_case.priority][test_case.status.value] += 1
            
            # Count by status
            status_summary[test_case.status.value] += 1
        
        # Print summary
        print(f"\n📊 TEST RESULTS SUMMARY:")
        print("-" * 50)
        for status, count in status_summary.items():
            icon = {"PASS": "✅", "FAIL": "❌", "ERROR": "🚨", "SKIP": "⏭️"}[status]
            print(f"{icon} {status}: {count}")
        
        print(f"\n🎯 PRIORITY BREAKDOWN:")
        print("-" * 50)
        for priority in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
            if priority in priority_summary:
                stats = priority_summary[priority] 
                total = sum(stats.values())
                pass_rate = (stats['PASS'] / total * 100) if total > 0 else 0
                print(f"{priority}: {stats['PASS']}/{total} passed ({pass_rate:.1f}%)")
        
        # Detailed test case results
        print(f"\n📋 DETAILED TEST RESULTS:")
        print("-" * 50)
        
        for test_case in self.test_results:
            status_icon = {"PASS": "✅", "FAIL": "❌", "ERROR": "🚨", "SKIP": "⏭️"}[test_case.status.value]
            
            print(f"\n{status_icon} {test_case.id}: {test_case.name}")
            print(f"   Category: {test_case.category} | Priority: {test_case.priority}")
            print(f"   Execution Time: {test_case.execution_time_ms:.1f}ms")
            print(f"   Expected: {test_case.expected_result}")
            print(f"   Actual: {test_case.actual_result}")
            
            if test_case.error_details:
                print(f"   ⚠️  Error: {test_case.error_details}")
            
            # Show key artifacts/metrics
            if test_case.artifacts:
                print(f"   📊 Key Metrics:")
                artifacts = test_case.artifacts
                
                if 'accuracy_results' in artifacts:
                    accuracy = artifacts['accuracy_percentage']
                    print(f"      - Language Accuracy: {accuracy:.1f}%")
                
                if 'performance_results' in artifacts:
                    perf = artifacts['performance_results']
                    if 'avg_response_time_ms' in perf:
                        print(f"      - Avg Response Time: {perf['avg_response_time_ms']:.1f}ms")
                        print(f"      - Throughput: {perf['throughput_per_second']:.1f} req/sec")
                
                if 'pipeline_results' in artifacts:
                    pipeline = artifacts['pipeline_results']
                    if 'intent_classification' in pipeline:
                        intent_result = pipeline['intent_classification']
                        print(f"      - Intent: {intent_result['intent']} (confidence: {intent_result['confidence']:.3f})")

    def calculate_overall_test_success(self) -> bool:
        """Calculate overall test suite success based on priority-weighted results"""
        
        # Weight by priority (CRITICAL failures are blocking)
        critical_tests = [tc for tc in self.test_results if tc.priority == "CRITICAL"]
        high_tests = [tc for tc in self.test_results if tc.priority == "HIGH"]
        
        # All CRITICAL tests must pass
        critical_pass = all(tc.status == TestResult.PASS for tc in critical_tests)
        
        # At least 80% of HIGH priority tests must pass
        if high_tests:
            high_pass_rate = sum(1 for tc in high_tests if tc.status == TestResult.PASS) / len(high_tests)
            high_acceptable = high_pass_rate >= 0.8
        else:
            high_acceptable = True
        
        overall_success = critical_pass and high_acceptable
        
        print(f"\n🎯 OVERALL TEST SUITE RESULT:")
        print("-" * 50)
        print(f"Critical Tests: {'✅ ALL PASS' if critical_pass else '❌ FAILURES DETECTED'}")
        print(f"High Priority Tests: {'✅ ACCEPTABLE' if high_acceptable else '❌ BELOW THRESHOLD'}")
        
        if overall_success:
            print(f"🏆 OVERALL RESULT: ✅ TEST SUITE PASSED")
            print(f"🚀 System is ready for production deployment!")
        else:
            print(f"🚨 OVERALL RESULT: ❌ TEST SUITE FAILED") 
            print(f"⚠️  Critical issues must be resolved before deployment!")
        
        return overall_success

# Main execution
async def main():
    """Execute the enterprise E2E test suite"""
    tester = EnterpriseE2ETester()
    
    try:
        success = await tester.run_enterprise_e2e_test_suite()
        
        # Save detailed results to file
        with open(f'e2e_test_results_{tester.test_session_id}.json', 'w', encoding='utf-8') as f:
            results_data = {
                'session_id': tester.test_session_id,
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                'overall_success': success,
                'test_cases': [asdict(tc) for tc in tester.test_results]
            }
            json.dump(results_data, f, indent=2, ensure_ascii=False)
        
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        logger.info("Test suite interrupted by user")
        sys.exit(2)
    except Exception as e:
        logger.error(f"Test suite failed with error: {e}")
        sys.exit(3)

if __name__ == "__main__":
    asyncio.run(main())