#!/usr/bin/env python3
"""
Development Environment Validation Script
Simple validation of the OpenSIPS AI Voice Connector development environment
"""

import subprocess
import sys
import os
from pathlib import Path

def run_command(cmd, description):
    """Run a command and return success status"""
    try:
        print(f"Testing: {description}")
        # Use cmd.exe for Windows compatibility
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30, 
                              executable='cmd.exe' if os.name == 'nt' else None)
        if result.returncode == 0:
            print(f"  SUCCESS: {description}")
            if result.stdout.strip():
                print(f"  Output: {result.stdout.strip()}")
            return True
        else:
            print(f"  FAILED: {description}")
            if result.stderr.strip():
                print(f"  Error: {result.stderr.strip()}")
            return False
    except subprocess.TimeoutExpired:
        print(f"  TIMEOUT: {description}")
        return False
    except Exception as e:
        print(f"  EXCEPTION: {description} - {e}")
        return False

def check_directory_structure():
    """Check if required directories exist"""
    required_dirs = [
        "core",
        "services/asr-service",
        "services/llm-service", 
        "services/tts-service",
        "models/vosk",
        "models/llm",
        "models/piper",
        "logs",
        "config"
    ]
    
    print("\nDirectory Structure Validation")
    all_good = True
    for dir_path in required_dirs:
        if Path(dir_path).exists():
            print(f"  EXISTS: {dir_path}")
        else:
            print(f"  MISSING: {dir_path}")
            all_good = False
    
    return all_good

def check_docker_services():
    """Check Docker installation and built images"""
    print("\nDocker Environment Validation")
    
    results = []
    
    # Check Docker daemon
    results.append(run_command("docker version --format '{{.Server.Version}}'", "Docker daemon"))
    
    # Check Docker Compose
    results.append(run_command("docker-compose version --short", "Docker Compose"))
    
    # Check built images
    results.append(run_command("docker images opensips-asr-service --format 'table {{.Repository}}:{{.Tag}}\t{{.Size}}'", "ASR service image"))
    results.append(run_command("docker images opensips-tts-service --format 'table {{.Repository}}:{{.Tag}}\t{{.Size}}'", "TTS service image"))
    
    return all(results)

def check_python_environment():
    """Check Python environment"""
    print("\nPython Environment Validation")
    
    results = []
    
    # Check Python version
    results.append(run_command("python --version", "Python installation"))
    
    # Check if we can import core modules
    core_test_script = '''
import sys
import os
sys.path.insert(0, "core")

try:
    from config.settings import Settings
    print("Settings module imported")
    
    from utils.logging import setup_logging
    print("Logging module imported")
    
    print("Core modules available")
except Exception as e:
    print(f"Core module import failed: {e}")
    sys.exit(1)
'''
    
    with open("temp_core_test.py", "w") as f:
        f.write(core_test_script)
    
    result = run_command("python temp_core_test.py", "Core module imports")
    
    # Clean up
    try:
        os.remove("temp_core_test.py")
    except:
        pass
    
    results.append(result)
    
    return all(results)

def check_configuration():
    """Check configuration files"""
    print("\nConfiguration Validation")
    
    results = []
    
    # Check main config file
    config_file = Path("config/app.ini")
    if config_file.exists():
        print("  EXISTS: config/app.ini")
        results.append(True)
    else:
        print("  MISSING: config/app.ini")
        results.append(False)
    
    # Check docker-compose file
    compose_file = Path("docker-compose.yml")
    if compose_file.exists():
        print("  EXISTS: docker-compose.yml")
        results.append(True)
    else:
        print("  MISSING: docker-compose.yml")
        results.append(False)
    
    return all(results)

def main():
    """Main validation function"""
    print("OpenSIPS AI Voice Connector - Development Environment Validation")
    print("=" * 70)
    
    # Change to project root
    project_root = Path(__file__).parent
    os.chdir(project_root)
    print(f"Working directory: {project_root.absolute()}")
    
    # Run all checks
    checks = [
        ("Directory Structure", check_directory_structure),
        ("Docker Environment", check_docker_services),
        ("Python Environment", check_python_environment),
        ("Configuration", check_configuration),
    ]
    
    results = []
    for name, check_func in checks:
        try:
            result = check_func()
            results.append(result)
        except Exception as e:
            print(f"\nError in {name}: {e}")
            results.append(False)
    
    # Summary
    print("\n" + "=" * 70)
    print("Validation Summary")
    print("=" * 70)
    
    passed = sum(results)
    total = len(results)
    
    for i, (name, _) in enumerate(checks):
        status = "PASS" if results[i] else "FAIL"
        print(f"  {status} {name}")
    
    print(f"\nOverall: {passed}/{total} checks passed")
    
    if passed == total:
        print("Development environment validation successful!")
        print("\nNext steps:")
        print("1. Download required model files (Vosk, LLaMA, Piper)")
        print("2. Fix service import issues")
        print("3. Start services with docker-compose")
        return 0
    else:
        print("Development environment has issues that need to be resolved.")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)