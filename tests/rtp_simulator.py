#!/usr/bin/env python3
"""
RTP Simulator for OpenSIPS AI Voice Connector Testing
Simulates OpenSIPS by sending RTP packets from audio files
"""

import asyncio
import logging
import socket
import struct
import time
import wave
import numpy as np
from pathlib import Path
from typing import Optional, List, Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class RTPPacket:
    """RTP packet structure for simulation"""
    version: int = 2
    padding: bool = False
    extension: bool = False
    cc: int = 0
    marker: bool = False
    payload_type: int = 0  # 0 = PCMU
    sequence_number: int = 0
    timestamp: int = 0
    ssrc: int = 0
    payload: bytes = b''

class AudioFile:
    """Audio file handler for test scenarios"""
    
    def __init__(self, file_path: str, description: str = ""):
        self.file_path = Path(file_path)
        self.description = description
        self.sample_rate = 8000  # OpenSIPS standard
        self.channels = 1
        self.sample_width = 2  # 16-bit
        
    def load_audio_data(self) -> bytes:
        """Load and convert audio file to PCMU format"""
        try:
            with wave.open(str(self.file_path), 'rb') as wav_file:
                frames = wav_file.readframes(wav_file.getnframes())
                # Convert to numpy array for processing
                audio_data = np.frombuffer(frames, dtype=np.int16)
                
                # Resample to 8000 Hz if needed
                if wav_file.getframerate() != 8000:
                    # Simple resampling (for testing - use proper resampling in production)
                    ratio = wav_file.getframerate() / 8000
                    new_length = int(len(audio_data) / ratio)
                    audio_data = np.interp(
                        np.linspace(0, len(audio_data), new_length),
                        np.arange(len(audio_data)),
                        audio_data
                    ).astype(np.int16)
                
                return audio_data.tobytes()
        except Exception as e:
            logger.error(f"Failed to load audio file {self.file_path}: {e}")
            return b''

