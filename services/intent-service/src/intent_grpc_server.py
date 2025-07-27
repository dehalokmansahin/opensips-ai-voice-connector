"""
Intent Recognition Service - gRPC Server Implementation
Foundation for Turkish BERT intent classification
"""

import asyncio
import time
import logging
from typing import Dict, Any, List, Optional
from concurrent import futures

import structlog
import grpc
from grpc import aio as aio_grpc

# Generated gRPC code
try:
    from . import intent_service_pb2
    from . import intent_service_pb2_grpc
except ImportError:
    # Fallback for development
    import intent_service_pb2
    import intent_service_pb2_grpc

# Setup structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)


class MockIntentClassifier:
    """Mock intent classifier for foundation implementation"""
    
    def __init__(self):
        self.model_version = "foundation-mock-v1.0"
        self.supported_intents = {
            "account_balance_inquiry": {
                "display_name": "Hesap Bakiye Sorgulama",
                "description": "Hesap bakiyesi öğrenme isteği",
                "default_threshold": 0.85,
                "examples": [
                    "hesap bakiyemi öğrenmek istiyorum",
                    "bakiyemi kontrol etmek istiyorum",
                    "hesabımda ne kadar param var"
                ]
            },
            "customer_service_request": {
                "display_name": "Müşteri Hizmetleri",
                "description": "Müşteri hizmetleriyle görüşme isteği",
                "default_threshold": 0.80,
                "examples": [
                    "müşteri hizmetleriyle konuşmak istiyorum",
                    "temsilciyle görüşmek istiyorum",
                    "operatöre bağlanmak istiyorum"
                ]
            },
            "balance_menu": {
                "display_name": "Bakiye Menüsü",
                "description": "Bakiye menüsü yanıtı",
                "default_threshold": 0.90,
                "examples": [
                    "hesap bakiyeniz",
                    "mevcut bakiye",
                    "kullanılabilir bakiye"
                ]
            },
            "agent_transfer": {
                "display_name": "Temsilci Aktarımı",
                "description": "Temsilciye aktarım onayı",
                "default_threshold": 0.85,
                "examples": [
                    "size aktarıyorum",
                    "temsilcimize bağlanıyorsunuz",
                    "lütfen bekleyiniz"
                ]
            },
            "unknown": {
                "display_name": "Bilinmeyen",
                "description": "Tanımlanamayan intent",
                "default_threshold": 0.50,
                "examples": []
            }
        }
        
        # Statistics
        self.total_classifications = 0
        self.successful_classifications = 0
        self.failed_classifications = 0
        self.total_processing_time = 0.0
        self.intent_usage_count = {intent: 0 for intent in self.supported_intents.keys()}
        self.start_time = time.time()
        
    def classify_text(self, text: str, confidence_threshold: float = 0.85, 
                     candidate_intents: List[str] = None) -> Dict[str, Any]:
        """Mock classification - will be replaced with external intent service in production"""
        start_time = time.time()
        
        try:
            text_lower = text.lower().strip()
            
            # Simple keyword-based classification for foundation (handles both Turkish and ASCII)
            if any(keyword in text_lower for keyword in ["bakiye", "hesap", "para"]):
                intent = "account_balance_inquiry"
                confidence = 0.92
            elif any(keyword in text_lower for keyword in ["müşteri", "musteri", "temsilci", "operatör", "operator", "insan"]):
                intent = "customer_service_request"
                confidence = 0.88
            elif any(keyword in text_lower for keyword in ["bakiyeniz", "mevcut", "kullanılabilir", "kullanilabilir"]):
                intent = "balance_menu"
                confidence = 0.95
            elif any(keyword in text_lower for keyword in ["aktarıyorum", "aktariyorum", "bağlanıyorsunuz", "baglaniyorsunuz", "bekleyiniz"]):
                intent = "agent_transfer"
                confidence = 0.89
            else:
                intent = "unknown"
                confidence = 0.30
            
            # Filter by candidate intents if provided
            if candidate_intents and intent not in candidate_intents:
                intent = "unknown"
                confidence = 0.25
            
            # Generate alternative intents
            alternatives = []
            for alt_intent, alt_info in self.supported_intents.items():
                if alt_intent != intent and alt_intent != "unknown":
                    alt_confidence = max(0.1, confidence - 0.3 + (0.1 * hash(alt_intent + text) % 3))
                    alternatives.append({
                        "intent": alt_intent,
                        "confidence": min(0.99, alt_confidence)
                    })
            
            # Sort alternatives by confidence
            alternatives.sort(key=lambda x: x["confidence"], reverse=True)
            alternatives = alternatives[:3]  # Top 3 alternatives
            
            processing_time = (time.time() - start_time) * 1000
            
            # Update statistics
            self.total_classifications += 1
            self.total_processing_time += processing_time
            self.intent_usage_count[intent] += 1
            
            if confidence >= confidence_threshold:
                self.successful_classifications += 1
            else:
                self.failed_classifications += 1
            
            return {
                "intent": intent,
                "confidence": confidence,
                "meets_threshold": confidence >= confidence_threshold,
                "alternatives": alternatives,
                "processing_time_ms": processing_time,
                "token_count": len(text.split()),
                "model_version": self.model_version
            }
            
        except Exception as e:
            processing_time = (time.time() - start_time) * 1000
            self.failed_classifications += 1
            logger.error("Classification failed", text=text, error=str(e))
            
            return {
                "intent": "unknown",
                "confidence": 0.0,
                "meets_threshold": False,
                "alternatives": [],
                "processing_time_ms": processing_time,
                "token_count": 0,
                "model_version": self.model_version,
                "error": str(e)
            }


