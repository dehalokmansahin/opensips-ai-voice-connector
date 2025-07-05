# Pytest configuration.
# Ensures src/ and pipecat/src are on sys.path and stubs optional binaries.

import sys
import os
from pathlib import Path
import types

# Proje root klasörünü bul
project_root = Path(__file__).parent.parent

# src ve pipecat/src klasörlerini Python path'ine ekle
src_path = str(project_root / "src")
pipecat_src_path = str(project_root / "pipecat" / "src")

if src_path not in sys.path:
    sys.path.insert(0, src_path)
if pipecat_src_path not in sys.path:
    sys.path.insert(0, pipecat_src_path)

print(f"Added to Python path:")
print(f"  - {src_path}")
print(f"  - {pipecat_src_path}")

# NumPy 2.x compatibility: soxr binary wheel stub
# soxr modülü NumPy 1.x ile compile edilmiş, NumPy 2.x ile uyumsuz
# Bu nedenle mock bir soxr modülü oluşturuyoruz

def create_soxr_stub():
    """soxr modülü için stub oluştur"""
    soxr_module = types.ModuleType('soxr')
    
    # Mock cysoxr submodule
    cysoxr_module = types.ModuleType('cysoxr')
    soxr_module.cysoxr = cysoxr_module
    
    # Mock functions that might be used
    def resample(input_array, input_rate, output_rate, **kwargs):
        """Mock resample function - basit linear interpolation"""
        import numpy as np
        if len(input_array) == 0:
            return np.array([])
        
        # Basit upsampling/downsampling
        ratio = output_rate / input_rate
        output_length = int(len(input_array) * ratio)
        
        if output_length == 0:
            return np.array([])
        
        # Linear interpolation
        indices = np.linspace(0, len(input_array) - 1, output_length)
        return np.interp(indices, np.arange(len(input_array)), input_array)
    
    soxr_module.resample = resample
    
    return soxr_module

# soxr modülünü sys.modules'e ekle
if 'soxr' not in sys.modules:
    sys.modules['soxr'] = create_soxr_stub()
    print("✅ soxr stub module created for NumPy 2.x compatibility")

# Pipecat version fallback
try:
    import pipecat
    if not hasattr(pipecat, '__version__'):
        pipecat.__version__ = "0.0.0"
except ImportError:
    pass