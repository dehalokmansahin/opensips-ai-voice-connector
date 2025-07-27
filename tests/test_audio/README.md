# Test Audio Files for OpenSIPS AI Voice Connector

## Banking Test Scenarios

### 1. card_delivery_query.wav
- **Purpose**: Test card delivery status inquiry (MVP scenario)
- **Simulates**: "Kart teslimat durumu nedir?"
- **Duration**: ~3 seconds
- **Expected Response**: Card delivery status information

### 2. general_greeting.wav  
- **Purpose**: Test general banking conversation initiation
- **Simulates**: "Merhaba, yardıma ihtiyacım var"
- **Duration**: ~2.5 seconds
- **Expected Response**: Greeting and assistance offer

### 3. turn1.wav & turn2.wav
- **Purpose**: Test multi-turn conversation with context memory
- **Turn 1 Simulates**: "Hesap bakiyemi öğrenebilir miyim?"
- **Turn 2 Simulates**: "Geçen ay kaç işlem yapmışım?"
- **Expected**: Context maintained between turns

### 4. silence.wav
- **Purpose**: Test VAD and silence handling
- **Duration**: 1 second of silence
- **Expected**: No ASR activation

### 5. short_utterance.wav & long_utterance.wav
- **Purpose**: Test different utterance lengths
- **Short**: 1.5 seconds (quick command)
- **Long**: 5 seconds (detailed inquiry)

## Audio Specifications
- **Sample Rate**: 8000 Hz (OpenSIPS standard)
- **Channels**: Mono (1)
- **Bit Depth**: 16-bit
- **Format**: WAV (PCM)

## Usage with RTP Simulator
```python
from tests.rtp_simulator import RTPSimulator, AudioFile

simulator = RTPSimulator(target_port=10000)
audio = AudioFile("tests/test_audio/card_delivery_query.wav", "Card delivery test")
await simulator.send_audio_file(audio)
```

## Note
These are synthetic audio files for testing purposes. In production testing, 
use real recordings of Turkish banking conversations for more accurate results.
