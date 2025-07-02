"""
WebSocket server for streaming LLM responses with RAG support.
"""
import asyncio
import json
import logging
import os
import websockets
from llm_stream import initialize_model, get_llm_instance, is_model_loaded
from rag_system import initialize_rag, get_rag_instance, is_rag_enabled

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

async def handle_client(websocket):
    """
    Handle individual WebSocket client connections.
    Keep connection alive until client closes it.
    
    Args:
        websocket: WebSocket connection
    """
    client_address = websocket.remote_address
    logger.info(f"🔗 New client connected: {client_address}")
    
    try:
        # Keep connection alive and handle multiple messages
        while True:
            try:
                # Wait for client message
                message = await websocket.recv()
                logger.info(f"📨 Received message from {client_address}: {message[:100]}...")
                
                try:
                    # Parse JSON message
                    data = json.loads(message)
                    logger.debug(f"🔍 Parsed JSON data: {data}")
                    logger.debug(f"🔍 Data type: {type(data)}")
                    
                    # Validate message format
                    if not isinstance(data, dict):
                        raise ValueError("Message must be a JSON object")
                    
                    # ------------------------------------------------------------------
                    # 🔄 1. Support BOTH formats: OpenAI ChatCompletion and flat prompt
                    # ------------------------------------------------------------------

                    prompt: str = ""
                    system_prompt: str = ""

                    if "messages" in data:
                        # OpenAI-style schema
                        messages = data["messages"]
                        if not isinstance(messages, list):
                            raise ValueError("'messages' must be a list of role/content objects")

                        # First system message becomes system_prompt (if any)
                        for m in messages:
                            if m.get("role") == "system":
                                system_prompt = m.get("content", "")
                                break

                        # Use the last user message as prompt
                        user_msgs = [m.get("content", "") for m in messages if m.get("role") == "user"]
                        if user_msgs:
                            prompt = user_msgs[-1]

                        # Remove keys we've already handled from generation_params later
                        data.pop("messages", None)
                    else:
                        # Legacy flat schema
                        prompt = data.get('prompt', '')
                        system_prompt = data.get('system_prompt', """
                    Sen Garanti BBVA IVR hattında, Türkçe TTS için konuşma metni üreten bir dil modelisin.

                    Kurallar:
                    1. Kısa-orta uzunlukta, net ve resmi cümleler yaz (en çok 20 kelime).
                    2. Türkçe imlâyı tam uygula (ç, ğ, ı, ö, ş, ü).
                    3. Tarihleri "2 Haziran 2025", saatleri "14.30" biçiminde yaz.
                    4. Kritik sayıları tam ver: "₺250", "1234".
                    5. Gereksiz sembol, yabancı kelime, ünlem ve jargon kullanma.
                    6. Yalnızca TTS'ye okunacak metni döndür; fazladan açıklama ekleme.

                    Örnek  
                    Girdi: {"status":"in_transit","date":"2025-06-02"}  
                    Çıktı: Kartınız kuryede, tahmini teslim tarihi 2 Haziran 2025.
                    """)

                    # RAG settings
                    use_rag = data.get('use_rag', True)  # Enable RAG by default
                    rag_k = data.get('rag_k', None)  # Number of documents to retrieve
                    
                    # Handle None values properly
                    if system_prompt is None:
                        system_prompt = ''
                        logger.debug("🔍 Converting None system_prompt to empty string")
                    
                    logger.debug(f"🔍 Extracted prompt: '{prompt}'")
                    logger.debug(f"🔍 Extracted system_prompt: '{system_prompt[:100]}...'")
                    logger.debug(f"🔍 RAG enabled: {use_rag}")
                    
                    if not prompt:
                        raise ValueError("Prompt text is required (provide either 'prompt' or a 'messages' list with at least one user message)")
                    
                    # Get additional generation parameters - handle None values
                    generation_params = {}
                    for k, v in data.items():
                        if k not in ['prompt', 'system_prompt', 'use_rag', 'rag_k']:
                            if v is not None:  # Only add non-None values
                                generation_params[k] = v
                                logger.debug(f"🔍 Added param {k}: {v}")
                            else:
                                logger.debug(f"🔍 Skipping None param {k}")
                    
                    logger.debug(f"🔍 Final generation_params: {generation_params}")
                    
                    # Enhance prompt with RAG if enabled
                    enhanced_prompt = prompt
                    context_used = ""
                    
                    if use_rag and is_rag_enabled():
                        rag_system = get_rag_instance()
                        logger.info("🔍 Enhancing prompt with RAG context...")
                        enhanced_prompt, context_used = rag_system.enhance_prompt_with_rag(
                            prompt, use_rag=True
                        )
                        
                        if context_used:
                            logger.info(f"✨ RAG enhanced prompt with {len(context_used)} chars of context")
                            # Send context info to client
                            context_info = json.dumps({
                                "rag_context": context_used[:500] + "..." if len(context_used) > 500 else context_used,
                                "context_length": len(context_used)
                            })
                            await websocket.send(context_info)
                        else:
                            logger.info("🔍 No relevant RAG context found, using original prompt")
                    elif use_rag and not is_rag_enabled():
                        logger.warning("⚠️ RAG requested but not enabled/initialized")
                    
                    logger.info(f"🤖 Processing request: prompt='{prompt[:50]}...', enhanced='{enhanced_prompt[:50]}...'")
                    
                    # Get the SHARED LLM instance (already loaded at startup)
                    logger.debug("🔍 Getting LLM instance...")
                    llm = get_llm_instance()
                    logger.debug(f"🔄 Using shared model instance for client {client_address}")
                    
                    # Stream response
                    logger.debug("🔍 Starting to stream response...")
                    chunk_count = 0
                    async for chunk in llm.stream_chat(enhanced_prompt, system_prompt, **generation_params):
                        chunk_count += 1
                        logger.debug(f"🔍 Received chunk #{chunk_count}: '{chunk[:20]}...'")
                        
                        # Send chunk to client
                        response = json.dumps({"chunk": chunk})
                        await websocket.send(response)
                        logger.debug(f"📤 Sent chunk to {client_address}: {chunk[:30]}...")
                    
                    logger.debug(f"🔍 Finished streaming, total chunks: {chunk_count}")
                    
                    # Send completion signal
                    completion = json.dumps({"done": True})
                    await websocket.send(completion)
                    logger.info(f"✅ Completed request for {client_address}")
                    logger.info(f"🔄 Waiting for next message from {client_address}...")
                    
                except json.JSONDecodeError as e:
                    error_msg = f"Invalid JSON: {str(e)}"
                    logger.error(f"❌ JSON error from {client_address}: {error_msg}")
                    error_response = json.dumps({"error": error_msg})
                    await websocket.send(error_response)
                    # Continue listening for next message instead of closing
                    
                except ValueError as e:
                    error_msg = str(e)
                    logger.error(f"❌ Validation error from {client_address}: {error_msg}")
                    error_response = json.dumps({"error": error_msg})
                    await websocket.send(error_response)
                    # Continue listening for next message instead of closing
                    
                except Exception as e:
                    error_msg = f"Processing error: {str(e)}"
                    logger.error(f"❌ Processing error from {client_address}: {error_msg}")
                    logger.error(f"❌ Error type: {type(e)}")
                    import traceback
                    logger.error(f"❌ Full traceback: {traceback.format_exc()}")
                    error_response = json.dumps({"error": error_msg})
                    await websocket.send(error_response)
                    # Continue listening for next message instead of closing
                    
            except websockets.exceptions.ConnectionClosed:
                logger.info(f"🔌 Client {client_address} disconnected")
                break  # Exit the while loop when client closes connection
                
    except Exception as e:
        logger.error(f"💥 Unexpected error with {client_address}: {e}")
    finally:
        logger.info(f"🔚 Connection handler finished for {client_address}")

