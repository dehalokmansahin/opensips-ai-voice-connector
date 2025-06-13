# Testing Guide

This guide provides comprehensive instructions for testing the OpenSIPS AI Voice Connector system.

## Quick Start Testing

### Prerequisites

```bash
# Install test dependencies
pip install pytest pytest-asyncio pytest-timeout
pip install sipp  # For SIP testing
pip install docker-compose

# Verify system is running
docker-compose ps
```

### 5-Minute Smoke Test

```bash
# Run basic functionality test
cd tests
python -m pytest test_e2e_smoke.py::TestE2ESmokeFlow::test_complete_call_flow -v

# Expected output:
# ✓ INVITE processing
# ✓ Media exchange
# ✓ BYE handling
# ✓ Cleanup verification
```

## Test Categories

### 1. Unit Tests

Test individual components in isolation:

```bash
# VAD component tests
python -m pytest tests/unit/test_vad.py -v

# TTS processor tests  
python -m pytest tests/unit/test_tts_processor.py -v

# SIP handling tests
python -m pytest tests/unit/test_sip_handling.py -v
```

### 2. Integration Tests

Test component interactions:

```bash
# OpenSIPS ↔ OAVC integration
python -m pytest tests/integration/test_opensips_integration.py -v

# AI engine integration
python -m pytest tests/integration/test_ai_integration.py -v

# RTP media flow
python -m pytest tests/integration/test_rtp_flow.py -v
```

### 3. End-to-End Tests

Test complete call flows:

```bash
# Full call flow (INVITE → media → BYE)
python -m pytest tests/e2e/test_call_flow.py -v

# Barge-in functionality
python -m pytest tests/e2e/test_barge_in.py -v

# Error scenarios
python -m pytest tests/e2e/test_error_scenarios.py -v
```

### 4. Performance Tests

Benchmark system performance:

```bash
# Load testing
python -m pytest tests/performance/test_load.py -v

# Latency benchmarks
python -m pytest tests/performance/test_latency.py -v

# Memory usage
python -m pytest tests/performance/test_memory.py -v
```

## Manual Testing Scenarios

### Basic Call Flow Test

1. **Setup Test Environment**:
   ```bash
   # Start services
   docker-compose up -d
   
   # Verify services are healthy
   docker-compose ps
   curl -f http://localhost:8080/health
   ```

2. **Make Test Call**:
   ```bash
   # Using SIPp for call simulation
   sipp -sf scenarios/basic_call.xml opensips-server:5060
   ```

3. **Verify Call Flow**:
   ```bash
   # Check logs for expected events
   docker-compose logs opensips | grep "INVITE\|BYE"
   docker-compose logs oavc | grep "call.*created\|call.*closed"
   ```

### Audio Quality Test

1. **Record Test Audio**:
   ```bash
   # Generate test audio file
   python scripts/generate_test_audio.py --duration 10 --format wav
   ```

2. **Send Audio Through System**:
   ```bash
   # Use audio injection tool
   python scripts/inject_audio.py --file test_audio.wav --target oavc:35000
   ```

3. **Analyze Output**:
   ```bash
   # Check audio quality metrics
   python scripts/analyze_audio.py --input received_audio.wav
   ```

### Barge-in Test

1. **Start Long TTS**:
   ```bash
   # Trigger long AI response
   echo "Tell me a long story" | python scripts/send_sip_message.py
   ```

2. **Interrupt During Speech**:
   ```bash
   # Send interruption after 2 seconds
   sleep 2 && echo "Stop" | python scripts/send_sip_message.py
   ```

3. **Verify Interruption**:
   ```bash
   # Check TTS was stopped quickly
   grep "TTS.*interrupt" /var/log/oavc.log
   ```

## Automated Test Scenarios

### SIPp Test Scenarios

#### Basic INVITE/BYE Test

