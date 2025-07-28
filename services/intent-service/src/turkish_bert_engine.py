"""
Turkish BERT Intent Recognition Engine
Real Turkish BERT model for IVR response classification using dbmdz/bert-base-turkish-uncased
"""

import os
import logging
import json
import re
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
import numpy as np

try:
    import torch
    from transformers import AutoTokenizer, AutoModelForSequenceClassification, pipeline
    from transformers import TrainingArguments, Trainer
    import pandas as pd
    from sklearn.metrics import accuracy_score, precision_recall_fscore_support
    BERT_AVAILABLE = True
except ImportError:
    BERT_AVAILABLE = False
    torch = None
    pd = None

import structlog

logger = structlog.get_logger(__name__)

@dataclass
class IntentPrediction:
    """Intent prediction result"""
    intent: str
    confidence: float
    raw_scores: Dict[str, float]
    preprocessed_text: str

@dataclass
class ModelConfig:
    """Turkish BERT model configuration"""
    model_name: str = "dbmdz/bert-base-turkish-uncased"
    max_length: int = 128
    batch_size: int = 8
    confidence_threshold: float = 0.7
    cache_dir: str = "./models/cache"
    device: str = "cpu"  # CPU-only for production deployment

class TurkishTextPreprocessor:
    """Turkish text preprocessing for BERT"""
    
    def __init__(self):
        self.turkish_chars = {
            'ç': 'c', 'ğ': 'g', 'ı': 'i', 'ö': 'o', 'ş': 's', 'ü': 'u',
            'Ç': 'C', 'Ğ': 'G', 'İ': 'I', 'Ö': 'O', 'Ş': 'S', 'Ü': 'U'
        }
        
    def normalize_turkish(self, text: str) -> str:
        """Normalize Turkish characters for better model compatibility"""
        # Keep original Turkish characters for Turkish BERT
        return text
    
    def clean_text(self, text: str) -> str:
        """Clean and normalize text for classification"""
        if not text:
            return ""
        
        # Convert to lowercase
        text = text.lower().strip()
        
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Remove special characters but keep Turkish chars
        text = re.sub(r'[^\w\sçğıöşüÇĞIÖŞÜ]', ' ', text)
        
        # Remove numbers unless they seem important
        text = re.sub(r'\b\d+\b', '', text)
        
        # Final cleanup
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    def preprocess(self, text: str) -> str:
        """Complete preprocessing pipeline"""
        cleaned = self.clean_text(text)
        normalized = self.normalize_turkish(cleaned)
        return normalized

