#!/usr/bin/env python3
"""
Simple import test for OpenSIPS AI Voice Connector enhancements
"""

def test_config_import():
    """Test config module import"""
    try:
        from src.config import Config, ConfigValidationError, ServiceConfigValidator
        print("✅ Config module imported successfully")
        print(f"   - Config class: {Config}")
        print(f"   - ConfigValidationError: {ConfigValidationError}")
        print(f"   - ServiceConfigValidator: {ServiceConfigValidator}")
        return True
    except Exception as e:
        print(f"❌ Config import failed: {e}")
        return False

def test_pipeline_manager_import():
    """Test enhanced pipeline manager import"""
    try:
        from src.pipeline.manager import EnhancedPipelineManager, PipelineError
        print("✅ Enhanced Pipeline Manager imported successfully")
        print(f"   - EnhancedPipelineManager: {EnhancedPipelineManager}")
        print(f"   - PipelineError: {PipelineError}")
        return True
    except Exception as e:
        print(f"❌ Pipeline Manager import failed: {e}")
        import traceback
        print(f"   Full traceback: {traceback.format_exc()}")
        return False

def test_main_imports():
    """Test main application imports"""
    try:
        # Test key imports from main.py
        import sys
        sys.path.insert(0, 'src')
        
        from config import Config
        print("✅ Main config import successful")
        return True
    except Exception as e:
        print(f"❌ Main imports failed: {e}")
        return False

def main():
    """Run all import tests"""
    print("🧪 Starting OpenSIPS AI Voice Connector Import Tests...")
    print("=" * 60)
    
    tests = [
        ("Config Module", test_config_import),
        ("Pipeline Manager", test_pipeline_manager_import),
        ("Main Imports", test_main_imports)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n📋 Testing {test_name}:")
        print("-" * 30)
        if test_func():
            passed += 1
        print()
    
    print("=" * 60)
    print(f"🎯 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All imports successful! OpenSIPS enhancements are ready.")
    else:
        print("⚠️ Some imports failed. Check the errors above.")
    
    return passed == total

if __name__ == "__main__":
    main() 