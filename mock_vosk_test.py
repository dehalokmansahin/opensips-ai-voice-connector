#!/usr/bin/env python
"""
Simple mock test for WebRTC VAD functionality
"""

import os
import time
import asyncio
import logging
from enum import Enum

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# We'll create a standalone implementation to test the WebRTC VAD functionality
try:
    import webrtcvad
    WEBRTC_AVAILABLE = True
except ImportError:
    WEBRTC_AVAILABLE = False
    logging.warning("webrtcvad package not installed. Run: pip install webrtcvad")

class SpeechState(Enum):
    """State of speech detection"""
    SILENCE = 0
    SPEAKING = 1
    POSSIBLE_END = 2
    BARGE_IN = 3


class SimpleVAD:
    """
    Simple WebRTC VAD implementation for testing
    """
    def __init__(self, 
                 aggressiveness=2, 
                 silence_frames_threshold=10,
                 speech_frames_threshold=3,
                 enable_barge_in=True,
                 barge_in_threshold=5):
        """Initialize the VAD"""
        self.vad = None
        if WEBRTC_AVAILABLE:
            try:
                self.vad = webrtcvad.Vad(aggressiveness)
                logging.info(f"WebRTC VAD initialized with aggressiveness level {aggressiveness}")
            except Exception as e:
                logging.error(f"Failed to initialize WebRTC VAD: {str(e)}")
                
        # Settings
        self.aggressiveness = aggressiveness
        self.silence_frames_threshold = silence_frames_threshold
        self.speech_frames_threshold = speech_frames_threshold
        self.enable_barge_in = enable_barge_in
        self.barge_in_threshold = barge_in_threshold
        
        # State variables
        self.speech_state = SpeechState.SILENCE
        self.silence_frames = 0
        self.speech_frames = 0
        self.is_tts_playing = False
        self.barge_in_callback = None
        self.sample_rate = 8000
        
        # For emulation without WebRTC
        self._emulate_mode = not WEBRTC_AVAILABLE
        
    def _detect_speech(self, audio):
        """Detect speech in audio frame"""
        if not self.vad or len(audio) < 160:
            return False
            
        # WebRTC VAD requires specific frame sizes
        # For 8kHz: frames should be 10, 20, or 30ms (80, 160, or 240 bytes for 16-bit PCM)
        # We'll use just a 20ms frame
        frame = audio[:160]
        
        try:
            return self.vad.is_speech(frame, self.sample_rate)
        except Exception as e:
            logging.warning(f"VAD error: {str(e)}")
            return False
            
    def _emulate_speech_detection(self, audio):
        """
        Emulate speech detection when WebRTC is not available
        Treats non-zero audio as speech
        """
        # Simple energy detection - if there's significant non-zero content, call it speech
        if len(audio) < 20:
            return False
            
        # Count non-zero bytes to determine if this is silence
        non_zero = sum(1 for b in audio[:40] if b != 0)
        return non_zero > 10  # If more than 10 non-zero bytes, consider it speech
    
    def update_state(self, audio):
        """Update state based on audio frame"""
        if self._emulate_mode:
            is_speech = self._emulate_speech_detection(audio)
        else:
            is_speech = self._detect_speech(audio)
            
        self._update_speech_state(is_speech)
        
        # Check for barge-in
        if self.enable_barge_in and self.is_tts_playing:
            if (self.speech_state == SpeechState.BARGE_IN and 
                self.speech_frames >= self.barge_in_threshold):
                # Try to handle barge-in
                return self._handle_barge_in()
        
        return False
        
    def _update_speech_state(self, is_speech):
        """Update speech state based on VAD result"""
        if is_speech:
            # Reset silence counter and increment speech counter
            self.silence_frames = 0
            self.speech_frames += 1
            
            # Transition to SPEAKING or BARGE_IN state after enough speech frames
            if self.speech_frames >= self.speech_frames_threshold:
                if self.speech_state != SpeechState.SPEAKING and self.speech_state != SpeechState.BARGE_IN:
                    logging.info("Speech detected")
                    
                    if self.is_tts_playing and self.enable_barge_in:
                        self.speech_state = SpeechState.BARGE_IN
                        logging.info("Potential barge-in detected")
                    else:
                        self.speech_state = SpeechState.SPEAKING
        else:
            # In silence, increment silence counter and reset speech counter
            self.silence_frames += 1
            self.speech_frames = 0
            
            # Handle state transitions based on silence duration
            if self.speech_state in (SpeechState.SPEAKING, SpeechState.BARGE_IN):
                if self.silence_frames >= 2:
                    self.speech_state = SpeechState.POSSIBLE_END
                    logging.info("Possible end of speech detected")
            elif self.speech_state == SpeechState.POSSIBLE_END:
                if self.silence_frames >= self.silence_frames_threshold:
                    self.speech_state = SpeechState.SILENCE
                    logging.info("End of speech confirmed")
    
    def _handle_barge_in(self):
        """Handle barge-in detection"""
        logging.info(f"🎯 BARGE-IN DETECTED! TTS would be stopped here. Speech frames: {self.speech_frames}")
        self.speech_state = SpeechState.SPEAKING
        
        # Reset TTS playing flag
        was_playing = self.is_tts_playing
        self.is_tts_playing = False
        
        # Call the callback asynchronously if registered
        if self.barge_in_callback and was_playing:
            asyncio.create_task(self.barge_in_callback())
            return True
        
        return False
        
    def register_barge_in_callback(self, callback):
        """Register barge-in callback"""
        self.barge_in_callback = callback
        
    def set_tts_playing(self, is_playing):
        """Set TTS playing state"""
        self.is_tts_playing = is_playing
        if is_playing:
            logging.info("TTS playback started, barge-in detection enabled")
        else:
            logging.info("TTS playback ended, barge-in detection disabled")


