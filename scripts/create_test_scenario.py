#!/usr/bin/env python3
"""
Basit IVR Test Senaryosu Oluşturma Scripti
Türk bankası çağrı merkezi bakiye sorgulama akışı test senaryosu
"""

import json
import sys
import os
import sqlite3
from datetime import datetime
from pathlib import Path

# Core modüllerini kullanabilmek için path'e ekle
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'core'))

def create_database():
    """Test senaryoları için SQLite veritabanı oluştur"""
    db_path = Path("data/test_controller/test_scenarios.db")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Senaryolar tablosu
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS scenarios (
            scenario_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            tags TEXT,
            steps TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Çalıştırmalar tablosu
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS executions (
            execution_id TEXT PRIMARY KEY,
            scenario_id TEXT,
            status TEXT DEFAULT 'pending',
            start_time TIMESTAMP,
            end_time TIMESTAMP,
            results TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (scenario_id) REFERENCES scenarios (scenario_id)
        )
    ''')
    
    conn.commit()
    conn.close()
    
    print(f"[OK] Veritabani olusturuldu: {db_path}")

def create_balance_inquiry_scenario():
    """Türk bankası bakiye sorgulama IVR test senaryosu oluştur"""
    
    scenario = {
        "scenario_id": "balance_inquiry_basic_001",
        "name": "Basit Bakiye Sorgulama Testi",
        "description": "Türk bankası çağrı merkezi bakiye sorgulama akışı temel test senaryosu",
        "tags": ["banking", "balance", "turkish", "basic"],
        "steps": [
            {
                "step_number": 1,
                "step_type": "tts_prompt",
                "prompt_text": "Merhaba, X Bankası çağrı merkezine hoş geldiniz. Bakiye sorgulamak için 1'e basınız.",
                "timeout_ms": 5000,
                "wait_for_response": True
            },
            {
                "step_number": 2,
                "step_type": "dtmf_send",
                "dtmf_sequence": "1",
                "timeout_ms": 1000
            },
            {
                "step_number": 3,
                "step_type": "tts_prompt", 
                "prompt_text": "Lütfen TC kimlik numaranızı giriniz ve ardından diyez tuşuna basınız.",
                "timeout_ms": 10000,
                "wait_for_response": True
            },
            {
                "step_number": 4,
                "step_type": "dtmf_send",
                "dtmf_sequence": "12345678901#",
                "timeout_ms": 2000
            },
            {
                "step_number": 5,
                "step_type": "tts_prompt",
                "prompt_text": "Bakiye bilginiz için lütfen bekleyiniz.",
                "timeout_ms": 3000
            },
            {
                "step_number": 6,
                "step_type": "tts_prompt",
                "prompt_text": "Vadesiz hesap bakiyeniz 1500 TL'dir. Ana menüye dönmek için 0'a basınız.",
                "timeout_ms": 5000
            },
            {
                "step_number": 7,
                "step_type": "dtmf_send",
                "dtmf_sequence": "0",
                "timeout_ms": 1000
            }
        ]
    }
    
    return scenario

def create_intent_validation_scenario():
    """Intent doğrulama içeren gelişmiş senaryo"""
    
    scenario = {
        "scenario_id": "intent_validation_001", 
        "name": "Intent Doğrulama Testi",
        "description": "Müşteri konuşmasını anlayıp uygun yanıt verme testi",
        "tags": ["intent", "asr", "turkish", "advanced"],
        "steps": [
            {
                "step_number": 1,
                "step_type": "tts_prompt",
                "prompt_text": "Merhaba, size nasıl yardımcı olabilirim? Lütfen isteğinizi söyleyiniz.",
                "timeout_ms": 8000,
                "wait_for_response": True
            },
            {
                "step_number": 2,
                "step_type": "asr_listen",
                "max_duration_ms": 5000,
                "expected_intent": "hesap_bakiye_sorgulama",
                "confidence_threshold": 0.7
            },
            {
                "step_number": 3,
                "step_type": "intent_validate",
                "pass_criteria": "intent_matches",
                "timeout_ms": 1000
            },
            {
                "step_number": 4,
                "step_type": "tts_prompt",
                "prompt_text": "Bakiye sorgulamanızı anlıyorum. TC kimlik numaranızı söyleyebilir misiniz?",
                "timeout_ms": 5000
            }
        ]
    }
    
    return scenario

def save_scenario_to_db(scenario):
    """Senaryoyu veritabanına kaydet"""
    db_path = Path("data/test_controller/test_scenarios.db")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT OR REPLACE INTO scenarios 
            (scenario_id, name, description, tags, steps, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            scenario["scenario_id"],
            scenario["name"], 
            scenario["description"],
            ",".join(scenario["tags"]),
            json.dumps(scenario["steps"], ensure_ascii=False),
            datetime.now().isoformat()
        ))
        
        conn.commit()
        print(f"[OK] Senaryo kaydedildi: {scenario['scenario_id']} - {scenario['name']}")
        
    except Exception as e:
        print(f"[ERROR] Senaryo kaydetme hatasi: {e}")
        
    finally:
        conn.close()

def main():
    """Ana fonksiyon"""
    print("IVR Test Senaryolari Olusturuluyor...")
    
    # Veritabanı oluştur
    create_database()
    
    # Temel bakiye sorgulama senaryosu
    balance_scenario = create_balance_inquiry_scenario()
    save_scenario_to_db(balance_scenario)
    
    # Intent doğrulama senaryosu  
    intent_scenario = create_intent_validation_scenario()
    save_scenario_to_db(intent_scenario)
    
    print("\nOlusturulan senaryolar:")
    print(f"1. {balance_scenario['name']} ({balance_scenario['scenario_id']})")
    print(f"2. {intent_scenario['name']} ({intent_scenario['scenario_id']})")
    
    print("\nTest senaryolari basariyla olusturuldu!")
    print("Test Controller Service ile senaryolari calistirabilirsiniz.")

if __name__ == "__main__":
    main()