async def handle_rag_management(websocket, path):
    """
    Handle RAG management WebSocket endpoint for document ingestion and queries.
    """
    client_address = websocket.remote_address
    logger.info(f"🔗 RAG management client connected: {client_address}")
    
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                action = data.get('action')
                
                if not is_rag_enabled():
                    await websocket.send(json.dumps({
                        "error": "RAG system not initialized"
                    }))
                    continue
                
                rag_system = get_rag_instance()
                
                if action == 'ingest':
                    # Ingest documents
                    force_reload = data.get('force_reload', False)
                    result = rag_system.ingest_documents(force_reload=force_reload)
                    await websocket.send(json.dumps({
                        "action": "ingest",
                        "success": result,
                        "stats": rag_system.get_stats()
                    }))
                
                elif action == 'search':
                    # Search documents
                    query = data.get('query', '')
                    k = data.get('k', 5)
                    
                    if not query:
                        await websocket.send(json.dumps({
                            "error": "Query is required for search"
                        }))
                        continue
                    
                    docs = rag_system.search_documents(query, k)
                    results = []
                    for doc in docs:
                        results.append({
                            "content": doc.page_content[:500],  # Truncate for readability
                            "metadata": doc.metadata
                        })
                    
                    await websocket.send(json.dumps({
                        "action": "search",
                        "query": query,
                        "results": results,
                        "count": len(results)
                    }))
                
                elif action == 'stats':
                    # Get RAG statistics
                    await websocket.send(json.dumps({
                        "action": "stats",
                        "stats": rag_system.get_stats()
                    }))
                
                else:
                    await websocket.send(json.dumps({
                        "error": f"Unknown action: {action}"
                    }))
                    
            except json.JSONDecodeError as e:
                await websocket.send(json.dumps({
                    "error": f"Invalid JSON: {str(e)}"
                }))
            except Exception as e:
                await websocket.send(json.dumps({
                    "error": f"Error: {str(e)}"
                }))
                
    except websockets.exceptions.ConnectionClosed:
        logger.info(f"🔌 RAG management client {client_address} disconnected")
    except Exception as e:
        logger.error(f"💥 RAG management error with {client_address}: {e}")

