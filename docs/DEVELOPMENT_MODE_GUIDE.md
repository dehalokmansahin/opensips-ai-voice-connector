# Development Mode Guide

This guide explains how to use the enhanced development environment with hot-reload capabilities for the OpenSIPS AI Voice Connector.

## Quick Start

```bash
# Start development environment
./scripts/dev-start.sh

# Check status
./scripts/dev-status.sh

# View logs
./scripts/dev-logs.sh

# Stop environment
./scripts/dev-stop.sh
```

## Features

### 🔥 Hot-Reload (30-second target)
- **Automatic code reload**: Changes to Python files trigger automatic service restart
- **Fast startup**: Optimized Docker builds with caching
- **Volume mounting**: Source code is mounted for immediate changes
- **Debounced restarts**: Multiple rapid changes are batched together

### 🐛 Enhanced Debugging
- **Colored console output**: Development logs are color-coded for easy reading
- **Detailed stack traces**: Enhanced exception handling with local variable inspection
- **Debug logging**: All services run with DEBUG level logging
- **Development loggers**: Special debugging utilities for state inspection

### ⚡ Performance Optimizations
- **Parallel builds**: Services build simultaneously for faster startup
- **Docker layer caching**: Optimized Dockerfile layers for quick rebuilds
- **Pip caching**: Python packages are cached between builds
- **Health check optimization**: Faster health checks in development

## Development Environment Structure

```
docker-compose.yml          # Base production configuration
docker-compose.dev.yml      # Development overrides
docker-compose.prod.yml     # Production overrides
```

### Development Compose Override Features

1. **Volume Mounting**:
   ```yaml
   volumes:
     - ./core:/app/core:rw              # Core application code
     - ./services/asr-service/src:/app/src:rw  # Service source code
     - ./shared/proto_generated:/app/shared:ro # Shared protocol files
   ```

2. **Environment Variables**:
   ```yaml
   environment:
     - DEVELOPMENT_MODE=1
     - LOG_LEVEL=DEBUG
     - PYTHONUNBUFFERED=1
     - PYTHONDONTWRITEBYTECODE=1
     - *_HOT_RELOAD=1
   ```

3. **Optimized Health Checks**:
   ```yaml
   healthcheck:
     interval: 15s     # Faster than production (30s)
     timeout: 5s       # Faster than production (10s)
     retries: 2        # Fewer than production (3)
     start_period: 20s # Faster than production (40s)
   ```

## Development Scripts

### Core Scripts

| Script | Purpose | Usage |
|--------|---------|-------|
| `dev-start.sh` | Start development environment | `./scripts/dev-start.sh` |
| `dev-stop.sh` | Stop development environment | `./scripts/dev-stop.sh` |
| `dev-restart.sh` | Quick restart (for manual hot-reload) | `./scripts/dev-restart.sh` |
| `dev-status.sh` | Check environment status | `./scripts/dev-status.sh` |

### Debugging Scripts

| Script | Purpose | Usage |
|--------|---------|-------|
| `dev-logs.sh` | View service logs | `./scripts/dev-logs.sh [service-name]` |
| `dev-debug.sh` | Connect to service container | `./scripts/dev-debug.sh [service] [command]` |
| `dev-test.sh` | Run development tests | `./scripts/dev-test.sh` |
| `dev-clean.sh` | Clean development environment | `./scripts/dev-clean.sh` |

### Example Usage

```bash
# Start development environment
./scripts/dev-start.sh

# Check if everything is running
./scripts/dev-status.sh

# View all service logs
./scripts/dev-logs.sh

# View specific service logs
./scripts/dev-logs.sh asr-service

# Debug a specific service
./scripts/dev-debug.sh opensips-ai-core
./scripts/dev-debug.sh llm-service python

# Run tests
./scripts/dev-test.sh

# Clean up everything
./scripts/dev-clean.sh
```

## Hot-Reload Mechanism

### How It Works

1. **File Watching**: The `file_watcher.py` utility monitors source code directories
2. **Change Detection**: Uses the `watchdog` library to detect file modifications
3. **Debouncing**: Multiple rapid changes are batched with a 2-second debounce
4. **Graceful Restart**: Services are gracefully shut down and restarted
5. **Container Restart**: Docker automatically restarts the container after exit

### Watched Directories

- `./core/` - Core application code
- `./services/*/src/` - Individual service source code
- `./services/common/` - Shared service utilities
- `./shared/proto_generated/` - Generated protocol buffer files

### Optimization for 30-Second Target

1. **Fast Docker Builds**:
   - Multi-stage builds with cached layers
   - Pip cache mounting: `--mount=type=cache,target=/root/.cache/pip`
   - Pre-built wheels for heavy dependencies

2. **Optimized Dependencies**:
   - CPU-only PyTorch for faster startup
   - Offline mode for transformers
   - Minimal runtime dependencies

3. **Quick Health Checks**:
   - Reduced health check intervals
   - Faster timeout values
   - Fewer retry attempts

## Development Logging

### Enhanced Log Format