class RTPSimulator:
    """RTP packet simulator for testing OpenSIPS integration"""
    
    def __init__(
        self,
        target_ip: str = "127.0.0.1",
        target_port: int = 10000,
        source_port: int = 5060,
        ssrc: int = 0x12345678
    ):
        self.target_ip = target_ip
        self.target_port = target_port
        self.source_port = source_port
        self.ssrc = ssrc
        self.sequence_number = 0
        self.timestamp = 0
        self.socket = None
        
    def create_rtp_packet(self, payload: bytes, marker: bool = False) -> bytes:
        """Create RTP packet from audio payload"""
        packet = RTPPacket(
            version=2,
            padding=False,
            extension=False,
            cc=0,
            marker=marker,
            payload_type=0,  # PCMU
            sequence_number=self.sequence_number,
            timestamp=self.timestamp,
            ssrc=self.ssrc,
            payload=payload
        )
        
        # Pack RTP header (12 bytes)
        header = struct.pack(
            '!BBHII',
            (packet.version << 6) | (int(packet.padding) << 5) | (int(packet.extension) << 4) | packet.cc,
            (int(packet.marker) << 7) | packet.payload_type,
            packet.sequence_number,
            packet.timestamp,
            packet.ssrc
        )
        
        self.sequence_number = (self.sequence_number + 1) % 65536
        return header + packet.payload
    
    async def setup_socket(self):
        """Setup UDP socket for RTP transmission"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.bind(("0.0.0.0", self.source_port))
            logger.info(f"RTP Simulator bound to port {self.source_port}")
            logger.info(f"Target: {self.target_ip}:{self.target_port}")
        except Exception as e:
            logger.error(f"Failed to setup socket: {e}")
            raise
    
    async def send_audio_file(
        self, 
        audio_file: AudioFile, 
        frame_size_ms: int = 20,
        progress_callback: Optional[Callable] = None
    ) -> bool:
        """Send audio file as RTP packets"""
        try:
            logger.info(f"📁 Loading audio file: {audio_file.file_path}")
            audio_data = audio_file.load_audio_data()
            
            if not audio_data:
                logger.error("No audio data loaded")
                return False
            
            # Calculate frame parameters
            samples_per_frame = (audio_file.sample_rate * frame_size_ms) // 1000
            bytes_per_frame = samples_per_frame * audio_file.sample_width
            timestamp_increment = samples_per_frame
            
            frames = []
            for i in range(0, len(audio_data), bytes_per_frame):
                frame = audio_data[i:i + bytes_per_frame]
                if len(frame) < bytes_per_frame:
                    # Pad last frame with silence
                    frame += b'\x00' * (bytes_per_frame - len(frame))
                frames.append(frame)
            
            logger.info(f"🎵 Sending {len(frames)} audio frames ({len(audio_data)} bytes)")
            logger.info(f"📊 Audio: {audio_file.sample_rate}Hz, {frame_size_ms}ms frames")
            
            # Send frames with real-time timing
            for i, frame in enumerate(frames):
                # Mark first and last packets
                marker = (i == 0 or i == len(frames) - 1)
                
                rtp_packet = self.create_rtp_packet(frame, marker)
                
                self.socket.sendto(rtp_packet, (self.target_ip, self.target_port))
                
                # Update timestamp for next packet
                self.timestamp += timestamp_increment
                
                # Progress callback
                if progress_callback:
                    progress_callback(i + 1, len(frames), audio_file.description)
                
                # Real-time delay
                await asyncio.sleep(frame_size_ms / 1000.0)
            
            logger.info(f"✅ Audio transmission completed: {audio_file.description}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to send audio file: {e}")
            return False
    
    async def send_silence(self, duration_ms: int = 1000):
        """Send silence frames"""
        logger.info(f"🔇 Sending {duration_ms}ms silence")
        
        frame_size_ms = 20
        samples_per_frame = 8000 * frame_size_ms // 1000
        silence_frame = b'\x00' * (samples_per_frame * 2)  # 16-bit silence
        
        frames_count = duration_ms // frame_size_ms
        
        for i in range(frames_count):
            rtp_packet = self.create_rtp_packet(silence_frame)
            self.socket.sendto(rtp_packet, (self.target_ip, self.target_port))
            self.timestamp += samples_per_frame
            await asyncio.sleep(frame_size_ms / 1000.0)
    
    def close(self):
        """Close socket connection"""
        if self.socket:
            self.socket.close()
            logger.info("RTP Simulator socket closed")

# Test scenario definitions
class TestScenario:
    """Test scenario with audio files and expected behavior"""
    
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.audio_files: List[AudioFile] = []
        self.expected_responses: List[str] = []
        self.timeout_seconds: int = 30
    
    def add_audio_file(self, file_path: str, description: str = ""):
        """Add audio file to scenario"""
        self.audio_files.append(AudioFile(file_path, description))
    
    def add_expected_response(self, response: str):
        """Add expected response pattern"""
        self.expected_responses.append(response)

# Pre-defined test scenarios
def get_banking_test_scenarios() -> List[TestScenario]:
    """Get predefined banking test scenarios"""
    scenarios = []
    
    # Scenario 1: Card Delivery Status
    card_scenario = TestScenario(
        "card_delivery_status",
        "Test card delivery status inquiry - primary MVP scenario"
    )
    card_scenario.add_audio_file("test_audio/card_delivery_query.wav", "Kart teslimat durumu nedir?")
    card_scenario.add_expected_response("Kartınızın teslimat durumu")
    card_scenario.timeout_seconds = 45
    scenarios.append(card_scenario)
    
    # Scenario 2: General Banking Inquiry
    general_scenario = TestScenario(
        "general_banking",
        "Test general banking conversation flow"
    )
    general_scenario.add_audio_file("test_audio/general_greeting.wav", "Merhaba, yardıma ihtiyacım var")
    general_scenario.add_expected_response("Nasıl yardımcı olabilirim")
    scenarios.append(general_scenario)
    
    # Scenario 3: Multiple Turns
    multi_turn = TestScenario(
        "multi_turn_conversation",
        "Test multi-turn conversation with context memory"
    )
    multi_turn.add_audio_file("test_audio/turn1.wav", "Hesap bakiyemi öğrenebilir miyim?")
    multi_turn.add_audio_file("test_audio/turn2.wav", "Geçen ay kaç işlem yapmışım?")
    multi_turn.timeout_seconds = 60
    scenarios.append(multi_turn)
    
    return scenarios

if __name__ == "__main__":
    # Example usage
    async def main():
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        simulator = RTPSimulator(target_port=10000)
        
        try:
            await simulator.setup_socket()
            
            # Test with silence first
            await simulator.send_silence(1000)
            
            print("RTP Simulator ready for testing!")
            print("Connect your application to receive RTP packets on port 10000")
            
        except KeyboardInterrupt:
            logger.info("Test interrupted by user")
        finally:
            simulator.close()
    
    asyncio.run(main())