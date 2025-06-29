# Ollama Performance Optimization Guide

## 🚀 Immediate Optimizations

### 1. Model Selection
```bash
# Test smaller models for faster inference
ollama pull llama3.2:1b     # 1B parameters (vs 3B)
ollama pull qwen2.5:0.5b    # 0.5B parameters (ultra-fast)
ollama pull phi3:mini       # Microsoft Phi-3 Mini
```

### 2. Ollama Configuration
```bash
# Set environment variables for performance
export OLLAMA_NUM_PARALLEL=4        # Parallel requests
export OLLAMA_MAX_LOADED_MODELS=2   # Keep models in memory
export OLLAMA_FLASH_ATTENTION=1     # Enable flash attention
export OLLAMA_HOST=0.0.0.0:11434    # Bind to all interfaces
```

### 3. System-level Optimizations
```bash
# Windows PowerShell - Set high priority
$Process = Get-Process "ollama"
$Process.PriorityClass = "High"

# Increase memory allocation
$env:OLLAMA_MAX_VRAM = "8GB"
```

### 4. Model-specific Parameters
```python
# In OllamaLLMService
payload = {
    "model": "llama3.2:1b",  # Smaller model
    "prompt": full_prompt,
    "stream": True,
    "options": {
        "temperature": 0.3,      # Lower for consistency
        "top_p": 0.8,           # Reduce for speed  
        "max_tokens": 50,       # Shorter responses
        "num_predict": 50,      # Limit prediction length
        "num_ctx": 1024,        # Smaller context window
        "num_thread": 8,        # CPU threads
        "repeat_penalty": 1.1,
        "stop": ["\\nKullanıcı:", "\\n\\n", ".", "!", "?"]  # Early stopping
    }
}
```

## 📊 Expected Performance Gains

| Optimization | First Token Latency | Total Response |
|-------------|-------------------|----------------|
| Current (3B) | 500-1500ms | 1500-3000ms |
| Smaller Model (1B) | 200-600ms | 800-1500ms |
| Optimized Config | 150-400ms | 500-1000ms |
| **Target Achievement** | **≤400ms** | **≤1000ms** |

## 🎯 Implementation Priority

1. **Switch to 1B model** (immediate 50-70% speedup)
2. **Optimize parameters** (20-30% additional gain)  
3. **System tuning** (10-20% final gain)
4. **GPU acceleration** (if available - 80%+ gain)

## ⚡ Quick Test Commands

```bash
# Test 1B model
ollama run llama3.2:1b "Merhaba nasılsın?"

# Benchmark different models
time ollama run llama3.2:1b "Test response"
time ollama run qwen2.5:0.5b "Test response"
``` 