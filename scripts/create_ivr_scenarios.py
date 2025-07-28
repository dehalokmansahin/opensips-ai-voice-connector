#!/usr/bin/env python3
"""
IVR Test Senaryoları - ScenarioManager uyumlu
Türk bankası çağrı merkezi test senaryoları
"""

import json
import sys
import os
from datetime import datetime
from pathlib import Path

# Core modüllerini kullanabilmek için path'e ekle
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'core'))

from ivr_testing.scenario_manager import ScenarioManager
from ivr_testing.scenario_manager import TestScenario, TestStep

def create_simple_ivr_scenario():
    """Basit IVR test senaryosu oluştur"""
    
    steps = [
        TestStep(
            step_number=1,
            step_type="tts_prompt",
            prompt_text="Bankamiza hos geldiniz. Bakiye sorgulamak icin 1'e basiniz.",
            timeout_ms=5000,
            wait_for_response=True
        ),
        TestStep(
            step_number=2,
            step_type="dtmf_send",
            dtmf_sequence="1",
            timeout_ms=1000
        ),
        TestStep(
            step_number=3,
            step_type="tts_prompt",
            prompt_text="TC kimlik numaranizi giriniz ve diyez tusuna basiniz.",
            timeout_ms=10000,
            wait_for_response=True
        ),
        TestStep(
            step_number=4,
            step_type="dtmf_send",
            dtmf_sequence="12345678901#",
            timeout_ms=2000
        ),
        TestStep(
            step_number=5,
            step_type="tts_prompt",
            prompt_text="Hesap bakiyeniz 1500 TL'dir. Tesekkur ederiz.",
            timeout_ms=3000
        )
    ]
    
    scenario = TestScenario(
        scenario_id="simple_balance_001",
        name="Basit Bakiye Sorgulama",
        description="Temel bakiye sorgulama IVR akisi testi",
        target_phone="+905551234567",
        timeout_seconds=60,
        steps=steps,
        created_by="test_system",
        tags=["banking", "balance", "basic"]
    )
    
    return scenario

def create_intent_based_scenario():
    """Intent tabanlı gelişmiş senaryo"""
    
    steps = [
        TestStep(
            step_number=1,
            step_type="tts_prompt",
            prompt_text="Size nasil yardimci olabilirim? Lutfen isteginizi soyleyiniz.",
            timeout_ms=8000,
            wait_for_response=True
        ),
        TestStep(
            step_number=2,
            step_type="asr_listen",
            max_duration_ms=5000,
            expected_intent="hesap_bakiye_sorgulama",
            confidence_threshold=0.7
        ),
        TestStep(
            step_number=3,
            step_type="intent_validate",
            pass_criteria="intent_matches",
            timeout_ms=1000
        ),
        TestStep(
            step_number=4,
            step_type="tts_prompt",
            prompt_text="Bakiye sorgulamanizi anliyorum. Bilgileriniz isleniyor...",
            timeout_ms=3000
        ),
        TestStep(
            step_number=5,
            step_type="tts_prompt",
            prompt_text="Hesap bakiyeniz 2750 TL'dir.",
            timeout_ms=3000
        )
    ]
    
    scenario = TestScenario(
        scenario_id="intent_balance_002",
        name="Intent Tabanli Bakiye Sorgulama",
        description="ASR ve intent recognition kullanan gelismis senaryo",
        target_phone="+905551234567",
        timeout_seconds=45,
        steps=steps,
        created_by="test_system",
        tags=["banking", "intent", "asr", "advanced"]
    )
    
    return scenario

def create_dtmf_menu_scenario():
    """DTMF menü navigasyon senaryosu"""
    
    steps = [
        TestStep(
            step_number=1,
            step_type="tts_prompt",
            prompt_text="Ana menu: Bakiye icin 1, Havale icin 2, Musteri hizmetleri icin 0'a basiniz.",
            timeout_ms=8000,
            wait_for_response=True
        ),
        TestStep(
            step_number=2,
            step_type="dtmf_send",
            dtmf_sequence="1",
            timeout_ms=1000
        ),
        TestStep(
            step_number=3,
            step_type="tts_prompt",
            prompt_text="Bakiye menu: Vadesiz hesap icin 1, Vadeli hesap icin 2'ye basiniz.",
            timeout_ms=6000,
            wait_for_response=True
        ),
        TestStep(
            step_number=4,
            step_type="dtmf_send",
            dtmf_sequence="1",
            timeout_ms=1000
        ),
        TestStep(
            step_number=5,
            step_type="tts_prompt",
            prompt_text="Vadesiz hesap bakiyeniz 3200 TL'dir. Ana menu icin 9'a basiniz.",
            timeout_ms=5000,
            wait_for_response=True
        ),
        TestStep(
            step_number=6,
            step_type="dtmf_send",
            dtmf_sequence="9",
            timeout_ms=1000
        )
    ]
    
    scenario = TestScenario(
        scenario_id="dtmf_navigation_003",
        name="DTMF Menu Navigasyonu",
        description="Karmasik DTMF menu yapisi test senaryosu",
        target_phone="+905551234567",
        timeout_seconds=90,
        steps=steps,
        created_by="test_system",
        tags=["banking", "dtmf", "navigation", "menu"]
    )
    
    return scenario

def main():
    """Ana fonksiyon"""
    print("IVR Test Senaryolari Olusturuluyor...")
    
    # Test Controller Service ile uyumlu veritabanı yolu
    db_path = "data/test_controller/test_scenarios.db"
    Path("data/test_controller").mkdir(parents=True, exist_ok=True)
    
    # ScenarioManager ile senaryoları kaydet
    scenario_manager = ScenarioManager(db_path=db_path)
    
    scenarios = [
        create_simple_ivr_scenario(),
        create_intent_based_scenario(),
        create_dtmf_menu_scenario()
    ]
    
    saved_count = 0
    for scenario in scenarios:
        try:
            if scenario_manager.save_scenario(scenario):
                print(f"[OK] Senaryo kaydedildi: {scenario.scenario_id} - {scenario.name}")
                saved_count += 1
            else:
                print(f"[ERROR] Senaryo kaydedilemedi: {scenario.scenario_id}")
        except Exception as e:
            print(f"[ERROR] Senaryo kaydetme hatasi ({scenario.scenario_id}): {e}")
    
    print(f"\nToplam {saved_count} senaryo basariyla kaydedildi.")
    
    # Senaryoları listele
    try:
        loaded_scenarios = scenario_manager.list_scenarios()
        print(f"\nVeritabaninda toplam {len(loaded_scenarios)} senaryo bulundu:")
        for scenario_info in loaded_scenarios:
            print(f"- {scenario_info['scenario_id']}: {scenario_info['name']}")
    except Exception as e:
        print(f"[ERROR] Senaryolar listelenemedi: {e}")

if __name__ == "__main__":
    main()