async def main():
    """Main server function."""
    # Configuration
    host = os.getenv('HOST', '0.0.0.0')
    port = int(os.getenv('PORT', '8765'))
    rag_port = int(os.getenv('RAG_PORT', '8766'))
    enable_rag = os.getenv('ENABLE_RAG', 'true').lower() == 'true'
    
    # RAG configuration for offline mode
    use_local_model = os.getenv('RAG_USE_LOCAL_MODEL', 'true').lower() == 'true'
    embedding_model = os.getenv('RAG_EMBEDDING_MODEL', 'sentence-transformers/all-MiniLM-L6-v2')
    local_models_dir = os.getenv('RAG_LOCAL_MODELS_DIR', 'rag_model')
    device = os.getenv('RAG_DEVICE', 'cpu')
    documents_dir = os.getenv('RAG_DOCUMENTS_DIR', 'rag_documents')
    
    logger.info(f"🚀 Starting WebSocket server on {host}:{port}")
    logger.info(f"🔍 RAG enabled: {enable_rag}")
    logger.info(f"🔍 RAG offline mode: {use_local_model}")
    logger.info(f"🔍 RAG embedding model: {embedding_model}")
    logger.info(f"🔍 RAG device: {device}")
    
    try:
        # IMPORTANT: Load the LLM model ONCE at startup
        logger.info("🔄 Pre-loading LLM model (this happens ONLY ONCE)...")
        initialize_model()
        logger.info("✅ LLM model loaded and ready! All future WebSocket connections will use this shared instance.")
        
        # Initialize RAG system if enabled
        if enable_rag:
            logger.info("🔄 Initializing RAG system...")
            try:
                # Initialize RAG with offline configuration
                rag_config = {
                    'use_local_model': use_local_model,
                    'embedding_model': embedding_model,
                    'local_models_dir': local_models_dir,
                    'device': device,
                    'documents_dir': documents_dir
                }
                
                logger.info(f"🔍 RAG configuration: {rag_config}")
                initialize_rag(**rag_config)
                
                # Display RAG stats
                from rag_system import get_rag_instance
                rag_system = get_rag_instance()
                stats = rag_system.get_stats()
                logger.info("📊 RAG System Stats:")
                for key, value in stats.items():
                    logger.info(f"   {key}: {value}")
                
                logger.info("✅ RAG system initialized and ready!")
                logger.info(f"🔍 RAG management available on ws://{host}:{rag_port}")
            except Exception as e:
                logger.error(f"❌ Failed to initialize RAG system: {e}")
                logger.warning("⚠️ Continuing without RAG support")
        
        # Start WebSocket servers
        logger.info(f"🌐 Starting main WebSocket server on ws://{host}:{port}")
        main_server = websockets.serve(handle_client, host, port)
        
        servers_to_start = [main_server]
        
        if enable_rag and is_rag_enabled():
            logger.info(f"🔍 Starting RAG management server on ws://{host}:{rag_port}")
            rag_server = websockets.serve(handle_rag_management, host, rag_port)
            servers_to_start.append(rag_server)
        
        # Start all servers
        await asyncio.gather(*servers_to_start)
        
        logger.info(f"🌐 Main WebSocket server running on ws://{host}:{port}")
        if enable_rag and is_rag_enabled():
            logger.info(f"🔍 RAG management server running on ws://{host}:{rag_port}")
        logger.info("🎯 Server ready to accept connections - model is loaded and shared!")
        logger.info(f"📊 Model loaded: {is_model_loaded()}")
        logger.info(f"🔍 RAG enabled: {is_rag_enabled()}")
        
        # Keep the server running
        await asyncio.Future()  # Run forever
            
    except KeyboardInterrupt:
        logger.info("🛑 Server shutdown requested")
    except Exception as e:
        logger.error(f"💥 Server error: {e}")
        raise

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Server stopped by user")
    except Exception as e:
        logger.error(f"💥 Fatal error: {e}")
        exit(1) 