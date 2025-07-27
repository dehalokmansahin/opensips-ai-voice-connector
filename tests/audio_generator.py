#!/usr/bin/env python3
"""
Test Audio Generator for OpenSIPS AI Voice Connector
Creates synthetic audio files for testing when real recordings are not available
"""

import wave
import numpy as np
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class TestAudioGenerator:
    """Generate test audio files for banking scenarios"""
    
    def __init__(self, output_dir: str = "tests/test_audio"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.sample_rate = 8000  # OpenSIPS standard
        self.channels = 1
        self.sample_width = 2  # 16-bit
    
    def generate_tone(self, frequency: float, duration_seconds: float) -> np.ndarray:
        """Generate sine wave tone"""
        samples = int(self.sample_rate * duration_seconds)
        t = np.linspace(0, duration_seconds, samples, False)
        tone = np.sin(2 * np.pi * frequency * t)
        # Convert to 16-bit range
        return (tone * 32767).astype(np.int16)
    
    def generate_speech_like_audio(self, duration_seconds: float) -> np.ndarray:
        """Generate speech-like audio with varying tones"""
        samples = int(self.sample_rate * duration_seconds)
        audio = np.zeros(samples, dtype=np.int16)
        
        # Create speech-like patterns with multiple frequencies
        segment_length = samples // 10
        frequencies = [300, 400, 350, 500, 450, 380, 420, 360, 480, 400]
        
        for i, freq in enumerate(frequencies):
            start = i * segment_length
            end = min(start + segment_length, samples)
            if start < samples:
                segment_duration = (end - start) / self.sample_rate
                segment = self.generate_tone(freq, segment_duration)
                audio[start:end] = segment[:end-start]
        
        # Add some amplitude variation to make it more speech-like
        envelope = np.random.uniform(0.3, 1.0, samples)
        audio = (audio * envelope).astype(np.int16)
        
        return audio
    
    def save_wav_file(self, audio_data: np.ndarray, filename: str):
        """Save audio data as WAV file"""
        filepath = self.output_dir / filename
        
        with wave.open(str(filepath), 'wb') as wav_file:
            wav_file.setnchannels(self.channels)
            wav_file.setsampwidth(self.sample_width)
            wav_file.setframerate(self.sample_rate)
            wav_file.writeframes(audio_data.tobytes())
        
        logger.info(f"Generated test audio: {filepath}")
        return filepath
    
    def generate_banking_test_files(self):
        """Generate all banking test audio files"""
        
        # 1. Card delivery status inquiry
        card_audio = self.generate_speech_like_audio(3.0)  # 3 seconds
        self.save_wav_file(card_audio, "card_delivery_query.wav")
        
        # 2. General greeting
        greeting_audio = self.generate_speech_like_audio(2.5)  # 2.5 seconds
        self.save_wav_file(greeting_audio, "general_greeting.wav")
        
        # 3. Multi-turn conversation - Turn 1
        turn1_audio = self.generate_speech_like_audio(2.8)  # 2.8 seconds
        self.save_wav_file(turn1_audio, "turn1.wav")
        
        # 4. Multi-turn conversation - Turn 2
        turn2_audio = self.generate_speech_like_audio(3.2)  # 3.2 seconds
        self.save_wav_file(turn2_audio, "turn2.wav")
        
        # 5. Background noise / silence test
        silence = np.zeros(int(self.sample_rate * 1.0), dtype=np.int16)
        self.save_wav_file(silence, "silence.wav")
        
        # 6. Short utterance
        short_audio = self.generate_speech_like_audio(1.5)  # 1.5 seconds
        self.save_wav_file(short_audio, "short_utterance.wav")
        
        # 7. Long utterance
        long_audio = self.generate_speech_like_audio(5.0)  # 5 seconds
        self.save_wav_file(long_audio, "long_utterance.wav")
        
        logger.info("All banking test audio files generated successfully!")
    
    def generate_test_audio_info(self) -> str:
        """Generate README for test audio files"""
        info = """# Test Audio Files for OpenSIPS AI Voice Connector

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
"""
        
        readme_path = self.output_dir / "README.md"
        with open(readme_path, 'w', encoding='utf-8') as f:
            f.write(info)
        
        return str(readme_path)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    generator = TestAudioGenerator()
    generator.generate_banking_test_files()
    readme_path = generator.generate_test_audio_info()
    
    print(f"✅ Test audio files generated in: {generator.output_dir}")
    print(f"📖 Documentation created: {readme_path}")