Development mode uses a detailed log format:
```
2024-01-15 10:30:45,123 | DEBUG    | grpc_clients.asr   | connect_to_service:42   | Connecting to ASR service at localhost:50051
```

### Color-Coded Output

When `colorlog` is available:
- 🔵 **DEBUG**: Cyan
- 🟢 **INFO**: Green  
- 🟡 **WARNING**: Yellow
- 🔴 **ERROR**: Red
- 🔴 **CRITICAL**: Bold Red

### Development Logger Features

```python
from utils.logging import get_development_logger

logger = get_development_logger(__name__)

# Debug object state
logger.debug_state(my_object, "after initialization")

# Debug function calls
logger.debug_function_call("process_audio", args=[audio_data], kwargs={"sample_rate": 16000})

# Debug performance
logger.debug_performance("audio_processing", start_time, end_time)

# Debug data flow
logger.debug_data_flow("pipeline_stage", "audio_chunk", len(audio_data))
```

## Troubleshooting

### Hot-Reload Not Working

1. **Check Development Mode**:
   ```bash
   docker-compose -f docker-compose.yml -f docker-compose.dev.yml exec opensips-ai-core env | grep DEVELOPMENT_MODE
   ```

2. **Check File Watcher**:
   ```bash
   ./scripts/dev-logs.sh opensips-ai-core | grep "Hot-reload"
   ```

3. **Manual Restart**:
   ```bash
   ./scripts/dev-restart.sh
   ```

### Slow Startup

1. **Check Docker Build Cache**:
   ```bash
   docker system df
   ```

2. **Clean Build Cache**:
   ```bash
   ./scripts/dev-clean.sh
   ```

3. **Rebuild with No Cache**:
   ```bash
   docker-compose -f docker-compose.yml -f docker-compose.dev.yml build --no-cache
   ```

### Service Health Issues

1. **Check Service Status**:
   ```bash
   ./scripts/dev-status.sh
   ```

2. **View Service Logs**:
   ```bash
   ./scripts/dev-logs.sh [service-name]
   ```

3. **Debug Service Container**:
   ```bash
   ./scripts/dev-debug.sh [service-name]
   ```

## Best Practices

### Code Development

1. **Use Development Loggers**: Take advantage of enhanced debugging features
2. **Test Frequently**: Use `./scripts/dev-test.sh` to run tests
3. **Monitor Logs**: Keep `./scripts/dev-logs.sh` running in a separate terminal
4. **Clean Regularly**: Use `./scripts/dev-clean.sh` to avoid build cache issues

### Performance Tips

1. **Batch Changes**: Make multiple related changes before saving to avoid excessive restarts
2. **Use .gitignore**: Ensure temporary files don't trigger unnecessary reloads
3. **Monitor Resources**: Development mode uses more CPU/memory than production
4. **Regular Cleanup**: Run `./scripts/dev-clean.sh` periodically

### Debugging Workflow

1. **Start with Status**: Always check `./scripts/dev-status.sh` first
2. **Use Debug Containers**: Connect to containers with `./scripts/dev-debug.sh`
3. **Check Multiple Services**: Issues may span multiple services
4. **Save Logs**: Capture logs when reporting issues

## Production vs Development

| Feature | Development | Production |
|---------|-------------|------------|
| **Hot-reload** | ✅ Enabled | ❌ Disabled |
| **Log Level** | DEBUG | INFO |
| **Health Check Interval** | 15s | 30s |
| **Build Optimization** | Fast rebuilds | Size optimization |
| **Security** | Relaxed | Hardened |
| **Resource Limits** | None | Enforced |
| **File Mounting** | Source code mounted | Code copied into image |

## Switching Between Modes

### Development → Production
```bash
./scripts/dev-stop.sh
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### Production → Development
```bash
docker-compose -f docker-compose.yml -f docker-compose.prod.yml down
./scripts/dev-start.sh
```

## Environment Variables

### Core Development Variables
```bash
DEVELOPMENT_MODE=1                    # Enables development features
CORE_LOG_LEVEL=DEBUG                 # Sets log level
PYTHONUNBUFFERED=1                   # Immediate stdout/stderr
PYTHONDONTWRITEBYTECODE=1            # Skip .pyc files
CORE_HOT_RELOAD=1                    # Enable hot-reload for core
ASR_HOT_RELOAD=1                     # Enable hot-reload for ASR
LLM_HOT_RELOAD=1                     # Enable hot-reload for LLM
TTS_HOT_RELOAD=1                     # Enable hot-reload for TTS
```

### Service-Specific Variables
```bash
# ASR Service
ASR_ENABLE_DEBUG=1
VOSK_SHOW_WORDS=true

# LLM Service  
LLM_ENABLE_DEBUG=1
TORCH_FORCE_CPU=1
TRANSFORMERS_OFFLINE=1
HF_HUB_OFFLINE=1

# TTS Service
TTS_ENABLE_DEBUG=1
```

This development mode is designed to provide a fast, productive development experience with automatic hot-reload capabilities targeting a 30-second restart time.