async def test_vad_with_file(audio_file, is_tts_playing=False, duration=5):
    """Test VAD with an audio file"""
    if not os.path.exists(audio_file):
        logging.error(f"Audio file not found: {audio_file}")
        return
        
    # Create VAD with lower barge-in threshold for testing
    vad = SimpleVAD(barge_in_threshold=5 if not is_tts_playing else 3)
    
    # Set up callback
    barge_in_detected = asyncio.Event()
    async def on_barge_in():
        logging.info("Barge-in callback triggered")
        barge_in_detected.set()
        
    vad.register_barge_in_callback(on_barge_in)
    
    # Set TTS state if needed
    if is_tts_playing:
        vad.set_tts_playing(True)
    
    # Read and process audio
    with open(audio_file, "rb") as f:
        audio_data = f.read()
        
    # Split into 20ms chunks
    chunk_size = 320  # 20ms at 8kHz, 16-bit
    chunks = [audio_data[i:i+chunk_size] for i in range(0, len(audio_data), chunk_size)]
    
    start_time = time.time()
    for i, chunk in enumerate(chunks):
        # Update VAD state
        vad.update_state(chunk)
        
        # Log current state occasionally
        if i % 10 == 0:
            logging.info(f"Frame {i}, State: {vad.speech_state.name}, " +
                         f"Speech frames: {vad.speech_frames}, " +
                         f"Silence frames: {vad.silence_frames}")
        
        # Simulate real-time processing
        await asyncio.sleep(0.02)
        
        # Check if we've exceeded the test duration
        if time.time() - start_time > duration:
            break
    
    # Check for barge-in
    if is_tts_playing:
        if barge_in_detected.is_set():
            logging.info("✅ Barge-in was successfully detected")
        else:
            logging.warning("❌ Barge-in was not detected")


async def test_with_synthetic_audio(duration=5, is_tts_playing=False, delay_barge_in=2):
    """Test with synthetic audio"""
    # Create VAD with lower barge-in threshold for testing
    vad = SimpleVAD(barge_in_threshold=3)
    
    # Set up callback
    barge_in_detected = asyncio.Event()
    async def on_barge_in():
        logging.info("Barge-in callback triggered")
        barge_in_detected.set()
        
    vad.register_barge_in_callback(on_barge_in)
    
    # Set TTS state if needed
    if is_tts_playing:
        vad.set_tts_playing(True)
    
    # Generate silence and noise patterns
    silence = bytes([0] * 320)
    noise = bytes([i % 256 for i in range(320)])
    
    # Start time tracking
    start_time = time.time()
    barge_in_time = start_time + delay_barge_in
    
    # Simulate audio for the duration
    while time.time() - start_time < duration:
        # If TTS is playing and it's time to trigger barge-in
        if is_tts_playing:
            if time.time() < barge_in_time:
                vad.update_state(silence)
            else:
                if not barge_in_detected.is_set():
                    logging.info("Sending noise to trigger barge-in")
                vad.update_state(noise)
        else:
            # Alternate between silence and noise every 0.5 seconds
            cycle = int((time.time() - start_time) / 0.5) % 2
            if cycle == 0:
                vad.update_state(silence)
            else:
                vad.update_state(noise)
        
        # Log current state occasionally
        if int((time.time() - start_time) * 50) % 50 == 0:
            logging.info(f"State: {vad.speech_state.name}, " +
                        f"Speech frames: {vad.speech_frames}, " +
                        f"Silence frames: {vad.silence_frames}")
        
        # Simulate real-time processing
        await asyncio.sleep(0.02)
    
    # Check for barge-in
    if is_tts_playing:
        if barge_in_detected.is_set():
            logging.info("✅ Barge-in was successfully detected")
        else:
            logging.warning("❌ Barge-in was not detected")


async def main():
    """Run the tests"""
    
    # Check if audio file exists
    audio_file = "test_audio/barge_in_test.raw"
    if os.path.exists(audio_file):
        logging.info(f"Testing with audio file: {audio_file}")
        logging.info("=== NORMAL MODE ===")
        await test_vad_with_file(audio_file, is_tts_playing=False, duration=5)
        
        logging.info("\n=== BARGE-IN MODE ===")
        await test_vad_with_file(audio_file, is_tts_playing=True, duration=5)
    else:
        logging.info("Audio file not found, using synthetic audio")
        
        logging.info("=== NORMAL MODE WITH SYNTHETIC AUDIO ===")
        await test_with_synthetic_audio(duration=5, is_tts_playing=False)
        
        logging.info("\n=== BARGE-IN MODE WITH SYNTHETIC AUDIO ===")
        await test_with_synthetic_audio(duration=5, is_tts_playing=True, delay_barge_in=2)

if __name__ == "__main__":
    asyncio.run(main()) 