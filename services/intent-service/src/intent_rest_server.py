"""
Intent Recognition Service - REST Mock Server Implementation
Turkish Bank Call Center Scenarios
"""

import time
import logging
from typing import Dict, Any, List, Optional

try:
    from flask import Flask, request, jsonify
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False
    Flask = None

try:
    import structlog
    STRUCTLOG_AVAILABLE = True
except ImportError:
    STRUCTLOG_AVAILABLE = False
    structlog = None

# Setup logging
if STRUCTLOG_AVAILABLE:
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
else:
    # Fallback to standard logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)


class TurkishBankIntentClassifier:
    """Turkish Bank Call Center Intent Classifier Mock"""
    
    def __init__(self):
        self.model_version = "turkish-bank-mock-v1.0"
        self.supported_intents = {
            "hesap_bakiye_sorgulama": {
                "display_name": "Hesap Bakiye Sorgulama",
                "description": "Müşterinin hesap bakiyesini öğrenmek istemesi",
                "default_threshold": 0.85,
                "examples": [
                    "hesap bakiyemi öğrenmek istiyorum",
                    "bakiyemi kontrol etmek istiyorum", 
                    "hesabımda ne kadar param var",
                    "para durumum nasıl",
                    "hesapta kaç lira var"
                ]
            },
            "kredi_karti_bilgi": {
                "display_name": "Kredi Kartı Bilgileri",
                "description": "Kredi kartı ile ilgili bilgi talebi",
                "default_threshold": 0.80,
                "examples": [
                    "kredi kartım ne zaman gelir",
                    "kartımın limiti nedir",
                    "kredi kartı başvurusu",
                    "kart borcum ne kadar",
                    "son kullanma tarihi"
                ]
            },
            "musteri_hizmetleri": {
                "display_name": "Müşteri Hizmetleri Talebi", 
                "description": "Operatör veya temsilci ile konuşma isteği",
                "default_threshold": 0.75,
                "examples": [
                    "müşteri hizmetleriyle konuşmak istiyorum",
                    "temsilciyle görüşmek istiyorum",
                    "operatöre bağlanmak istiyorum",
                    "insan operatör istiyorum",
                    "canlı destek"
                ]
            },
            "havale_eft": {
                "display_name": "Havale/EFT İşlemleri",
                "description": "Para transferi işlemleri",
                "default_threshold": 0.82,
                "examples": [
                    "para göndermek istiyorum",
                    "havale yapmak istiyorum",
                    "eft işlemi",
                    "başka hesaba para transferi",
                    "para yatırmak istiyorum"
                ]
            },
            "sifre_unutma": {
                "display_name": "Şifre Unutma",
                "description": "İnternet bankacılığı veya kart şifresi unutma",
                "default_threshold": 0.88,
                "examples": [
                    "şifremi unuttum",
                    "internet bankacılığı şifresi",
                    "kart şifremi unuttum", 
                    "yeni şifre almak istiyorum",
                    "şifre sıfırlama"
                ]
            },
            "hesap_acma": {
                "display_name": "Hesap Açma",
                "description": "Yeni banka hesabı açma talebi",
                "default_threshold": 0.85,
                "examples": [
                    "hesap açmak istiyorum",
                    "yeni hesap",
                    "banka hesabı açtırmak istiyorum",
                    "vadesiz hesap",
                    "mevduat hesabı"
                ]
            },
            "sikayet": {
                "display_name": "Şikayet",
                "description": "Müşteri şikayeti",
                "default_threshold": 0.70,
                "examples": [
                    "şikayet etmek istiyorum",
                    "memnun değilim",
                    "sorun yaşıyorum",
                    "hatalı işlem",
                    "problem var"
                ]
            },
            "bilinmeyen": {
                "display_name": "Bilinmeyen Talep",
                "description": "Tanımlanmayan intent",
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
        """Turkish Bank Call Center Intent Classification"""
        start_time = time.time()
        
        try:
            text_lower = text.lower().strip()
            
            # Turkish bank call center keyword classification
            if any(keyword in text_lower for keyword in ["bakiye", "hesap", "para", "lira", "tl"]):
                intent = "hesap_bakiye_sorgulama"
                confidence = 0.92
            elif any(keyword in text_lower for keyword in ["kredi", "kart", "limit", "borç", "son kullanma"]):
                intent = "kredi_karti_bilgi"
                confidence = 0.88
            elif any(keyword in text_lower for keyword in ["müşteri", "temsilci", "operatör", "insan", "canlı"]):
                intent = "musteri_hizmetleri"
                confidence = 0.85
            elif any(keyword in text_lower for keyword in ["havale", "eft", "gönder", "transfer", "yatır"]):
                intent = "havale_eft"
                confidence = 0.87
            elif any(keyword in text_lower for keyword in ["şifre", "unuttum", "sıfırla", "yeni şifre"]):
                intent = "sifre_unutma"
                confidence = 0.93
            elif any(keyword in text_lower for keyword in ["hesap aç", "yeni hesap", "vadesiz", "mevduat"]):
                intent = "hesap_acma"
                confidence = 0.90
            elif any(keyword in text_lower for keyword in ["şikayet", "problem", "sorun", "memnun değil", "hata"]):
                intent = "sikayet"
                confidence = 0.82
            else:
                intent = "bilinmeyen"
                confidence = 0.30
            
            # Filter by candidate intents if provided
            if candidate_intents and intent not in candidate_intents:
                intent = "bilinmeyen"
                confidence = 0.25
            
            # Generate alternative intents
            alternatives = []
            for alt_intent, alt_info in self.supported_intents.items():
                if alt_intent != intent and alt_intent != "bilinmeyen":
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
                "intent": "bilinmeyen",
                "confidence": 0.0,
                "meets_threshold": False,
                "alternatives": [],
                "processing_time_ms": processing_time,
                "token_count": 0,
                "model_version": self.model_version,
                "error": str(e)
            }


# Initialize Flask app and classifier
if not FLASK_AVAILABLE:
    raise ImportError("Flask is required. Install with: pip install Flask")

app = Flask(__name__)
classifier = TurkishBankIntentClassifier()
active_sessions = set()

logger.info("Turkish Bank Intent Recognition Service initialized", 
           model_version=classifier.model_version)

@app.route('/v1/classify', methods=['POST'])
@app.route('/classify', methods=['POST'])  # Backward compatibility
def classify_intent():
    """Classify single text input"""
    try:
        data = request.get_json()
        if not data or 'text' not in data:
            return jsonify({'error': 'Missing text field'}), 400
        
        session_id = data.get('session_id', f"session_{int(time.time() * 1000)}")
        active_sessions.add(session_id)
        
        text = data['text']
        threshold = data.get('confidence_threshold', 0.85)
        candidate_intents = data.get('candidate_intents', None)
        
        logger.debug("Processing intent classification",
                    session_id=session_id,
                    text=text,
                    threshold=threshold)
        
        # Classify using Turkish bank classifier
        result = classifier.classify_text(
            text=text,
            confidence_threshold=threshold,
            candidate_intents=candidate_intents
        )
        
        logger.info("Intent classification completed",
                   session_id=session_id,
                   intent=result["intent"],
                   confidence=result["confidence"],
                   meets_threshold=result["meets_threshold"],
                   processing_time_ms=result["processing_time_ms"])
        
        return jsonify(result)
        
    except Exception as e:
        logger.error("Intent classification failed", error=str(e))
        return jsonify({'error': str(e)}), 500

@app.route('/v1/classify/batch', methods=['POST'])
@app.route('/classify/batch', methods=['POST'])  # Backward compatibility
def classify_intent_batch():
    """Classify multiple texts in batch"""
    try:
        data = request.get_json()
        if not data or 'requests' not in data:
            return jsonify({'error': 'Missing requests field'}), 400
        
        start_time = time.time()
        responses = []
        successful = 0
        failed = 0
        
        logger.debug("Processing batch classification", batch_size=len(data['requests']))
        
        for req in data['requests']:
            if 'text' not in req:
                continue
                
            result = classifier.classify_text(
                text=req['text'],
                confidence_threshold=req.get('confidence_threshold', 0.85),
                candidate_intents=req.get('candidate_intents', None)
            )
            responses.append(result)
            
            if result['meets_threshold']:
                successful += 1
            else:
                failed += 1
        
        total_time = (time.time() - start_time) * 1000
        avg_time = total_time / len(data['requests']) if data['requests'] else 0
        
        batch_response = {
            'responses': responses,
            'batch_metrics': {
                'total_processing_time_ms': total_time,
                'successful_classifications': successful,
                'failed_classifications': failed,
                'average_processing_time_ms': avg_time
            }
        }
        
        logger.info("Batch classification completed",
                   batch_size=len(data['requests']),
                   successful=successful,
                   failed=failed,
                   total_time_ms=total_time)
        
        return jsonify(batch_response)
        
    except Exception as e:
        logger.error("Batch classification failed", error=str(e))
        return jsonify({'error': str(e)}), 500

@app.route('/v1/intents', methods=['GET'])
@app.route('/intents', methods=['GET'])  # Backward compatibility
def get_supported_intents():
    """Get list of supported intents"""
    try:
        intents_list = []
        for intent_key, intent_info in classifier.supported_intents.items():
            intents_list.append({
                'intent_label': intent_key,
                'display_name': intent_info['display_name'],
                'description': intent_info['description'], 
                'default_threshold': intent_info['default_threshold'],
                'example_phrases': intent_info['examples'],
                'training_sample_count': len(intent_info['examples'])
            })
        
        response = {
            'supported_intents': intents_list,
            'total_count': len(classifier.supported_intents),
            'model_version': classifier.model_version
        }
        
        logger.debug("Supported intents requested", count=len(intents_list))
        return jsonify(response)
        
    except Exception as e:
        logger.error("Get supported intents failed", error=str(e))
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        response = {
            'status': 'SERVING',
            'message': 'Turkish Bank Intent Recognition Service operational',
            'model_version': classifier.model_version,
            'supported_intents_count': len(classifier.supported_intents),
            'model_load_time_ms': 100.0
        }
        
        logger.debug("Health check passed")
        return jsonify(response)
        
    except Exception as e:
        logger.error("Health check failed", error=str(e))
        return jsonify({
            'status': 'NOT_SERVING',
            'message': f'Health check failed: {str(e)}'
        }), 500

@app.route('/v1/stats', methods=['GET'])
@app.route('/stats', methods=['GET'])  # Backward compatibility
def get_stats():
    """Get service statistics"""
    try:
        uptime = time.time() - classifier.start_time
        avg_processing_time = (classifier.total_processing_time / 
                             classifier.total_classifications 
                             if classifier.total_classifications > 0 else 0.0)
        
        response = {
            'total_classifications': classifier.total_classifications,
            'successful_classifications': classifier.successful_classifications,
            'failed_classifications': classifier.failed_classifications,
            'average_processing_time_ms': avg_processing_time,
            'average_confidence': 0.85,
            'uptime_seconds': int(uptime),
            'model_version': classifier.model_version,
            'active_sessions': len(active_sessions),
            'intent_usage_count': classifier.intent_usage_count
        }
        
        logger.debug("Service stats requested", uptime_seconds=int(uptime))
        return jsonify(response)
        
    except Exception as e:
        logger.error("Get stats failed", error=str(e))
        return jsonify({'error': str(e)}), 500

def run_server():
    """Start the REST server"""
    logger.info("Turkish Bank Intent Recognition Service starting", 
               port=5000, 
               model="turkish-bank-mock",
               supported_intents=len(classifier.supported_intents))
    
    app.run(host='0.0.0.0', port=5000, debug=False)

if __name__ == '__main__':
    run_server()