class TurkishBERTIntentClassifier:
    """Turkish BERT-based intent classifier for IVR responses"""
    
    def __init__(self, config: ModelConfig = None):
        """
        Initialize Turkish BERT intent classifier
        
        Args:
            config: Model configuration
        """
        self.config = config or ModelConfig()
        self.preprocessor = TurkishTextPreprocessor()
        
        # Model components
        self.tokenizer = None
        self.model = None
        self.classifier = None
        
        # Intent mapping
        self.intent_labels = {}
        self.label_to_intent = {}
        
        # Training data
        self.training_data = None
        
        logger.info("Turkish BERT Intent Classifier initialized", 
                   model_name=self.config.model_name,
                   device=self.config.device)
    
    def load_model(self) -> bool:
        """Load Turkish BERT model and tokenizer"""
        if not BERT_AVAILABLE:
            logger.error("BERT dependencies not available. Install: transformers, torch")
            return False
        
        try:
            logger.info("Loading Turkish BERT model", model=self.config.model_name)
            
            # Create cache directory
            os.makedirs(self.config.cache_dir, exist_ok=True)
            
            # Load tokenizer
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.config.model_name,
                cache_dir=self.config.cache_dir
            )
            
            # Load model
            self.model = AutoModelForSequenceClassification.from_pretrained(
                self.config.model_name,
                cache_dir=self.config.cache_dir,
                num_labels=len(self.intent_labels) if self.intent_labels else 8  # Default labels
            )
            
            # Set to evaluation mode and CPU
            self.model.eval()
            if self.config.device == "cpu":
                self.model = self.model.to("cpu")
            
            logger.info("Turkish BERT model loaded successfully")
            return True
            
        except Exception as e:
            logger.error("Failed to load Turkish BERT model", error=str(e))
            return False
    
    def create_default_intents(self):
        """Create default IVR intent categories for Turkish banking"""
        self.intent_labels = {
            "hesap_bakiye": 0,          # Account balance inquiry
            "kart_islemleri": 1,        # Card operations
            "kredi_bilgi": 2,           # Credit information
            "para_transferi": 3,        # Money transfer
            "musteri_hizmetleri": 4,    # Customer service
            "sikayet": 5,               # Complaint
            "genel_bilgi": 6,           # General information
            "diger": 7                  # Other/unknown
        }
        
        self.label_to_intent = {v: k for k, v in self.intent_labels.items()}
        
        logger.info("Default Turkish IVR intents created", 
                   intent_count=len(self.intent_labels))
    
    def load_training_data(self, data_path: str) -> bool:
        """Load training data for intent classification"""
        try:
            if not os.path.exists(data_path):
                logger.warning("Training data not found, using defaults", path=data_path)
                self._create_sample_training_data()
                return True
            
            with open(data_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Convert to lists for easier handling
            texts = []
            labels = []
            
            for intent, examples in data.items():
                if isinstance(examples, list):
                    for example in examples:
                        texts.append(example)
                        labels.append(intent)
                elif isinstance(examples, dict) and 'examples' in examples:
                    for example in examples['examples']:
                        texts.append(example)
                        labels.append(intent)
            
            # Create DataFrame if pandas is available, otherwise use dict
            if pd is not None:
                self.training_data = pd.DataFrame({
                    'text': texts,
                    'intent': labels
                })
                unique_intents = self.training_data['intent'].unique()
            else:
                self.training_data = {'texts': texts, 'intents': labels}
                unique_intents = list(set(labels))
            
            # Update intent labels
            self.intent_labels = {intent: i for i, intent in enumerate(unique_intents)}
            self.label_to_intent = {v: k for k, v in self.intent_labels.items()}
            
            logger.info("Training data loaded", 
                       samples=len(texts),
                       intents=len(self.intent_labels))
            return True
            
        except Exception as e:
            logger.error("Failed to load training data", error=str(e))
            return False
    
    def _create_sample_training_data(self):
        """Create sample training data for Turkish IVR intents"""
        sample_data = {
            "hesap_bakiye": [
                "hesap bakiyemi öğrenmek istiyorum",
                "bakiyemi kontrol etmek istiyorum",
                "hesabımda ne kadar param var",
                "para durumum nasıl",
                "hesapta kaç lira var",
                "bakiye sorgulama yapmak istiyorum"
            ],
            "kart_islemleri": [
                "kartımı kaybettim",
                "kart bloke etmek istiyorum",
                "kart şifremi unuttum",
                "yeni kart talep etmek istiyorum",
                "kart limiti öğrenmek istiyorum",
                "kart işlemlerim hakkında bilgi"
            ],
            "kredi_bilgi": [
                "kredi başvurusu yapmak istiyorum",
                "kredi faiz oranları nedir",
                "kredi borcum ne kadar",
                "kredi taksit bilgisi",
                "konut kredisi hakkında bilgi",
                "ihtiyaç kredisi başvurusu"
            ],
            "para_transferi": [
                "para transferi yapmak istiyorum",
                "havale göndermek istiyorum",
                "EFT işlemi yapmak istiyorum",
                "başka hesaba para göndermek",
                "transfer limiti öğrenmek",
                "havale ücreti ne kadar"
            ],
            "musteri_hizmetleri": [
                "müşteri temsilcisi ile görüşmek istiyorum",
                "canlı destek",
                "operatör bağlamak",
                "temsilci ile konuşmak",
                "müşteri hizmetleri",
                "insan ile konuşmak istiyorum"
            ],
            "sikayet": [
                "şikayet etmek istiyorum",
                "sorun yaşıyorum",
                "memnun değilim",
                "şikayetim var",
                "problem bildirmek istiyorum",
                "hizmetinizden şikayetçiyim"
            ],
            "genel_bilgi": [
                "çalışma saatleri nedir",
                "şube bilgisi",
                "ATM nerede",
                "faiz oranları",
                "ürün bilgisi",
                "hizmet bilgisi almak istiyorum"
            ]
        }
        
        texts = []
        labels = []
        
        for intent, examples in sample_data.items():
            for example in examples:
                texts.append(example)
                labels.append(intent)
        
        self.training_data = pd.DataFrame({
            'text': texts,
            'intent': labels
        })
        
        # Update intent labels
        unique_intents = self.training_data['intent'].unique()
        self.intent_labels = {intent: i for i, intent in enumerate(unique_intents)}
        self.label_to_intent = {v: k for k, v in self.intent_labels.items()}
        
        logger.info("Sample training data created", 
                   samples=len(self.training_data),
                   intents=len(self.intent_labels))
    
    def initialize(self, training_data_path: str = None) -> bool:
        """Initialize the classifier with model and training data"""
        try:
            # Load training data
            if training_data_path:
                success = self.load_training_data(training_data_path)
            else:
                self.create_default_intents()
                self._create_sample_training_data()
                success = True
            
            if not success:
                return False
            
            # Load model
            if not self.load_model():
                return False
            
            # Create pipeline for inference
            self.classifier = pipeline(
                "text-classification",
                model=self.model,
                tokenizer=self.tokenizer,
                device=-1 if self.config.device == "cpu" else 0,
                return_all_scores=True
            )
            
            logger.info("Turkish BERT Intent Classifier initialized successfully")
            return True
            
        except Exception as e:
            logger.error("Failed to initialize classifier", error=str(e))
            return False
    
    def predict_intent(self, text: str) -> IntentPrediction:
        """
        Predict intent for given text
        
        Args:
            text: Input text to classify
            
        Returns:
            IntentPrediction with result details
        """
        if not self.classifier:
            raise RuntimeError("Classifier not initialized. Call initialize() first.")
        
        try:
            # Preprocess text
            preprocessed_text = self.preprocessor.preprocess(text)
            
            if not preprocessed_text:
                return IntentPrediction(
                    intent="diger",
                    confidence=0.0,
                    raw_scores={},
                    preprocessed_text=""
                )
            
            # Get predictions
            results = self.classifier(preprocessed_text)
            
            # Parse results
            raw_scores = {}
            max_score = 0.0
            predicted_label = None
            
            for result in results[0]:  # results is list of lists
                label = result['label']
                score = result['score']
                
                # Map LABEL_X to intent name
                if label.startswith('LABEL_'):
                    label_idx = int(label.split('_')[1])
                    intent_name = self.label_to_intent.get(label_idx, "diger")
                else:
                    intent_name = label
                
                raw_scores[intent_name] = score
                
                if score > max_score:
                    max_score = score
                    predicted_label = intent_name
            
            # Determine final intent
            if max_score < self.config.confidence_threshold:
                predicted_intent = "diger"
                confidence = max_score
            else:
                predicted_intent = predicted_label
                confidence = max_score
            
            return IntentPrediction(
                intent=predicted_intent,
                confidence=confidence,
                raw_scores=raw_scores,
                preprocessed_text=preprocessed_text
            )
            
        except Exception as e:
            logger.error("Intent prediction failed", error=str(e), text=text)
            return IntentPrediction(
                intent="diger",
                confidence=0.0,
                raw_scores={},
                preprocessed_text=preprocessed_text if 'preprocessed_text' in locals() else text
            )
    
    def batch_predict(self, texts: List[str]) -> List[IntentPrediction]:
        """Predict intents for multiple texts"""
        return [self.predict_intent(text) for text in texts]
    
    def get_supported_intents(self) -> Dict[str, Dict[str, Any]]:
        """Get list of supported intents with metadata"""
        intent_info = {}
        
        for intent, label in self.intent_labels.items():
            intent_info[intent] = {
                "label": label,
                "display_name": intent.replace('_', ' ').title(),
                "description": f"Turkish IVR intent: {intent}",
                "confidence_threshold": self.config.confidence_threshold
            }
        
        return intent_info
    
    def validate_prediction(self, prediction: IntentPrediction, expected_intent: str) -> bool:
        """
        Validate if prediction matches expected intent
        
        Args:
            prediction: Intent prediction result
            expected_intent: Expected intent for validation
            
        Returns:
            True if prediction is valid
        """
        if prediction.confidence < self.config.confidence_threshold:
            return False
        
        return prediction.intent == expected_intent
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get model information and statistics"""
        return {
            "model_name": self.config.model_name,
            "device": self.config.device,
            "confidence_threshold": self.config.confidence_threshold,
            "supported_intents": list(self.intent_labels.keys()),
            "intent_count": len(self.intent_labels),
            "training_samples": len(self.training_data) if self.training_data is not None else 0,
            "model_loaded": self.model is not None,
            "classifier_ready": self.classifier is not None
        }