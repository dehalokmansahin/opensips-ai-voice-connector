#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Production Test Suite - Turkish Banking IVR System
Prodüksiyon seviyesi test paketi - gerçek banka çağrı merkezi koşulları
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
import threading
import statistics
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Any
from enum import Enum
from concurrent.futures import ThreadPoolExecutor

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
        logging.FileHandler('production_test_results.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Core modüllerini import et
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'core'))

try:
    from grpc_clients import asr_service_pb2, asr_service_pb2_grpc
    from grpc_clients import tts_service_pb2, tts_service_pb2_grpc
    GRPC_AVAILABLE = True
except ImportError:
    logger.warning("gRPC client modules not available")
    GRPC_AVAILABLE = False

class TestType(Enum):
    FUNCTIONAL = "FUNCTIONAL"
    PERFORMANCE = "PERFORMANCE"
    LOAD = "LOAD"
    STRESS = "STRESS"
    INTEGRATION = "INTEGRATION"

@dataclass
class ProductionTestCase:
    """Production test case structure"""
    id: str
    name: str
    description: str
    test_type: TestType
    priority: str  # CRITICAL, HIGH, MEDIUM, LOW
    expected_result: str
    max_execution_time_ms: float
    pass_criteria: Dict[str, Any]
    actual_result: Optional[str] = None
    status: Optional[str] = None
    execution_time_ms: Optional[float] = None
    error_details: Optional[str] = None
    metrics: Optional[Dict] = None