```xml
<!-- scenarios/basic_call.xml -->
<?xml version="1.0" encoding="ISO-8859-1" ?>
<scenario name="Basic Call">
  <send retrans="500">
    <![CDATA[
      INVITE sip:test@[remote_ip]:[remote_port] SIP/2.0
      Via: SIP/2.0/UDP [local_ip]:[local_port];branch=[branch]
      From: sipp <sip:sipp@[local_ip]:[local_port]>;tag=[pid]SIPpTag00[call_number]
      To: test <sip:test@[remote_ip]:[remote_port]>
      Call-ID: [call_id]
      CSeq: 1 INVITE
      Contact: sip:sipp@[local_ip]:[local_port]
      Content-Type: application/sdp
      Content-Length: [len]

      v=0
      o=user1 53655765 2353687637 IN IP4 [local_ip]
      s=-
      c=IN IP4 [local_ip]
      t=0 0
      m=audio 6000 RTP/AVP 0
      a=rtpmap:0 PCMU/8000
    ]]>
  </send>

  <recv response="100" optional="true">
  </recv>

  <recv response="200" rtd="true">
  </recv>

  <send>
    <![CDATA[
      ACK sip:test@[remote_ip]:[remote_port] SIP/2.0
      Via: SIP/2.0/UDP [local_ip]:[local_port];branch=[branch]
      From: sipp <sip:sipp@[local_ip]:[local_port]>;tag=[pid]SIPpTag00[call_number]
      To: test <sip:test@[remote_ip]:[remote_port]>[peer_tag_param]
      Call-ID: [call_id]
      CSeq: 1 ACK
      Contact: sip:sipp@[local_ip]:[local_port]
      Content-Length: 0
    ]]>
  </send>

  <pause milliseconds="5000"/>

  <send retrans="500">
    <![CDATA[
      BYE sip:test@[remote_ip]:[remote_port] SIP/2.0
      Via: SIP/2.0/UDP [local_ip]:[local_port];branch=[branch]
      From: sipp <sip:sipp@[local_ip]:[local_port]>;tag=[pid]SIPpTag00[call_number]
      To: test <sip:test@[remote_ip]:[remote_port]>[peer_tag_param]
      Call-ID: [call_id]
      CSeq: 2 BYE
      Contact: sip:sipp@[local_ip]:[local_port]
      Content-Length: 0
    ]]>
  </send>

  <recv response="200" crlf="true">
  </recv>
</scenario>
```

#### Load Test Scenario

```bash
# Run 10 concurrent calls
sipp -sf scenarios/basic_call.xml -l 10 -r 1 -rp 1000 opensips-server:5060

# Run for 60 seconds with 50 calls/second
sipp -sf scenarios/basic_call.xml -r 50 -d 60000 opensips-server:5060
```

### Python Test Scripts

#### Audio Injection Test

```python
#!/usr/bin/env python3
"""
Audio injection test script
"""
import asyncio
import socket
import wave
import time

async def inject_audio_file(filename: str, target_host: str, target_port: int):
    """Inject audio file as RTP packets"""
    
    # Open audio file
    with wave.open(filename, 'rb') as wav_file:
        frames = wav_file.readframes(wav_file.getnframes())
        sample_rate = wav_file.getframerate()
        
    # Create UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    # Send audio in 20ms chunks (160 bytes for PCMU)
    chunk_size = 160
    chunk_duration = 0.02  # 20ms
    
    for i in range(0, len(frames), chunk_size):
        chunk = frames[i:i+chunk_size]
        if len(chunk) < chunk_size:
            chunk += b'\x00' * (chunk_size - len(chunk))  # Pad with silence
            
        # Send RTP packet
        sock.sendto(chunk, (target_host, target_port))
        
        # Wait for next chunk
        await asyncio.sleep(chunk_duration)
        
    sock.close()
    print(f"Injected {len(frames)} bytes of audio")

if __name__ == "__main__":
    asyncio.run(inject_audio_file("test_audio.wav", "localhost", 35000))
```

#### Latency Measurement Test

