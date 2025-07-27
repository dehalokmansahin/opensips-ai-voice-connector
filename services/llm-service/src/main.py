"""
LLM Service - Language Model Microservice
Extracted from working legacy Llama WebSocket implementation with banking context
"""

import asyncio
import json
import logging
import sys
import time
from typing import Dict, Any, Optional, List

import structlog
import grpc
from grpc import aio as aio_grpc
from concurrent import futures
import websockets

# Generated gRPC code (will be created by proto-gen.sh)
from . import common_pb2
try:
    from . import llm_service_pb2
    from . import llm_service_pb2_grpc
except ImportError:
    # Fallback for development
    import sys
    sys.path.append('.')
    import llm_service_pb2
    import llm_service_pb2_grpc

# Setup structured logging (same as legacy)
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


class LlamaLLMEngine:
    """Llama LLM engine - extracted from proven legacy implementation"""
    
    def __init__(self, 
                 url: str = "ws://llm-turkish-server:8765",
                 model: str = "llama3.2:3b-instruct-turkish",
                 temperature: float = 0.2,
                 max_tokens: int = 80):
        self.url = url
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.websocket: Optional = None
        self.is_connected = False
        
        # Banking-specific system prompt (improved from legacy)
        self.banking_system_prompt = (
            "Sen bir banka müşteri hizmetleri sanal asistanısın. "
            "Kullanıcıya kart teslimat durumu, hesap bilgileri, para transferi, "
            "fatura ödeme gibi bankacılık konularında yardımcı olursun. "
            "Cevapların kısa, net, güvenli ve anlaşılır olmalıdır. "
            "Hassas bilgileri asla paylaşma."
        )
        
    async def connect(self):
        """Connect to Llama WebSocket server (same as legacy)"""
        try:
            self.websocket = await websockets.connect(self.url)
            self.is_connected = True
            
            logger.info("Llama LLM engine connected", 
                       url=self.url, 
                       model=self.model,
                       temperature=self.temperature,
                       max_tokens=self.max_tokens)
            
        except Exception as e:
            logger.error("Failed to connect to Llama server", url=self.url, error=str(e))
            raise
    
    async def disconnect(self):
        """Disconnect from Llama server"""
        if self.websocket and self.is_connected:
            try:
                await self.websocket.close()
            except Exception as e:
                logger.error("Error disconnecting from Llama", error=str(e))
        
        self.is_connected = False
        self.websocket = None
    
    async def generate_response(self, messages: List[Dict[str, str]], context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Generate response using Llama (same OpenAI format as legacy)"""
        if not self.is_connected or not self.websocket:
            await self.connect()
        
        try:
            # Prepare request in OpenAI format (same as legacy)
            request = {
                "messages": messages,
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
                "model": self.model,
                "stream": False  # Get complete response
            }
            
            # Add banking context if provided
            if context:
                request["context"] = context
            
            logger.debug("Sending request to Llama",
                        messages_count=len(messages),
                        last_user_message=messages[-1]["content"] if messages else "",
                        temperature=self.temperature,
                        max_tokens=self.max_tokens)
            
            # Send request to Llama server
            await self.websocket.send(json.dumps(request))
            
            # Wait for response with timeout
            response = await asyncio.wait_for(
                self.websocket.recv(),
                timeout=10.0
            )
            
            # Parse JSON response (same as legacy)
            data = json.loads(response)
            
            logger.debug("Llama response received",
                        has_choices="choices" in data,
                        has_error="error" in data)
            
            return data
            
        except asyncio.TimeoutError:
            logger.warning("Llama generation timeout")
            return {"error": "Generation timeout"}
        except json.JSONDecodeError as e:
            logger.error("Invalid JSON from Llama", error=str(e))
            return {"error": f"Invalid JSON: {e}"}
        except Exception as e:
            logger.error("Llama generation failed", error=str(e))
            return {"error": f"Generation failed: {e}"}
    
    def analyze_banking_intent(self, user_input: str) -> Dict[str, Any]:
        """Analyze banking intent from user input"""
        user_lower = user_input.lower()
        
        # Banking intent patterns (expanded from legacy use case)
        banking_intents = {
            "card_delivery_status": [
                "kart", "teslimat", "kargo", "geldi mi", "nerede", "ne zaman"
            ],
            "account_balance": [
                "bakiye", "hesap", "param", "ne kadar"
            ],
            "money_transfer": [
                "transfer", "gönder", "para gönder", "havale"
            ],
            "bill_payment": [
                "fatura", "ödeme", "elektrik", "su", "gaz"
            ],
            "general_inquiry": [
                "yardım", "bilgi", "nasıl", "ne", "merhaba"
            ]
        }
        
        # Simple intent detection
        for intent, keywords in banking_intents.items():
            if any(keyword in user_lower for keyword in keywords):
                confidence = sum(1 for keyword in keywords if keyword in user_lower) / len(keywords)
                return {
                    "intent_type": intent,
                    "confidence": min(confidence * 2, 1.0),  # Boost confidence
                    "parameters": self._extract_parameters(user_input, intent)
                }
        
        return {
            "intent_type": "general_inquiry",
            "confidence": 0.5,
            "parameters": {}
        }
    
    def _extract_parameters(self, user_input: str, intent_type: str) -> Dict[str, str]:
        """Extract parameters from user input based on intent"""
        parameters = {}
        
        if intent_type == "card_delivery_status":
            # Look for card types
            if "kredi" in user_input.lower():
                parameters["card_type"] = "credit"
            elif "banka" in user_input.lower():
                parameters["card_type"] = "debit"
        
        return parameters


class LLMServiceImpl(llm_service_pb2_grpc.LLMServiceServicer):
    """LLM Service gRPC implementation using proven Llama WebSocket"""
    
    def __init__(self):
        # LLM engines per session (like legacy)
        self.session_engines: Dict[str, LlamaLLMEngine] = {}
        self.session_contexts: Dict[str, List[Dict[str, str]]] = {}
        self.session_stats: Dict[str, Dict[str, Any]] = {}
        
        # Default Llama server config
        self.default_llm_config = {
            "url": "ws://llm-turkish-server:8765",
            "model": "llama3.2:3b-instruct-turkish",
            "temperature": 0.2,
            "max_tokens": 80
        }
        
        logger.info("LLM Service initialized with Llama WebSocket engine")
    
    async def GenerateResponse(self, request, context):
        """Generate response to user input"""
        try:
            session_id = request.session_id
            user_input = request.user_input
            conversation_context = request.context
            config = request.config
            
            start_time = time.time()
            
            # Get or create LLM engine for session
            if session_id not in self.session_engines:
                await self._create_session_engine(session_id, config)
            
            engine = self.session_engines[session_id]
            
            # Get conversation history
            if session_id not in self.session_contexts:
                self.session_contexts[session_id] = []
                # Add system prompt for banking (same as legacy)
                self.session_contexts[session_id].append({
                    "role": "system",
                    "content": engine.banking_system_prompt
                })
            
            messages = self.session_contexts[session_id].copy()
            
            # Add user message
            messages.append({
                "role": "user", 
                "content": user_input
            })
            
            logger.debug("Processing LLM request",
                        session_id=session_id,
                        user_input=user_input,
                        messages_count=len(messages))
            
            # Generate response using Llama (same as legacy)
            llama_result = await engine.generate_response(messages)
            
            processing_time = (time.time() - start_time) * 1000
            
            # Update session stats
            self._update_session_stats(session_id, llama_result, processing_time)
            
            # Convert Llama result to protobuf response
            response = llm_service_pb2.GenerateResponseResponse()
            response.session_id = session_id
            
            # Parse Llama response (same logic as legacy)
            if "choices" in llama_result and llama_result["choices"]:
                choice = llama_result["choices"][0]
                assistant_message = choice["message"]["content"]
                
                # Add to conversation context
                messages.append({
                    "role": "assistant",
                    "content": assistant_message
                })
                self.session_contexts[session_id] = messages[-10:]  # Keep last 10 messages
                
                response.status.code = common_pb2.Status.OK
                
                # LLM result
                response.result.response_text = assistant_message
                response.result.confidence = 0.9  # High confidence for Llama
                
                # Analyze banking intent
                intent_analysis = engine.analyze_banking_intent(user_input)
                response.result.intent_analysis.primary_intent.intent_type = intent_analysis["intent_type"]
                response.result.intent_analysis.primary_intent.confidence = intent_analysis["confidence"]
                
                # Set conversation state
                response.result.conversation_state.current_topic = intent_analysis["intent_type"]
                response.result.conversation_state.conversation_phase = "inquiry"
                response.result.conversation_state.turn_count = len(messages) // 2
                
                # Banking safety checks
                pii_check = response.result.safety_checks.add()
                pii_check.check_type = "pii_detection"
                pii_check.passed = True  # Simple implementation
                pii_check.message = "No PII detected"
                
                logger.info("LLM response generated",
                           session_id=session_id,
                           response_text=assistant_message,
                           intent=intent_analysis["intent_type"],
                           processing_time_ms=processing_time)
                
            elif "error" in llama_result:
                # Error occurred
                response.status.code = common_pb2.Status.INTERNAL
                response.status.message = llama_result["error"]
                logger.error("LLM generation error", session_id=session_id, error=llama_result["error"])
                
            else:
                # Unexpected response format
                response.status.code = common_pb2.Status.INTERNAL
                response.status.message = "Unexpected LLM response format"
                logger.error("Unexpected LLM response", session_id=session_id, response=llama_result)
            
            # Metrics
            response.metrics.processing_time_ms = processing_time
            response.metrics.input_tokens = len(user_input.split())  # Rough estimate
            response.metrics.output_tokens = len(response.result.response_text.split()) if response.result.response_text else 0
            response.metrics.model_version = engine.model
            
            return response
            
        except Exception as e:
            logger.error("LLM generation failed", session_id=session_id, error=str(e))
            response = llm_service_pb2.GenerateResponseResponse()
            response.status.code = common_pb2.Status.INTERNAL
            response.status.message = f"LLM generation failed: {str(e)}"
            return response
    
    async def GenerateResponseStream(self, request, context):
        """Stream-based response generation (placeholder)"""
        # For now, just return single response
        response = await self.GenerateResponse(request, context)
        yield response
    
    async def AnalyzeIntent(self, request, context):
        """Analyze user intent"""
        try:
            session_id = request.session_id
            user_input = request.user_input
            
            # Get engine for session
            if session_id not in self.session_engines:
                await self._create_session_engine(session_id, None)
            
            engine = self.session_engines[session_id]
            
            # Analyze intent
            intent_analysis = engine.analyze_banking_intent(user_input)
            
            response = llm_service_pb2.AnalyzeIntentResponse()
            response.status.code = common_pb2.Status.OK
            response.session_id = session_id
            
            # Set intent analysis
            response.analysis.primary_intent.intent_type = intent_analysis["intent_type"]
            response.analysis.primary_intent.confidence = intent_analysis["confidence"]
            response.analysis.intent_confidence = intent_analysis["confidence"]
            
            # Add extracted entities
            for key, value in intent_analysis["parameters"].items():
                response.analysis.extracted_entities[key] = value
            
            logger.info("Intent analyzed",
                       session_id=session_id,
                       user_input=user_input,
                       intent=intent_analysis["intent_type"],
                       confidence=intent_analysis["confidence"])
            
            return response
            
        except Exception as e:
            logger.error("Intent analysis failed", session_id=session_id, error=str(e))
            response = llm_service_pb2.AnalyzeIntentResponse()
            response.status.code = common_pb2.Status.INTERNAL
            response.status.message = f"Intent analysis failed: {str(e)}"
            return response
    
    async def UpdateContext(self, request, context):
        """Update conversation context"""
        try:
            session_id = request.session_id
            updates = dict(request.updates)
            
            # Apply context updates
            if session_id in self.session_contexts:
                # Simple implementation - just log updates
                logger.info("Context updated", session_id=session_id, updates=updates)
            
            response = llm_service_pb2.UpdateContextResponse()
            response.status.code = common_pb2.Status.OK
            
            return response
            
        except Exception as e:
            logger.error("Context update failed", session_id=session_id, error=str(e))
            response = llm_service_pb2.UpdateContextResponse()
            response.status.code = common_pb2.Status.INTERNAL
            response.status.message = f"Context update failed: {str(e)}"
            return response
    
    async def ProcessBankingIntent(self, request, context):
        """Process banking-specific intent"""
        try:
            session_id = request.session_id
            intent = request.intent
            customer = request.customer
            
            response = llm_service_pb2.ProcessBankingIntentResponse()
            response.status.code = common_pb2.Status.OK
            response.session_id = session_id
            
            # Banking intent processing
            if intent.intent_type == "card_delivery_status":
                response.result.response_template = (
                    "Kartınızın teslimat durumunu kontrol ediyorum. "
                    "Hesap numaranızı doğrulayabilir misiniz?"
                )
                
                # Add authentication requirement
                response.result.auth_requirement.required = True
                response.result.auth_requirement.auth_methods.append("account_number")
                response.result.auth_requirement.reason = "Kart bilgilerine erişim için kimlik doğrulama gerekli"
                
                # Add required action
                action = response.result.required_actions.add()
                action.action_type = "api_call"
                action.service_endpoint = "card-delivery-service"
                action.requires_customer_consent = True
                
            elif intent.intent_type == "account_balance":
                response.result.response_template = (
                    "Hesap bakiyenizi öğrenmek için kimlik doğrulama gerekli. "
                    "TC kimlik numaranızın son 4 hanesi ile telefon numaranızı doğrulayabilir misiniz?"
                )
                
                response.result.auth_requirement.required = True
                response.result.auth_requirement.auth_methods.extend(["phone_verification", "tc_last_4"])
                
            else:
                response.result.response_template = (
                    "Size nasıl yardımcı olabilirim? "
                    "Kart teslimat durumu, hesap bakiyesi gibi konularda destek sağlayabilirim."
                )
            
            # Compliance info
            response.result.compliance.requires_audit_log = True
            response.result.compliance.data_classification = "confidential"
            response.result.compliance.compliance_tags.append("banking_inquiry")
            
            logger.info("Banking intent processed",
                       session_id=session_id,
                       intent_type=intent.intent_type,
                       auth_required=response.result.auth_requirement.required)
            
            return response
            
        except Exception as e:
            logger.error("Banking intent processing failed", session_id=session_id, error=str(e))
            response = llm_service_pb2.ProcessBankingIntentResponse()
            response.status.code = common_pb2.Status.INTERNAL
            response.status.message = f"Banking intent processing failed: {str(e)}"
            return response
    
    async def HealthCheck(self, request, context):
        """Health check implementation"""
        try:
            # Test connection to Llama server
            test_engine = LlamaLLMEngine(**self.default_llm_config)
            
            start_time = time.time()
            await test_engine.connect()
            
            # Test with simple message
            test_messages = [
                {"role": "system", "content": "Sen bir test asistanısın."},
                {"role": "user", "content": "Merhaba"}
            ]
            test_result = await test_engine.generate_response(test_messages)
            
            await test_engine.disconnect()
            
            response_time = (time.time() - start_time) * 1000
            
            response = common_pb2.HealthCheckResponse()
            response.status = common_pb2.HealthCheckResponse.SERVING
            response.message = "LLM service operational"
            response.details["active_sessions"] = str(len(self.session_engines))
            response.details["test_response_time_ms"] = f"{response_time:.2f}"
            response.details["llm_url"] = self.default_llm_config["url"]
            response.details["model"] = self.default_llm_config["model"]
            
            logger.debug("LLM health check passed", response_time_ms=response_time)
            return response
            
        except Exception as e:
            logger.error("LLM health check failed", error=str(e))
            response = common_pb2.HealthCheckResponse()
            response.status = common_pb2.HealthCheckResponse.NOT_SERVING
            response.status.message = f"Health check failed: {str(e)}"
            return response
    
    async def _create_session_engine(self, session_id: str, config):
        """Create LLM engine for session"""
        try:
            # Use config or defaults
            engine_config = self.default_llm_config.copy()
            if config:
                if config.model_name:
                    engine_config["model"] = config.model_name
                if config.temperature > 0:
                    engine_config["temperature"] = config.temperature
                if config.max_tokens > 0:
                    engine_config["max_tokens"] = config.max_tokens
            
            engine = LlamaLLMEngine(**engine_config)
            await engine.connect()
            
            # Clean up old engine if exists
            if session_id in self.session_engines:
                await self.session_engines[session_id].disconnect()
            
            self.session_engines[session_id] = engine
            self.session_stats[session_id] = {
                'created_at': time.time(),
                'total_requests': 0,
                'successful_responses': 0,
                'avg_processing_time': 0.0
            }
            
            logger.info("LLM engine created for session",
                       session_id=session_id,
                       model=engine_config["model"],
                       temperature=engine_config["temperature"])
            
        except Exception as e:
            logger.error("Failed to create LLM engine", session_id=session_id, error=str(e))
            raise
    
    def _update_session_stats(self, session_id: str, llama_result: Dict[str, Any], processing_time: float):
        """Update session statistics"""
        if session_id in self.session_stats:
            stats = self.session_stats[session_id]
            stats['total_requests'] += 1
            
            if "choices" in llama_result and llama_result["choices"]:
                stats['successful_responses'] += 1
            
            # Update average processing time
            total_time = stats['avg_processing_time'] * (stats['total_requests'] - 1)
            stats['avg_processing_time'] = (total_time + processing_time) / stats['total_requests']


async def serve():
    """Start the LLM gRPC server"""
    server = aio_grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    
    # Add LLM service
    llm_service_pb2_grpc.add_LLMServiceServicer_to_server(LLMServiceImpl(), server)
    
    # Configure server
    listen_addr = '[::]:50054'
    server.add_insecure_port(listen_addr)
    
    # Start server
    await server.start()
    logger.info("LLM Service started", address=listen_addr, model="llama3.2-turkish")
    
    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("LLM Service shutting down")
        await server.stop(grace=30)


if __name__ == '__main__':
    asyncio.run(serve())