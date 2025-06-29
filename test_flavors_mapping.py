#!/usr/bin/env python3
"""
FLAVORS mapping test scripti
"""

import sys
from pathlib import Path

# Path setup
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "pipecat" / "src"))
sys.path.insert(0, str(project_root / "tests"))
import conftest

def test_flavors_mapping():
    """FLAVORS mapping'ini test et"""
    
    print("🔧 FLAVORS Mapping Test")
    print("=" * 40)
    
    try:
        from utils import FLAVORS, list_available_flavors, get_ai_engine_class
        
        print(f"📋 Available AI Flavors: {list_available_flavors()}")
        
        for flavor in list_available_flavors():
            try:
                engine_class = get_ai_engine_class(flavor)
                print(f"✅ {flavor}: {engine_class.__name__}")
            except Exception as e:
                print(f"❌ {flavor}: {e}")
        
        # Pipecat flavor'ını özellikle test et
        if 'pipecat' in list_available_flavors():
            print("\n🎯 Pipecat Flavor Test:")
            pipecat_class = get_ai_engine_class('pipecat')
            print(f"✅ Pipecat class: {pipecat_class}")
            print(f"✅ Class name: {pipecat_class.__name__}")
            print(f"✅ Module: {pipecat_class.__module__}")
        else:
            print("\n❌ Pipecat flavor not available!")
        
        return True
        
    except Exception as e:
        print(f"❌ FLAVORS mapping test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_config_loading():
    """Config loading test"""
    
    print("\n⚙️ Config Loading Test")
    print("=" * 40)
    
    try:
        from utils import load_config
        
        cfg_file = Path("cfg/opensips-ai-voice-connector.ini")
        
        if cfg_file.exists():
            cfg = load_config(str(cfg_file))
            print(f"✅ Config loaded successfully")
            print(f"📋 AI Flavor: {cfg.ai_flavor}")
            print(f"📋 AI Model: {cfg.ai_model}")
            print(f"📋 Sample Rate: {cfg.sample_rate}")
            print(f"📋 Vosk URL: {cfg.vosk_url}")
            return True
        else:
            print(f"❌ Config file not found: {cfg_file}")
            return False
            
    except Exception as e:
        print(f"❌ Config loading failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 OpenSIPS AI Flavors & Config Test")
    print("=" * 50)
    
    flavors_ok = test_flavors_mapping()
    config_ok = test_config_loading()
    
    print("\n📊 Test Results:")
    print(f"  FLAVORS Mapping: {'✅' if flavors_ok else '❌'}")
    print(f"  Config Loading: {'✅' if config_ok else '❌'}")
    
    if flavors_ok and config_ok:
        print("\n🎉 All tests passed! OpenSIPS integration ready!")
    else:
        print("\n⚠️ Some tests failed. Check the issues above.") 