```python
#!/usr/bin/env python3
"""
Measure end-to-end latency
"""
import asyncio
import time
import websockets
import json

async def measure_latency():
    """Measure time from audio input to AI response"""
    
    uri = "ws://localhost:2700/ws"
    
    async with websockets.connect(uri) as websocket:
        # Send test message
        test_message = {
            "type": "audio",
            "data": "SGVsbG8gd29ybGQ=",  # Base64 encoded "Hello world"
            "timestamp": time.time()
        }
        
        start_time = time.time()
        await websocket.send(json.dumps(test_message))
        
        # Wait for response
        response = await websocket.recv()
        end_time = time.time()
        
        latency = (end_time - start_time) * 1000  # Convert to ms
        print(f"End-to-end latency: {latency:.2f}ms")
        
        return latency

if __name__ == "__main__":
    latency = asyncio.run(measure_latency())
    assert latency < 500, f"Latency too high: {latency}ms"
```

## Test Data and Fixtures

### Audio Test Files

```bash
# Generate test audio files
mkdir -p tests/fixtures/audio

# Short beep (for VAD testing)
python -c "
import numpy as np
import wave
import struct

# Generate 1 second 440Hz tone
sample_rate = 8000
duration = 1.0
frequency = 440

t = np.linspace(0, duration, int(sample_rate * duration))
audio = np.sin(2 * np.pi * frequency * t) * 0.5

# Convert to 16-bit PCM
audio_int = (audio * 32767).astype(np.int16)

# Save as WAV
with wave.open('tests/fixtures/audio/test_beep.wav', 'wb') as wav_file:
    wav_file.setnchannels(1)
    wav_file.setsampwidth(2)
    wav_file.setframerate(sample_rate)
    wav_file.writeframes(audio_int.tobytes())
"

# Silence (for timeout testing)
python -c "
import wave
import struct

# Generate 5 seconds of silence
sample_rate = 8000
duration = 5.0
samples = int(sample_rate * duration)

with wave.open('tests/fixtures/audio/silence.wav', 'wb') as wav_file:
    wav_file.setnchannels(1)
    wav_file.setsampwidth(2)
    wav_file.setframerate(sample_rate)
    wav_file.writeframes(b'\x00\x00' * samples)
"
```

### SIP Message Templates

```python
# tests/fixtures/sip_messages.py

INVITE_TEMPLATE = """INVITE sip:{user}@{host}:{port} SIP/2.0
Via: SIP/2.0/UDP {local_ip}:{local_port};branch={branch}
From: <sip:test@{local_ip}:{local_port}>;tag={from_tag}
To: <sip:{user}@{host}:{port}>
Call-ID: {call_id}
CSeq: 1 INVITE
Contact: <sip:test@{local_ip}:{local_port}>
Content-Type: application/sdp
Content-Length: {content_length}

{sdp_body}"""

SDP_TEMPLATE = """v=0
o=- {session_id} {session_version} IN IP4 {local_ip}
s=-
c=IN IP4 {local_ip}
t=0 0
m=audio {rtp_port} RTP/AVP 0
a=rtpmap:0 PCMU/8000
a=sendrecv"""

BYE_TEMPLATE = """BYE sip:{user}@{host}:{port} SIP/2.0
Via: SIP/2.0/UDP {local_ip}:{local_port};branch={branch}
From: <sip:test@{local_ip}:{local_port}>;tag={from_tag}
To: <sip:{user}@{host}:{port}>;tag={to_tag}
Call-ID: {call_id}
CSeq: 2 BYE
Content-Length: 0"""
```

## Continuous Integration Testing

### GitHub Actions Workflow

The CI pipeline runs automatically on every commit:

```yaml
# .github/workflows/ci.yml (already created)
# - Smoke tests (< 2 minutes)
# - Code quality checks
# - Docker build verification
# - Performance benchmarks (main branch only)
```

### Local CI Simulation

