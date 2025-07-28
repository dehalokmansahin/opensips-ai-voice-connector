"""
Intent Recognition REST Client
Provides interface to Intent Recognition REST API service for IVR automation
"""

import asyncio
import logging
import time
import aiohttp
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

class IntentRESTClient:
    """REST client for Intent Recognition service"""
    
    def __init__(self, service_url: str = None):
        """Initialize Intent Recognition REST client"""
        self.service_url = service_url or "http://localhost:5000"
        self.session: Optional[aiohttp.ClientSession] = None
        self.is_connected = False
        
        # Client statistics
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.total_processing_time = 0.0
        
        logger.info(f"Intent Recognition REST client initialized: {self.service_url}")
    
    async def connect(self) -> bool:
        """Connect to Intent Recognition service"""
        try:
            if self.is_connected:
                return True
            
            # Create aiohttp session
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(timeout=timeout)
            
            # Test connection with health check
            async with self.session.get(f"{self.service_url}/health") as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("status") == "SERVING":
                        self.is_connected = True
                        logger.info(f"Connected to Intent Recognition service: {self.service_url}")
                        logger.info(f"Model version: {data.get('model_version')}")
                        logger.info(f"Supported intents: {data.get('supported_intents_count')}")
                        return True
                
            logger.error("Intent service not healthy")
            return False
                
        except Exception as e:
            logger.error(f"Failed to connect to Intent Recognition service: {e}")
            return False
    
    async def disconnect(self):
        """Disconnect from Intent Recognition service"""
        try:
            if self.session:
                await self.session.close()
            self.is_connected = False
            self.session = None
            logger.info("Disconnected from Intent Recognition service")
            
        except Exception as e:
            logger.error(f"Error disconnecting from Intent service: {e}")
    
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
            
            # Create request payload
            payload = {
                "text": text,
                "confidence_threshold": confidence_threshold
            }
            if candidate_intents:
                payload["candidate_intents"] = candidate_intents
            if session_id:
                payload["session_id"] = session_id
            
            # Make HTTP request
            async with self.session.post(f"{self.service_url}/classify", json=payload) as response:
                if response.status == 200:
                    result = await response.json()
                    
                    processing_time = (time.time() - start_time) * 1000
                    
                    # Update statistics
                    self.total_requests += 1
                    self.total_processing_time += processing_time
                    
                    if result.get("meets_threshold", False):
                        self.successful_requests += 1
                    else:
                        self.failed_requests += 1
                    
                    # Add client processing time
                    result["client_processing_time_ms"] = processing_time
                    
                    logger.debug(f"Intent classification completed: {text[:50]}... -> {result['intent']} ({result['confidence']:.2f})")
                    
                    return result
                else:
                    error_text = await response.text()
                    logger.error(f"HTTP error {response.status}: {error_text}")
                    self.failed_requests += 1
                    return self._create_error_result(f"HTTP {response.status}: {error_text}", start_time)
                    
        except asyncio.TimeoutError:
            self.failed_requests += 1
            logger.error(f"Request timeout for text: {text[:50]}...")
            return self._create_error_result("Request timeout", start_time)
            
        except Exception as e:
            self.failed_requests += 1
            logger.error(f"Error during intent classification: {e}")
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
            
            # Create batch request payload
            payload = {
                "requests": [
                    {
                        "text": text,
                        "confidence_threshold": confidence_threshold
                    }
                    for text in texts
                ]
            }
            
            # Make HTTP request
            async with self.session.post(f"{self.service_url}/classify/batch", json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    results = data.get("responses", [])
                    
                    total_time = (time.time() - start_time) * 1000
                    
                    # Update statistics
                    self.total_requests += len(texts)
                    self.total_processing_time += total_time
                    
                    batch_metrics = data.get("batch_metrics", {})
                    self.successful_requests += batch_metrics.get("successful_classifications", 0)
                    self.failed_requests += batch_metrics.get("failed_classifications", 0)
                    
                    logger.debug(f"Batch intent classification completed: {len(texts)} texts")
                    
                    return results
                else:
                    error_text = await response.text()
                    logger.error(f"Batch HTTP error {response.status}: {error_text}")
                    self.failed_requests += len(texts)
                    return [self._create_error_result(f"HTTP {response.status}", start_time) for _ in texts]
                    
        except Exception as e:
            self.failed_requests += len(texts)
            logger.error(f"Error during batch intent classification: {e}")
            return [self._create_error_result(str(e), start_time) for _ in texts]
    
    async def get_supported_intents(self) -> List[Dict[str, Any]]:
        """Get list of supported intents"""
        try:
            if not self.is_connected:
                if not await self.connect():
                    return []
            
            async with self.session.get(f"{self.service_url}/intents") as response:
                if response.status == 200:
                    data = await response.json()
                    intents = data.get("supported_intents", [])
                    logger.debug(f"Retrieved {len(intents)} supported intents")
                    return intents
                else:
                    logger.error(f"Failed to get supported intents: HTTP {response.status}")
                    return []
                    
        except Exception as e:
            logger.error(f"Error getting supported intents: {e}")
            return []
    
    async def health_check(self) -> bool:
        """Check service health"""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            async with self.session.get(f"{self.service_url}/health") as response:
                if response.status == 200:
                    data = await response.json()
                    is_healthy = data.get("status") == "SERVING"
                    logger.debug(f"Intent service health check: {is_healthy}")
                    return is_healthy
                else:
                    logger.error(f"Health check failed: HTTP {response.status}")
                    return False
                    
        except Exception as e:
            logger.error(f"Intent service health check failed: {e}")
            return False
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get service statistics"""
        try:
            if not self.is_connected:
                if not await self.connect():
                    return {}
            
            async with self.session.get(f"{self.service_url}/stats") as response:
                if response.status == 200:
                    stats = await response.json()
                    return stats
                else:
                    logger.error(f"Failed to get stats: HTTP {response.status}")
                    return {}
                    
        except Exception as e:
            logger.error(f"Error getting intent service stats: {e}")
            return {}
    
    def _create_error_result(self, error_message: str, start_time: float) -> Dict[str, Any]:
        """Create error result dictionary"""
        processing_time = (time.time() - start_time) * 1000
        return {
            "intent": "bilinmeyen",
            "confidence": 0.0,
            "meets_threshold": False,
            "alternatives": [],
            "processing_time_ms": processing_time,
            "token_count": 0,
            "model_version": "unknown",
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
    
    def __init__(self, service_url: str = None):
        """Initialize Intent Recognition manager"""
        self.client = IntentRESTClient(service_url)
        self.default_threshold = 0.80  # Turkish bank scenarios threshold
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
            logger.error(f"Failed to refresh supported intents: {e}")
    
    async def cleanup(self):
        """Clean up resources"""
        await self.client.disconnect()


# Wrapper to maintain compatibility
IntentClient = IntentRESTClient