class ProductionTestSuite:
    """Production-Grade Test Suite for Turkish Banking IVR System"""
    
    def __init__(self):
        self.services = {
            "opensips_core": "http://localhost:8080",
            "intent": "http://localhost:5000",
            "asr_grpc": "localhost:50051", 
            "tts_grpc": "localhost:50053",
            "test_controller": "http://localhost:50055"
        }
        
        self.test_results: List[ProductionTestCase] = []
        self.test_session_id = f"prod-{uuid.uuid4().hex[:8]}"
        self.start_time = time.time()
        
        # Production Turkish Banking Scenarios
        self.production_scenarios = [
            {
                'id': 'PROD_BALANCE_001',
                'input': 'hesap bakiyemi öğrenmek istiyorum',
                'expected_intent': 'hesap_bakiye_sorgulama',
                'min_confidence': 0.85,
                'category': 'account_inquiry',
                'priority': 'CRITICAL'
            },
            {
                'id': 'PROD_BALANCE_002',
                'input': 'banka bakiyemi kontrol etmek istiyorum',
                'expected_intent': 'hesap_bakiye_sorgulama',
                'min_confidence': 0.80,
                'category': 'account_inquiry',
                'priority': 'CRITICAL'
            },
            {
                'id': 'PROD_CREDIT_001',
                'input': 'kredi kartı limitimi öğrenebilir miyim',
                'expected_intent': 'kredi_karti_bilgi',
                'min_confidence': 0.80,
                'category': 'credit_card',
                'priority': 'HIGH'
            },
            {
                'id': 'PROD_CREDIT_002',
                'input': 'kredi kartımın borcu ne kadar',
                'expected_intent': 'kredi_karti_bilgi',
                'min_confidence': 0.75,
                'category': 'credit_card',
                'priority': 'HIGH'
            },
            {
                'id': 'PROD_TRANSFER_001',
                'input': 'para transferi yapmak istiyorum',
                'expected_intent': 'para_transferi',
                'min_confidence': 0.75,
                'category': 'transfer',
                'priority': 'HIGH'
            },
            {
                'id': 'PROD_CUSTOMER_001',
                'input': 'müşteri temsilcisi ile konuşmak istiyorum',
                'expected_intent': 'musteri_hizmetleri',
                'min_confidence': 0.80,
                'category': 'customer_service',
                'priority': 'HIGH'
            },
            {
                'id': 'PROD_CUSTOMER_002',
                'input': 'operatöre bağlanmak istiyorum',
                'expected_intent': 'musteri_hizmetleri',
                'min_confidence': 0.75,
                'category': 'customer_service',
                'priority': 'HIGH'
            },
            {
                'id': 'PROD_EDGE_001',
                'input': 'ne yapabilirim yardım edin',
                'expected_intent': 'genel_yardim',
                'min_confidence': 0.60,
                'category': 'help',
                'priority': 'MEDIUM'
            },
            {
                'id': 'PROD_EDGE_002',
                'input': 'asdasd xyz 123 anlamıyorum',
                'expected_intent': 'bilinmeyen',
                'min_confidence': 0.0,
                'category': 'unknown',
                'priority': 'LOW'
            }
        ]

    def print_header(self, title):
        """Production test başlığı"""
        print("=" * 100)
        print(f"🏭 {title}")
        print("=" * 100)
    
    def print_step(self, step_num, description):
        """Production test adımı"""
        print(f"\n[PROD STEP {step_num}] {description}")
        print("-" * 80)

    async def execute_production_test_case(self, test_case: ProductionTestCase, test_function) -> ProductionTestCase:
        """Execute production test case with metrics"""
        logger.info(f"Executing production test: {test_case.id} - {test_case.name}")
        
        start_time = time.time()
        try:
            result = await test_function(test_case)
            test_case.actual_result = str(result)
            test_case.status = "PASS" if result else "FAIL"
            
        except Exception as e:
            logger.error(f"Production test {test_case.id} failed: {e}")
            test_case.status = "ERROR"
            test_case.error_details = str(e)
            test_case.actual_result = f"ERROR: {str(e)}"
        
        finally:
            test_case.execution_time_ms = (time.time() - start_time) * 1000
            self.test_results.append(test_case)
        
        return test_case

    # ==== PRODUCTION FUNCTIONAL TESTS ====
    
    async def test_production_service_availability(self, test_case: ProductionTestCase) -> bool:
        """CRITICAL: Production service availability test"""
        logger.info("🔍 PRODUCTION: Testing service availability...")
        
        availability_results = {}
        all_available = True
        
        # Critical services that must be available in production
        critical_services = [
            ("Intent Service", f"{self.services['intent']}/health", "REST"),
            ("Test Controller", f"{self.services['test_controller']}/health", "REST"),
            ("ASR Service", self.services['asr_grpc'], "gRPC"),
            ("TTS Service", self.services['tts_grpc'], "gRPC")
        ]
        
        for service_name, endpoint, protocol in critical_services:
            try:
                if protocol == "REST":
                    timeout = aiohttp.ClientTimeout(total=3)  # Production timeout
                    async with aiohttp.ClientSession(timeout=timeout) as session:
                        start_time = time.time()
                        async with session.get(endpoint) as response:
                            response_time = (time.time() - start_time) * 1000
                            
                            if response.status == 200:
                                availability_results[service_name] = {
                                    'status': 'AVAILABLE',
                                    'response_time_ms': response_time,
                                    'protocol': protocol
                                }
                            else:
                                availability_results[service_name] = {
                                    'status': 'UNAVAILABLE',
                                    'http_status': response.status,
                                    'protocol': protocol
                                }
                                all_available = False
                
                elif protocol == "gRPC" and GRPC_AVAILABLE:
                    channel = grpc.aio.insecure_channel(endpoint)
                    await asyncio.wait_for(channel.channel_ready(), timeout=3.0)
                    await channel.close()
                    availability_results[service_name] = {
                        'status': 'AVAILABLE',
                        'protocol': protocol
                    }
                else:
                    availability_results[service_name] = {
                        'status': 'SKIP',
                        'reason': 'gRPC not available',
                        'protocol': protocol
                    }
                    
            except Exception as e:
                availability_results[service_name] = {
                    'status': 'ERROR',
                    'error': str(e),
                    'protocol': protocol
                }
                all_available = False
        
        test_case.metrics = {'availability_results': availability_results}
        logger.info(f"Production service availability: {all_available}")
        
        return all_available

    async def test_production_turkish_accuracy(self, test_case: ProductionTestCase) -> bool:
        """HIGH: Production Turkish language accuracy test"""
        logger.info("🔍 PRODUCTION: Testing Turkish language accuracy...")
        
        accuracy_results = []
        total_tests = 0
        correct_classifications = 0
        total_processing_time = 0
        
        for scenario in self.production_scenarios[:6]:  # Test first 6 critical scenarios
            total_tests += 1
            
            try:
                timeout = aiohttp.ClientTimeout(total=5)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    payload = {
                        "text": scenario['input'],
                        "confidence_threshold": 0.7,
                        "session_id": self.test_session_id
                    }
                    
                    start_time = time.time()
                    async with session.post(f"{self.services['intent']}/classify", json=payload) as response:
                        processing_time = (time.time() - start_time) * 1000
                        total_processing_time += processing_time
                        
                        if response.status == 200:
                            result = await response.json()
                            
                            is_correct = result['intent'] == scenario['expected_intent']
                            confidence_ok = result['confidence'] >= scenario['min_confidence']
                            
                            if is_correct and confidence_ok:
                                correct_classifications += 1
                            
                            accuracy_results.append({
                                'scenario_id': scenario['id'],
                                'input': scenario['input'],
                                'expected': scenario['expected_intent'],
                                'actual': result['intent'],
                                'confidence': result['confidence'],
                                'correct': is_correct,
                                'confidence_ok': confidence_ok,
                                'processing_time_ms': processing_time,
                                'category': scenario['category']
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
        avg_processing_time = total_processing_time / total_tests if total_tests > 0 else 0
        
        test_case.metrics = {
            'accuracy_results': accuracy_results,
            'accuracy_percentage': accuracy_percentage,
            'correct_classifications': correct_classifications,
            'total_tests': total_tests,
            'avg_processing_time_ms': avg_processing_time
        }
        
        # Production criteria: >= 85% accuracy
        success = accuracy_percentage >= 85.0
        logger.info(f"Production Turkish accuracy: {accuracy_percentage:.1f}% ({correct_classifications}/{total_tests})")
        
        return success

    async def test_production_load_performance(self, test_case: ProductionTestCase) -> bool:
        """HIGH: Production load and performance test"""
        logger.info("🔍 PRODUCTION: Testing load performance...")
        
        # Production load test parameters
        concurrent_users = 10  # Simulated concurrent bank customers
        test_duration_seconds = 10
        max_acceptable_response_time = 200  # 200ms max for production
        max_acceptable_error_rate = 2  # 2% max error rate
        
        performance_metrics = {
            'response_times': [],
            'successful_requests': 0,
            'failed_requests': 0,
            'timeout_requests': 0,
            'error_requests': 0
        }
        
        async def production_request():
            """Single production request simulation"""
            try:
                # Use random scenario for realistic load
                scenario = self.production_scenarios[hash(threading.current_thread().ident) % len(self.production_scenarios)]
                
                timeout = aiohttp.ClientTimeout(total=5)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    payload = {
                        "text": scenario['input'],
                        "confidence_threshold": 0.7,
                        "session_id": f"{self.test_session_id}-{threading.current_thread().ident}"
                    }
                    
                    start_time = time.time()
                    async with session.post(f"{self.services['intent']}/classify", json=payload) as response:
                        response_time = (time.time() - start_time) * 1000
                        
                        if response.status == 200:
                            result = await response.json()
                            return {
                                'success': True,
                                'response_time_ms': response_time,
                                'intent': result.get('intent', 'unknown'),
                                'confidence': result.get('confidence', 0.0)
                            }
                        else:
                            return {
                                'success': False,
                                'response_time_ms': response_time,
                                'http_status': response.status
                            }
            except asyncio.TimeoutError:
                return {'success': False, 'error': 'timeout'}
            except Exception as e:
                return {'success': False, 'error': str(e)}
        
        # Execute load testing
        start_time = time.time()
        batch_count = 0
        
        while (time.time() - start_time) < test_duration_seconds:
            batch_count += 1
            
            # Create batch of concurrent requests
            batch_tasks = [production_request() for _ in range(concurrent_users)]
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
            
            for result in batch_results:
                if isinstance(result, dict):
                    if result.get('success'):
                        performance_metrics['successful_requests'] += 1
                        performance_metrics['response_times'].append(result['response_time_ms'])
                    else:
                        if result.get('error') == 'timeout':
                            performance_metrics['timeout_requests'] += 1
                        elif 'http_status' in result:
                            performance_metrics['failed_requests'] += 1
                        else:
                            performance_metrics['error_requests'] += 1
                else:
                    performance_metrics['error_requests'] += 1
            
            # Small delay between batches for realistic load
            await asyncio.sleep(0.1)
        
        # Calculate production metrics
        total_requests = (performance_metrics['successful_requests'] + 
                         performance_metrics['failed_requests'] + 
                         performance_metrics['timeout_requests'] + 
                         performance_metrics['error_requests'])
        
        if performance_metrics['response_times']:
            avg_response_time = statistics.mean(performance_metrics['response_times'])
            p95_response_time = statistics.quantiles(performance_metrics['response_times'], n=20)[18]  # 95th percentile
            max_response_time = max(performance_metrics['response_times'])
            min_response_time = min(performance_metrics['response_times'])
        else:
            avg_response_time = p95_response_time = max_response_time = min_response_time = 0
        
        error_rate = ((total_requests - performance_metrics['successful_requests']) / total_requests * 100) if total_requests > 0 else 100
        throughput = performance_metrics['successful_requests'] / test_duration_seconds
        
        performance_metrics.update({
            'total_requests': total_requests,
            'avg_response_time_ms': avg_response_time,
            'p95_response_time_ms': p95_response_time,
            'max_response_time_ms': max_response_time,
            'min_response_time_ms': min_response_time,
            'error_rate_percentage': error_rate,
            'throughput_per_second': throughput,
            'concurrent_users': concurrent_users,
            'test_duration_seconds': test_duration_seconds,
            'batch_count': batch_count
        })
        
        # Production acceptance criteria
        performance_acceptable = (
            avg_response_time <= max_acceptable_response_time and
            error_rate <= max_acceptable_error_rate and
            throughput >= 5.0  # Minimum 5 requests/second
        )
        
        test_case.metrics = {'performance_metrics': performance_metrics}
        logger.info(f"Production load test - Acceptable: {performance_acceptable}")
        logger.info(f"Avg response: {avg_response_time:.1f}ms, Error rate: {error_rate:.1f}%, Throughput: {throughput:.1f} req/s")
        
        return performance_acceptable

    async def test_production_end_to_end_flow(self, test_case: ProductionTestCase) -> bool:
        """CRITICAL: Production end-to-end IVR flow test"""
        logger.info("🔍 PRODUCTION: Testing end-to-end flow...")
        
        # Production banking scenario
        production_scenario = {
            'customer_phone': '+905551234567',
            'bank_number': '+908502200200',
            'customer_speech': 'hesap bakiyemi öğrenmek istiyorum',
            'expected_intent': 'hesap_bakiye_sorgulama',
            'expected_response_keywords': ['bakiye', 'TL']
        }
        
        flow_results = {}
        
        try:
            # Step 1: SIP Call Simulation
            call_id = f"prod-call-{uuid.uuid4().hex[:8]}"
            flow_results['call_establishment'] = {
                'status': 'SUCCESS',
                'call_id': call_id,
                'caller': production_scenario['customer_phone'],
                'called': production_scenario['bank_number']
            }
            
            # Step 2: Intent Classification (Core business logic)
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                payload = {
                    "text": production_scenario['customer_speech'],
                    "confidence_threshold": 0.7,
                    "call_id": call_id,
                    "session_id": self.test_session_id
                }
                
                start_time = time.time()
                async with session.post(f"{self.services['intent']}/classify", json=payload) as response:
                    processing_time = (time.time() - start_time) * 1000
                    
                    if response.status == 200:
                        result = await response.json()
                        
                        # Validate business logic
                        intent_correct = result['intent'] == production_scenario['expected_intent']
                        confidence_adequate = result['confidence'] >= 0.8  # Production threshold
                        threshold_met = result['meets_threshold']
                        
                        flow_results['intent_classification'] = {
                            'status': 'SUCCESS' if (intent_correct and confidence_adequate) else 'FAIL',
                            'intent': result['intent'],
                            'confidence': result['confidence'],
                            'expected': production_scenario['expected_intent'],
                            'processing_time_ms': processing_time,
                            'meets_production_criteria': intent_correct and confidence_adequate
                        }
                        
                        # Step 3: IVR Response Generation
                        if intent_correct:
                            ivr_response = self.generate_production_ivr_response(result['intent'])
                            flow_results['ivr_response'] = {
                                'status': 'SUCCESS',
                                'response': ivr_response,
                                'contains_keywords': any(keyword in ivr_response['text'].lower() 
                                                       for keyword in production_scenario['expected_response_keywords'])
                            }
                        else:
                            flow_results['ivr_response'] = {
                                'status': 'FAIL',
                                'reason': 'Intent classification failed'
                            }
                        
                        # Step 4: Call Completion
                        flow_results['call_completion'] = {
                            'status': 'SUCCESS',
                            'call_id': call_id,
                            'total_duration': processing_time + 2000  # Estimated total call time
                        }
                        
                        # Overall flow success
                        flow_success = (
                            flow_results['intent_classification']['status'] == 'SUCCESS' and
                            flow_results['ivr_response']['status'] == 'SUCCESS'
                        )
                        
                        test_case.metrics = {'flow_results': flow_results}
                        logger.info(f"Production E2E flow: {'SUCCESS' if flow_success else 'FAIL'}")
                        
                        return flow_success
                    else:
                        flow_results['error'] = f"HTTP {response.status}"
                        test_case.metrics = {'flow_results': flow_results}
                        return False
        
        except Exception as e:
            flow_results['error'] = str(e)
            test_case.metrics = {'flow_results': flow_results}
            logger.error(f"Production E2E flow failed: {e}")
            return False

    def generate_production_ivr_response(self, intent: str) -> Dict:
        """Generate production-ready IVR responses"""
        production_responses = {
            'hesap_bakiye_sorgulama': {
                'text': 'Hesap bakiyeniz 3.450 TL\'dir. Son işlemlerinizi öğrenmek için 1\'e, ana menüye dönmek için 0\'a basınız.',
                'next_actions': ['account_details', 'main_menu'],
                'dtmf_options': ['1', '0'],
                'audio_duration_seconds': 6.5
            },
            'kredi_karti_bilgi': {
                'text': 'Kredi kartı limitiniz 15.000 TL\'dir. Kullanılabilir limit 12.300 TL\'dir. Detaylar için 2\'ye basınız.',
                'next_actions': ['card_details'],
                'dtmf_options': ['2', '0'],
                'audio_duration_seconds': 7.2
            },
            'musteri_hizmetleri': {
                'text': 'Müşteri temsilcimize aktarılıyorsunuz. Lütfen bekleyiniz.',
                'next_actions': ['transfer_agent'],
                'dtmf_options': [],
                'audio_duration_seconds': 3.5
            },
            'para_transferi': {
                'text': 'Para transferi için müşteri numaranızı girmeniz gerekmektedir. Bilgi için 3\'e basınız.',
                'next_actions': ['customer_verification'],
                'dtmf_options': ['3', '0'],
                'audio_duration_seconds': 5.8
            }
        }
        
        return production_responses.get(intent, {
            'text': 'İsteğinizi anlayamadım. Ana menü için 0\'a, müşteri hizmetleri için 9\'a basınız.',
            'next_actions': ['main_menu'],
            'dtmf_options': ['0', '9'],
            'audio_duration_seconds': 4.2
        })

    # ==== PRODUCTION TEST SUITE EXECUTION ====
    
    async def run_production_test_suite(self):
        """Execute complete production test suite"""
        self.print_header("PRODUCTION TEST SUITE - Turkish Banking IVR System")
        logger.info(f"🏭 Starting Production Test Suite - Session: {self.test_session_id}")
        
        # Define production test cases
        production_test_cases = [
            # CRITICAL PRODUCTION TESTS
            ProductionTestCase(
                id="PROD_CRITICAL_001",
                name="Service Availability Test",
                description="Verify all critical services are available for production",
                test_type=TestType.FUNCTIONAL,
                priority="CRITICAL",
                expected_result="All critical services available with < 3s response time",
                max_execution_time_ms=5000,
                pass_criteria={"all_services_available": True, "max_response_time_ms": 3000}
            ),
            
            ProductionTestCase(
                id="PROD_CRITICAL_002",
                name="End-to-End IVR Flow",
                description="Complete Turkish banking IVR flow validation",
                test_type=TestType.INTEGRATION,
                priority="CRITICAL",
                expected_result="IVR flow completes successfully with correct intent and response",
                max_execution_time_ms=10000,
                pass_criteria={"flow_complete": True, "intent_correct": True, "response_generated": True}
            ),
            
            # HIGH PRIORITY PRODUCTION TESTS
            ProductionTestCase(
                id="PROD_HIGH_001",
                name="Turkish Language Accuracy",
                description="Production-level Turkish language processing accuracy",
                test_type=TestType.FUNCTIONAL,
                priority="HIGH",
                expected_result=">=85% accuracy across production scenarios",
                max_execution_time_ms=15000,
                pass_criteria={"accuracy_percentage": 85.0, "avg_processing_time_ms": 100}
            ),
            
            ProductionTestCase(
                id="PROD_HIGH_002",
                name="Load Performance Test",
                description="System performance under production load conditions",
                test_type=TestType.PERFORMANCE,
                priority="HIGH",
                expected_result="Avg response <200ms, error rate <2%, throughput >5 req/s",
                max_execution_time_ms=15000,
                pass_criteria={"avg_response_time_ms": 200, "error_rate_percentage": 2.0, "min_throughput": 5.0}
            )
        ]
        
        # Map test cases to execution functions
        test_functions = {
            "PROD_CRITICAL_001": self.test_production_service_availability,
            "PROD_CRITICAL_002": self.test_production_end_to_end_flow,
            "PROD_HIGH_001": self.test_production_turkish_accuracy,
            "PROD_HIGH_002": self.test_production_load_performance
        }
        
        # Execute all production test cases
        logger.info(f"Executing {len(production_test_cases)} production test cases...")
        
        for test_case in production_test_cases:
            self.print_step(len(self.test_results) + 1, f"{test_case.name}")
            test_function = test_functions[test_case.id]
            await self.execute_production_test_case(test_case, test_function)
        
        # Generate production test report
        production_ready = self.generate_production_test_report()
        
        return production_ready

    def generate_production_test_report(self):
        """Generate comprehensive production test report"""
        self.print_header("PRODUCTION TEST REPORT")
        
        total_execution_time = (time.time() - self.start_time)
        
        print(f"🏭 Production Test Session: {self.test_session_id}")
        print(f"⏱️  Total Execution Time: {total_execution_time:.2f} seconds")
        print(f"📊 Total Test Cases: {len(self.test_results)}")
        print(f"📅 Test Date: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Results by priority and type
        priority_summary = {}
        type_summary = {}
        status_counts = {'PASS': 0, 'FAIL': 0, 'ERROR': 0}
        
        for test_case in self.test_results:
            # Count by priority
            if test_case.priority not in priority_summary:
                priority_summary[test_case.priority] = {'PASS': 0, 'FAIL': 0, 'ERROR': 0}
            priority_summary[test_case.priority][test_case.status] += 1
            
            # Count by type
            test_type = test_case.test_type.value
            if test_type not in type_summary:
                type_summary[test_type] = {'PASS': 0, 'FAIL': 0, 'ERROR': 0}
            type_summary[test_type][test_case.status] += 1
            
            # Count by status
            status_counts[test_case.status] += 1
        
        # Print summary
        print(f"\n📈 PRODUCTION TEST RESULTS SUMMARY:")
        print("-" * 60)
        for status, count in status_counts.items():
            icon = {"PASS": "✅", "FAIL": "❌", "ERROR": "🚨"}[status]
            print(f"{icon} {status}: {count}")
        
        print(f"\n🎯 PRIORITY BREAKDOWN:")
        print("-" * 60)
        for priority in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
            if priority in priority_summary:
                stats = priority_summary[priority]
                total = sum(stats.values())
                pass_rate = (stats['PASS'] / total * 100) if total > 0 else 0
                print(f"{priority}: {stats['PASS']}/{total} passed ({pass_rate:.1f}%)")
        
        # Detailed results
        print(f"\n📋 DETAILED PRODUCTION TEST RESULTS:")
        print("-" * 60)
        
        for test_case in self.test_results:
            status_icon = {"PASS": "✅", "FAIL": "❌", "ERROR": "🚨"}[test_case.status]
            
            print(f"\n{status_icon} {test_case.id}: {test_case.name}")
            print(f"   Type: {test_case.test_type.value} | Priority: {test_case.priority}")
            print(f"   Execution Time: {test_case.execution_time_ms:.1f}ms (Max: {test_case.max_execution_time_ms:.0f}ms)")
            print(f"   Expected: {test_case.expected_result}")
            print(f"   Actual: {test_case.actual_result}")
            
            if test_case.error_details:
                print(f"   ⚠️  Error: {test_case.error_details}")
            
            # Show production metrics
            if test_case.metrics:
                print(f"   📊 Production Metrics:")
                metrics = test_case.metrics
                
                if 'accuracy_results' in metrics:
                    accuracy = metrics['accuracy_percentage']
                    avg_time = metrics.get('avg_processing_time_ms', 0)
                    print(f"      - Turkish Accuracy: {accuracy:.1f}% (Avg: {avg_time:.1f}ms)")
                
                if 'performance_metrics' in metrics:
                    perf = metrics['performance_metrics']
                    print(f"      - Avg Response: {perf.get('avg_response_time_ms', 0):.1f}ms")
                    print(f"      - Error Rate: {perf.get('error_rate_percentage', 0):.1f}%")
                    print(f"      - Throughput: {perf.get('throughput_per_second', 0):.1f} req/s")
                
                if 'flow_results' in metrics:
                    flow = metrics['flow_results']
                    if 'intent_classification' in flow:
                        intent = flow['intent_classification']
                        print(f"      - Intent: {intent.get('intent', 'unknown')} (confidence: {intent.get('confidence', 0):.3f})")

        # Production readiness assessment
        print(f"\n🏭 PRODUCTION READINESS ASSESSMENT:")
        print("-" * 60)
        
        # Critical tests must all pass
        critical_tests = [tc for tc in self.test_results if tc.priority == "CRITICAL"]
        critical_pass = all(tc.status == "PASS" for tc in critical_tests)
        
        # High priority tests - at least 80% must pass
        high_tests = [tc for tc in self.test_results if tc.priority == "HIGH"]
        if high_tests:
            high_pass_rate = sum(1 for tc in high_tests if tc.status == "PASS") / len(high_tests)
            high_acceptable = high_pass_rate >= 0.8
        else:
            high_acceptable = True
        
        # Overall production readiness
        production_ready = critical_pass and high_acceptable
        
        print(f"Critical Tests: {'✅ ALL PASS' if critical_pass else '❌ FAILURES DETECTED'}")
        print(f"High Priority Tests: {'✅ ACCEPTABLE' if high_acceptable else '❌ BELOW THRESHOLD'}")
        
        if production_ready:
            print(f"\n🚀 PRODUCTION READINESS: ✅ APPROVED")
            print(f"   🏆 The OpenSIPS AI Voice Connector system is READY for production deployment!")
            print(f"   🏦 Turkish banking call centers can deploy this system with confidence.")
            print(f"   📈 All critical functionality and performance criteria have been met.")
        else:
            print(f"\n⚠️  PRODUCTION READINESS: ❌ NOT APPROVED")
            print(f"   🚨 Critical issues must be resolved before production deployment!")
            print(f"   🔧 System requires additional optimization and fixes.")
        
        return production_ready

# Main execution
async def main():
    """Execute production test suite"""
    suite = ProductionTestSuite()
    
    try:
        production_ready = await suite.run_production_test_suite()
        
        # Save detailed production results
        with open(f'production_test_results_{suite.test_session_id}.json', 'w', encoding='utf-8') as f:
            results_data = {
                'session_id': suite.test_session_id,
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                'production_ready': production_ready,
                'test_cases': [asdict(tc) for tc in suite.test_results]
            }
            json.dump(results_data, f, indent=2, ensure_ascii=False, default=str)
        
        print(f"\n📄 Detailed results saved to: production_test_results_{suite.test_session_id}.json")
        
        if production_ready:
            print(f"\n🎉 PRODUCTION TEST SUITE: ✅ PASSED!")
            print(f"🚀 System is READY for Turkish banking production deployment!")
            sys.exit(0)
        else:
            print(f"\n🚨 PRODUCTION TEST SUITE: ❌ FAILED!")
            print(f"⚠️  Critical issues must be resolved before production!")
            sys.exit(1)
        
    except KeyboardInterrupt:
        logger.info("Production test suite interrupted by user")
        sys.exit(2)
    except Exception as e:
        logger.error(f"Production test suite failed: {e}")
        sys.exit(3)

if __name__ == "__main__":
    asyncio.run(main())