```bash
# Run the same tests as CI locally
./scripts/run_ci_tests.sh

# Or run individual test suites
pytest tests/test_e2e_smoke.py -v --timeout=15
flake8 src/ --count --statistics
black --check src/
docker build -t oavc:test .
```

## Performance Testing

### Load Testing with SIPp

```bash
# Test with increasing load
for rate in 1 5 10 20 50; do
    echo "Testing with $rate calls/second"
    sipp -sf scenarios/basic_call.xml -r $rate -l 100 -d 30000 opensips-server:5060
    sleep 10  # Cool down between tests
done
```

### Memory and CPU Monitoring

```bash
# Monitor during load test
./scripts/monitor_performance.sh &
MONITOR_PID=$!

# Run load test
sipp -sf scenarios/load_test.xml -r 50 -d 60000 opensips-server:5060

# Stop monitoring
kill $MONITOR_PID
```

### Latency Testing

```python
# tests/performance/test_latency.py
import pytest
import asyncio
import time

@pytest.mark.asyncio
async def test_call_setup_latency():
    """Test call setup latency is under 100ms"""
    start_time = time.time()
    
    # Simulate INVITE processing
    result = await process_invite(test_invite_message)
    
    latency = (time.time() - start_time) * 1000
    assert latency < 100, f"Call setup too slow: {latency:.2f}ms"

@pytest.mark.asyncio 
async def test_audio_processing_latency():
    """Test audio processing latency is under 50ms"""
    audio_chunk = generate_test_audio_chunk()
    
    start_time = time.time()
    result = await process_audio_chunk(audio_chunk)
    latency = (time.time() - start_time) * 1000
    
    assert latency < 50, f"Audio processing too slow: {latency:.2f}ms"
```

## Troubleshooting Test Failures

### Common Test Issues

1. **Port Conflicts**:
   ```bash
   # Check for port conflicts
   netstat -tulpn | grep -E "(5060|8088|8089|35000)"
   
   # Kill conflicting processes
   sudo fuser -k 5060/udp
   ```

2. **Docker Issues**:
   ```bash
   # Clean up Docker state
   docker-compose down -v
   docker system prune -f
   docker-compose up -d
   ```

3. **Timing Issues**:
   ```bash
   # Increase test timeouts for slow systems
   pytest tests/ --timeout=30 -v
   ```

### Debug Mode Testing

```bash
# Run tests with debug logging
export LOG_LEVEL=DEBUG
export DEBUG_MODE=true
pytest tests/ -v -s --log-cli-level=DEBUG
```

### Test Result Analysis

```bash
# Generate test report
pytest tests/ --html=test_report.html --self-contained-html

# Coverage report
pytest tests/ --cov=src --cov-report=html

# Performance profiling
pytest tests/performance/ --profile --profile-svg
```

## Best Practices

### Writing Tests

1. **Use descriptive test names**:
   ```python
   def test_invite_with_invalid_sdp_returns_400_error():
       """Test that INVITE with malformed SDP returns 400 Bad Request"""
   ```

2. **Test one thing at a time**:
   ```python
   # Good: Tests specific functionality
   def test_vad_detects_speech_in_noisy_environment():
       pass
   
   # Bad: Tests multiple things
   def test_complete_system_functionality():
       pass
   ```

3. **Use fixtures for common setup**:
   ```python
   @pytest.fixture
   def mock_ai_engine():
       engine = MockAIEngine()
       yield engine
       engine.cleanup()
   ```

4. **Clean up after tests**:
   ```python
   def test_call_creation():
       call = create_test_call()
       try:
           # Test logic here
           pass
       finally:
           call.cleanup()
   ```

### Test Environment

1. **Use isolated test environment**
2. **Mock external dependencies**
3. **Use deterministic test data**
4. **Clean state between tests**

### Performance Testing

1. **Establish baselines**
2. **Test under realistic load**
3. **Monitor resource usage**
4. **Test degradation gracefully** 