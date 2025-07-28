"""
Intent Recognition gRPC Client
Provides interface to Intent Recognition service for IVR automation
"""

import asyncio
import logging
import time
from typing import Dict, Any, List, Optional, Tuple

import grpc
from grpc import aio as aio_grpc

# Import generated protobuf code
try:
    from ..grpc_clients import intent_service_pb2, intent_service_pb2_grpc
except ImportError:
    # Fallback for testing
    import sys
    from pathlib import Path
    shared_path = Path(__file__).parent.parent.parent / "shared" / "proto_generated"
    sys.path.append(str(shared_path))
    import intent_service_pb2
    import intent_service_pb2_grpc

from google.protobuf.empty_pb2 import Empty

logger = logging.getLogger(__name__)


class IntentClient:
    """gRPC client for Intent Recognition service"""
    
    def __init__(self, service_registry=None, service_url: str = None):
        """Initialize Intent Recognition client"""
        self.service_registry = service_registry
        self.service_url = service_url or "localhost:50054"
        self.channel: Optional[aio_grpc.Channel] = None
        self.stub: Optional[intent_service_pb2_grpc.IntentRecognitionStub] = None
        self.is_connected = False
        
        # Client statistics
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.total_processing_time = 0.0
        
        logger.info("Intent Recognition client initialized", service_url=self.service_url)
    
    async def connect(self) -> bool:
        """Connect to Intent Recognition service"""
        try:
            if self.is_connected:
                return True
            
            # Get service URL from registry if available
            if self.service_registry:
                service_url = await self.service_registry.get_service_url("intent")
                if service_url:
                    self.service_url = service_url
            
            # Create gRPC channel
            self.channel = aio_grpc.insecure_channel(self.service_url)
            self.stub = intent_service_pb2_grpc.IntentRecognitionStub(self.channel)
            
            # Test connection with health check
            health_request = Empty()
            response = await self.stub.HealthCheck(health_request, timeout=5.0)
            
            if response.status == intent_service_pb2.HealthResponse.SERVING:
                self.is_connected = True
                logger.info("Connected to Intent Recognition service", 
                          service_url=self.service_url,
                          model_version=response.model_version,
                          supported_intents=response.supported_intents_count)
                return True
            else:
                logger.error("Intent service not serving", status=response.status)
                return False
                
        except Exception as e:
            logger.error("Failed to connect to Intent Recognition service", 
                        service_url=self.service_url, error=str(e))
            return False
    
    async def disconnect(self):
        """Disconnect from Intent Recognition service"""
        try:
            if self.channel:
                await self.channel.close()
            self.is_connected = False
            self.channel = None
            self.stub = None
            logger.info("Disconnected from Intent Recognition service")
            
        except Exception as e:
            logger.error("Error disconnecting from Intent service", error=str(e))
    
    async def classify_intent(self, 
                            text: str, 
                            confidence_threshold: float = 0.85,
                            candidate_intents: List[str] = None,
                            session_id: str = None) -> Dict[str, Any]:
        """
        Classify text into intent category
        
        Args:
            text: Text to classify
            confidence_threshold: Minimum confidence threshold
            candidate_intents: Optional list of candidate intents to limit classification
            session_id: Optional session identifier
            
        Returns:
            Dictionary with classification results
        """
        start_time = time.time()
        
        try:
            if not self.is_connected:
                if not await self.connect():
                    return self._create_error_result("Not connected to service", start_time)
            
            # Create request
            request = intent_service_pb2.ClassifyIntentRequest()
            request.text = text
            request.confidence_threshold = confidence_threshold
            if candidate_intents:
                request.candidate_intents.extend(candidate_intents)
            if session_id:
                request.session_id = session_id
            
            # Make gRPC call
            response = await self.stub.ClassifyIntent(request, timeout=10.0)
            
            processing_time = (time.time() - start_time) * 1000
            
            # Update statistics
            self.total_requests += 1
            self.total_processing_time += processing_time
            
            if response.meets_threshold:
                self.successful_requests += 1
            else:
                self.failed_requests += 1
            
            # Convert response to dictionary
            result = {
                "intent": response.intent,
                "confidence": response.confidence,
                "meets_threshold": response.meets_threshold,
                "alternatives": [
                    {
                        "intent": alt.intent,
                        "confidence": alt.confidence
                    }
                    for alt in response.alternative_intents
                ],
                "processing_time_ms": processing_time,
                "token_count": response.metrics.token_count,
                "model_version": response.metrics.model_version,
                "service_processing_time_ms": response.metrics.processing_time_ms
            }
            
            logger.debug("Intent classification completed",
                        text=text,
                        intent=result["intent"],
                        confidence=result["confidence"],
                        processing_time_ms=processing_time)
            
            return result
            
        except grpc.RpcError as e:
            processing_time = (time.time() - start_time) * 1000
            self.failed_requests += 1
            logger.error("gRPC error during intent classification",
                        text=text, error=str(e), code=e.code())
            return self._create_error_result(f"gRPC error: {e.code()}", start_time)
            
        except Exception as e:
            processing_time = (time.time() - start_time) * 1000
            self.failed_requests += 1
            logger.error("Error during intent classification", text=text, error=str(e))
            return self._create_error_result(str(e), start_time)
    
    async def classify_intent_batch(self, 
                                  texts: List[str], 
                                  confidence_threshold: float = 0.85) -> List[Dict[str, Any]]:
        """
        Classify multiple texts in batch
        
        Args:
            texts: List of texts to classify
            confidence_threshold: Minimum confidence threshold
            
        Returns:
            List of classification results
        """
        start_time = time.time()
        
        try:
            if not self.is_connected:
                if not await self.connect():
                    return [self._create_error_result("Not connected to service", start_time) 
                           for _ in texts]
            
            # Create batch request
            request = intent_service_pb2.ClassifyIntentBatchRequest()
            for i, text in enumerate(texts):
                req = request.requests.add()
                req.text = text
                req.confidence_threshold = confidence_threshold
                req.session_id = f"batch_{int(time.time())}_{i}"
            
            # Make gRPC call
            response = await self.stub.ClassifyIntentBatch(request, timeout=30.0)
            
            total_time = (time.time() - start_time) * 1000
            
            # Update statistics
            self.total_requests += len(texts)
            self.total_processing_time += total_time
            self.successful_requests += response.batch_metrics.successful_classifications
            self.failed_requests += response.batch_metrics.failed_classifications
            
            # Convert responses to dictionaries
            results = []
            for resp in response.responses:
                result = {
                    "intent": resp.intent,
                    "confidence": resp.confidence,
                    "meets_threshold": resp.meets_threshold,
                    "alternatives": [
                        {
                            "intent": alt.intent,
                            "confidence": alt.confidence
                        }
                        for alt in resp.alternative_intents
                    ],
                    "processing_time_ms": resp.metrics.processing_time_ms,
                    "token_count": resp.metrics.token_count,
                    "model_version": resp.metrics.model_version
                }
                results.append(result)
            
            logger.debug("Batch intent classification completed",
                        batch_size=len(texts),
                        successful=response.batch_metrics.successful_classifications,
                        failed=response.batch_metrics.failed_classifications,
                        total_time_ms=total_time)
            
            return results
            
        except Exception as e:
            self.failed_requests += len(texts)
            logger.error("Error during batch intent classification", 
                        batch_size=len(texts), error=str(e))
            return [self._create_error_result(str(e), start_time) for _ in texts]
    
    async def get_supported_intents(self) -> List[Dict[str, Any]]:
        """Get list of supported intents"""
        try:
            if not self.is_connected:
                if not await self.connect():
                    return []
            
            request = Empty()
            response = await self.stub.GetSupportedIntents(request, timeout=5.0)
            
            intents = []
            for intent_info in response.supported_intents:
                intents.append({
                    "intent_label": intent_info.intent_label,
                    "display_name": intent_info.display_name,
                    "description": intent_info.description,
                    "default_threshold": intent_info.default_threshold,
                    "example_phrases": list(intent_info.example_phrases),
                    "training_sample_count": intent_info.training_sample_count
                })
            
            logger.debug("Retrieved supported intents", count=len(intents))
            return intents
            
        except Exception as e:
            logger.error("Error getting supported intents", error=str(e))
            return []
    
    async def health_check(self) -> bool:
        """Check service health"""
        try:
            if not self.is_connected:
                if not await self.connect():
                    return False
            
            request = Empty()
            response = await self.stub.HealthCheck(request, timeout=5.0)
            
            is_healthy = response.status == intent_service_pb2.HealthResponse.SERVING
            logger.debug("Intent service health check", healthy=is_healthy)
            return is_healthy
            
        except Exception as e:
            logger.error("Intent service health check failed", error=str(e))
            return False
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get service statistics"""
        try:
            if not self.is_connected:
                if not await self.connect():
                    return {}
            
            request = Empty()
            response = await self.stub.GetStats(request, timeout=5.0)
            
            stats = {
                "total_classifications": response.total_classifications,
                "successful_classifications": response.successful_classifications,
                "failed_classifications": response.failed_classifications,
                "average_processing_time_ms": response.average_processing_time_ms,
                "average_confidence": response.average_confidence,
                "uptime_seconds": response.uptime_seconds,
                "model_version": response.model_version,
                "active_sessions": response.active_sessions,
                "intent_usage_count": dict(response.intent_usage_count)
            }
            
            return stats
            
        except Exception as e:
            logger.error("Error getting intent service stats", error=str(e))
            return {}
    
    def _create_error_result(self, error_message: str, start_time: float) -> Dict[str, Any]:
        """Create error result dictionary"""
        processing_time = (time.time() - start_time) * 1000
        return {
            "intent": "unknown",
            "confidence": 0.0,
            "meets_threshold": False,
            "alternatives": [],
            "processing_time_ms": processing_time,
            "token_count": 0,
            "model_version": "unknown",
            "service_processing_time_ms": 0.0,
            "error": error_message
        }
    
    def get_client_stats(self) -> Dict[str, Any]:
        """Get client-side statistics"""
        avg_processing_time = (self.total_processing_time / self.total_requests 
                             if self.total_requests > 0 else 0.0)
        
        return {
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "average_processing_time_ms": avg_processing_time,
            "is_connected": self.is_connected,
            "service_url": self.service_url
        }


class IntentRecognitionManager:
    """High-level manager for intent recognition operations"""
    
    def __init__(self, service_registry=None, service_url: str = None):
        """Initialize Intent Recognition manager"""
        self.client = IntentClient(service_registry, service_url)
        self.default_threshold = 0.85
        self.supported_intents_cache = None
        self.cache_expiry = 0
        
    async def initialize(self):
        """Initialize the manager and connect to service"""
        success = await self.client.connect()
        if success:
            # Cache supported intents
            await self._refresh_supported_intents()
        return success
    
    async def classify_ivr_response(self, 
                                  response_text: str, 
                                  expected_intent: str = None,
                                  confidence_threshold: float = None) -> Dict[str, Any]:
        """
        Classify IVR response text for test automation
        
        Args:
            response_text: IVR response text to classify
            expected_intent: Expected intent for validation
            confidence_threshold: Override default threshold
            
        Returns:
            Classification result with validation info
        """
        threshold = confidence_threshold or self.default_threshold
        
        result = await self.client.classify_intent(
            text=response_text,
            confidence_threshold=threshold
        )
        
        # Add validation information
        if expected_intent:
            result["expected_intent"] = expected_intent
            result["intent_matches"] = result["intent"] == expected_intent
            result["validation_passed"] = (result["intent_matches"] and 
                                         result["meets_threshold"])
        
        return result
    
    async def validate_intent_sequence(self, 
                                     text_intent_pairs: List[Tuple[str, str]],
                                     confidence_threshold: float = None) -> Dict[str, Any]:
        """
        Validate a sequence of text-intent pairs for IVR flow testing
        
        Args:
            text_intent_pairs: List of (text, expected_intent) tuples
            confidence_threshold: Override default threshold
            
        Returns:
            Validation results for the sequence
        """
        threshold = confidence_threshold or self.default_threshold
        texts = [pair[0] for pair in text_intent_pairs]
        expected_intents = [pair[1] for pair in text_intent_pairs]
        
        # Classify all texts in batch
        results = await self.client.classify_intent_batch(texts, threshold)
        
        # Validate results
        validation_results = []
        correct_count = 0
        
        for i, (result, expected) in enumerate(zip(results, expected_intents)):
            intent_matches = result["intent"] == expected
            validation_passed = intent_matches and result["meets_threshold"]
            
            if validation_passed:
                correct_count += 1
            
            validation_results.append({
                "text": texts[i],
                "expected_intent": expected,
                "predicted_intent": result["intent"],
                "confidence": result["confidence"],
                "intent_matches": intent_matches,
                "meets_threshold": result["meets_threshold"],
                "validation_passed": validation_passed
            })
        
        return {
            "sequence_results": validation_results,
            "total_items": len(text_intent_pairs),
            "correct_predictions": correct_count,
            "accuracy": correct_count / len(text_intent_pairs) if text_intent_pairs else 0.0,
            "validation_passed": correct_count == len(text_intent_pairs)
        }
    
    async def get_supported_intents(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Get supported intents with caching"""
        current_time = time.time()
        
        if (force_refresh or 
            self.supported_intents_cache is None or 
            current_time > self.cache_expiry):
            await self._refresh_supported_intents()
        
        return self.supported_intents_cache or []
    
    async def _refresh_supported_intents(self):
        """Refresh supported intents cache"""
        try:
            self.supported_intents_cache = await self.client.get_supported_intents()
            self.cache_expiry = time.time() + 300  # Cache for 5 minutes
        except Exception as e:
            logger.error("Failed to refresh supported intents", error=str(e))
    
    async def cleanup(self):
        """Clean up resources"""
        await self.client.disconnect()