class IntentRecognitionServiceImpl(intent_service_pb2_grpc.IntentRecognitionServicer):
    """Intent Recognition Service gRPC implementation"""
    
    def __init__(self):
        self.classifier = MockIntentClassifier()
        self.active_sessions = set()
        logger.info("Intent Recognition Service initialized", model_version=self.classifier.model_version)
    
    async def ClassifyIntent(self, request, context):
        """Classify single text input"""
        try:
            session_id = request.session_id or f"session_{int(time.time() * 1000)}"
            self.active_sessions.add(session_id)
            
            logger.debug("Processing intent classification",
                        session_id=session_id,
                        text=request.text,
                        threshold=request.confidence_threshold)
            
            # Use default threshold if not provided
            threshold = request.confidence_threshold if request.confidence_threshold > 0 else 0.85
            candidate_intents = list(request.candidate_intents) if request.candidate_intents else None
            
            # Classify using mock classifier
            result = self.classifier.classify_text(
                text=request.text,
                confidence_threshold=threshold,
                candidate_intents=candidate_intents
            )
            
            # Build response
            response = intent_service_pb2.ClassifyIntentResponse()
            response.intent = result["intent"]
            response.confidence = result["confidence"]
            response.meets_threshold = result["meets_threshold"]
            
            # Add alternative intents
            for alt in result["alternatives"]:
                alt_score = response.alternative_intents.add()
                alt_score.intent = alt["intent"]
                alt_score.confidence = alt["confidence"]
            
            # Add metrics
            response.metrics.processing_time_ms = result["processing_time_ms"]
            response.metrics.token_count = result["token_count"]
            response.metrics.model_version = result["model_version"]
            
            logger.info("Intent classification completed",
                       session_id=session_id,
                       intent=result["intent"],
                       confidence=result["confidence"],
                       meets_threshold=result["meets_threshold"],
                       processing_time_ms=result["processing_time_ms"])
            
            return response
            
        except Exception as e:
            logger.error("Intent classification failed", session_id=session_id, error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Classification failed: {str(e)}")
            return intent_service_pb2.ClassifyIntentResponse()
    
    async def ClassifyIntentBatch(self, request, context):
        """Classify multiple texts in batch"""
        try:
            start_time = time.time()
            responses = []
            successful = 0
            failed = 0
            
            logger.debug("Processing batch classification", batch_size=len(request.requests))
            
            for req in request.requests:
                single_response = await self.ClassifyIntent(req, context)
                responses.append(single_response)
                
                if single_response.meets_threshold:
                    successful += 1
                else:
                    failed += 1
            
            total_time = (time.time() - start_time) * 1000
            avg_time = total_time / len(request.requests) if request.requests else 0
            
            # Build batch response
            batch_response = intent_service_pb2.ClassifyIntentBatchResponse()
            batch_response.responses.extend(responses)
            
            # Add batch metrics
            batch_response.batch_metrics.total_processing_time_ms = total_time
            batch_response.batch_metrics.successful_classifications = successful
            batch_response.batch_metrics.failed_classifications = failed
            batch_response.batch_metrics.average_processing_time_ms = avg_time
            
            logger.info("Batch classification completed",
                       batch_size=len(request.requests),
                       successful=successful,
                       failed=failed,
                       total_time_ms=total_time)
            
            return batch_response
            
        except Exception as e:
            logger.error("Batch classification failed", error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Batch classification failed: {str(e)}")
            return intent_service_pb2.ClassifyIntentBatchResponse()
    
    async def GetSupportedIntents(self, request, context):
        """Get list of supported intents"""
        try:
            response = intent_service_pb2.GetSupportedIntentsResponse()
            response.total_count = len(self.classifier.supported_intents)
            response.model_version = self.classifier.model_version
            
            for intent_key, intent_info in self.classifier.supported_intents.items():
                intent_pb = response.supported_intents.add()
                intent_pb.intent_label = intent_key
                intent_pb.display_name = intent_info["display_name"]
                intent_pb.description = intent_info["description"]
                intent_pb.default_threshold = intent_info["default_threshold"]
                intent_pb.example_phrases.extend(intent_info["examples"])
                intent_pb.training_sample_count = len(intent_info["examples"])
            
            logger.debug("Supported intents requested", count=response.total_count)
            return response
            
        except Exception as e:
            logger.error("Get supported intents failed", error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Failed to get supported intents: {str(e)}")
            return intent_service_pb2.GetSupportedIntentsResponse()
    
    async def UpdateTrainingData(self, request, context):
        """Update training data (placeholder for Epic 2.1)"""
        try:
            logger.info("Training data update requested",
                       examples_count=len(request.examples),
                       retrain_immediately=request.retrain_immediately,
                       source=request.update_source)
            
            response = intent_service_pb2.UpdateTrainingDataResponse()
            response.success = True
            response.message = "Training data update received (will be implemented in Epic 2.1)"
            response.examples_added = len(request.examples)
            response.model_retrained = False  # Not implemented yet
            response.new_model_version = self.classifier.model_version
            
            return response
            
        except Exception as e:
            logger.error("Training data update failed", error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Training data update failed: {str(e)}")
            return intent_service_pb2.UpdateTrainingDataResponse()
    
    async def HealthCheck(self, request, context):
        """Health check implementation"""
        try:
            response = intent_service_pb2.HealthResponse()
            response.status = intent_service_pb2.HealthResponse.SERVING
            response.message = "Intent Recognition Service operational (foundation)"
            response.model_version = self.classifier.model_version
            response.supported_intents_count = len(self.classifier.supported_intents)
            response.model_load_time_ms = 100.0  # Mock load time
            
            logger.debug("Health check passed")
            return response
            
        except Exception as e:
            logger.error("Health check failed", error=str(e))
            response = intent_service_pb2.HealthResponse()
            response.status = intent_service_pb2.HealthResponse.NOT_SERVING
            response.message = f"Health check failed: {str(e)}"
            return response
    
    async def GetStats(self, request, context):
        """Get service statistics"""
        try:
            uptime = time.time() - self.classifier.start_time
            avg_processing_time = (self.classifier.total_processing_time / 
                                 self.classifier.total_classifications 
                                 if self.classifier.total_classifications > 0 else 0.0)
            
            avg_confidence = 0.85  # Mock average confidence
            
            response = intent_service_pb2.StatsResponse()
            response.total_classifications = self.classifier.total_classifications
            response.successful_classifications = self.classifier.successful_classifications
            response.failed_classifications = self.classifier.failed_classifications
            response.average_processing_time_ms = avg_processing_time
            response.average_confidence = avg_confidence
            response.uptime_seconds = int(uptime)
            response.model_version = self.classifier.model_version
            response.active_sessions = len(self.active_sessions)
            
            # Add intent usage counts
            for intent, count in self.classifier.intent_usage_count.items():
                response.intent_usage_count[intent] = count
            
            logger.debug("Service stats requested", uptime_seconds=int(uptime))
            return response
            
        except Exception as e:
            logger.error("Get stats failed", error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Failed to get stats: {str(e)}")
            return intent_service_pb2.StatsResponse()


async def serve():
    """Start the Intent Recognition gRPC server"""
    server = aio_grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    
    # Add Intent Recognition service
    intent_service_pb2_grpc.add_IntentRecognitionServicer_to_server(
        IntentRecognitionServiceImpl(), server
    )
    
    # Configure server
    listen_addr = '[::]:50054'
    server.add_insecure_port(listen_addr)
    
    # Start server
    await server.start()
    logger.info("Intent Recognition Service started", 
               address=listen_addr, 
               model="foundation-mock",
               supported_intents=5)
    
    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Intent Recognition Service shutting down")
        await server.stop(grace=30)


if __name__ == '__main__':
    asyncio.run(serve())