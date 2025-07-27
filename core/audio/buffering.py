"""
Audio buffering for RTP stream processing
Implements jitter buffer and event replay buffer for reliable audio processing
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from collections import deque
import threading

logger = logging.getLogger(__name__)

@dataclass
class BufferedAudioPacket:
    """Audio packet with buffering metadata"""
    sequence_number: int
    timestamp: int
    payload: bytes
    received_time: float
    session_id: str
    packet_size: int = field(init=False)
    
    def __post_init__(self):
        self.packet_size = len(self.payload)

class JitterBuffer:
    """
    Jitter buffer for real-time audio smoothing
    Configurable depth for handling network jitter
    """
    
    def __init__(
        self, 
        buffer_depth_ms: int = 60, 
        sample_rate: int = 8000,
        frame_size_ms: int = 20,
        max_packet_loss_tolerance: float = 0.05
    ):
        self.buffer_depth_ms = buffer_depth_ms
        self.sample_rate = sample_rate
        self.frame_size_ms = frame_size_ms
        self.max_packet_loss_tolerance = max_packet_loss_tolerance
        
        # Calculate buffer parameters
        self.buffer_depth_packets = buffer_depth_ms // frame_size_ms
        self.samples_per_frame = (sample_rate * frame_size_ms) // 1000
        
        # Buffer storage
        self._buffer: Dict[int, BufferedAudioPacket] = {}
        self._lock = threading.RLock()
        
        # Sequence tracking
        self._expected_sequence = 0
        self._last_output_sequence = -1
        self._base_timestamp = 0
        
        # Statistics
        self._stats = {
            'packets_buffered': 0,
            'packets_output': 0,
            'packets_dropped_late': 0,
            'packets_dropped_duplicate': 0,
            'packets_interpolated': 0,
            'jitter_events': 0,
            'buffer_overflows': 0
        }
        
        logger.info(f"JitterBuffer initialized: depth={buffer_depth_ms}ms, "
                   f"packets={self.buffer_depth_packets}, frame_size={frame_size_ms}ms")
    
    def add_packet(self, packet: BufferedAudioPacket) -> bool:
        """Add packet to jitter buffer"""
        with self._lock:
            seq = packet.sequence_number
            
            # Check for duplicate packets
            if seq in self._buffer:
                self._stats['packets_dropped_duplicate'] += 1
                logger.debug(f"Dropping duplicate packet: seq={seq}")
                return False
            
            # Initialize expected sequence on first packet
            if self._expected_sequence == 0:
                self._expected_sequence = seq
                self._base_timestamp = packet.timestamp
            
            # Check if packet is too late (beyond buffer window)
            seq_diff = self._sequence_diff(seq, self._expected_sequence)
            if seq_diff < -self.buffer_depth_packets:
                self._stats['packets_dropped_late'] += 1
                logger.debug(f"Dropping late packet: seq={seq}, expected={self._expected_sequence}")
                return False
            
            # Check for buffer overflow
            if len(self._buffer) >= self.buffer_depth_packets * 2:
                self._handle_buffer_overflow()
                return False
            
            # Add packet to buffer
            self._buffer[seq] = packet
            self._stats['packets_buffered'] += 1
            
            logger.debug(f"Buffered packet: seq={seq}, buffer_size={len(self._buffer)}")
            return True
    
    def get_next_audio(self, interpolate_missing: bool = True) -> Optional[bytes]:
        """Get next audio data from buffer, with optional interpolation"""
        with self._lock:
            current_seq = self._expected_sequence
            
            # Check if expected packet is available
            if current_seq in self._buffer:
                packet = self._buffer.pop(current_seq)
                self._expected_sequence = (current_seq + 1) & 0xFFFF
                self._last_output_sequence = current_seq
                self._stats['packets_output'] += 1
                
                logger.debug(f"Output packet: seq={current_seq}")
                return packet.payload
            
            # Handle missing packet
            if interpolate_missing:
                # Simple interpolation: use silence or repeat last packet
                interpolated_audio = self._interpolate_missing_packet(current_seq)
                if interpolated_audio:
                    self._expected_sequence = (current_seq + 1) & 0xFFFF
                    self._last_output_sequence = current_seq
                    self._stats['packets_interpolated'] += 1
                    
                    logger.debug(f"Interpolated missing packet: seq={current_seq}")
                    return interpolated_audio
            
            # No packet available
            return None
    
    def _interpolate_missing_packet(self, sequence: int) -> Optional[bytes]:
        """Generate interpolated audio for missing packet"""
        try:
            # For PCMU, generate silence (0x7F is silence in μ-law)
            silence_byte = 0x7F
            expected_size = self.samples_per_frame  # PCMU = 1 byte per sample
            return bytes([silence_byte] * expected_size)
            
        except Exception as e:
            logger.error(f"Error interpolating packet {sequence}: {e}")
            return None
    
    def _sequence_diff(self, seq1: int, seq2: int) -> int:
        """Calculate sequence number difference handling wraparound"""
        diff = seq1 - seq2
        if diff > 32768:
            diff -= 65536
        elif diff < -32768:
            diff += 65536
        return diff
    
    def _handle_buffer_overflow(self):
        """Handle buffer overflow by removing oldest packets"""
        with self._lock:
            if not self._buffer:
                return
            
            # Remove oldest packets (lowest sequence numbers relative to expected)
            sorted_seqs = sorted(self._buffer.keys(), 
                               key=lambda x: self._sequence_diff(x, self._expected_sequence))
            
            # Remove oldest 25% of packets
            remove_count = max(1, len(sorted_seqs) // 4)
            for seq in sorted_seqs[:remove_count]:
                del self._buffer[seq]
            
            self._stats['buffer_overflows'] += 1
            logger.warning(f"Buffer overflow: removed {remove_count} packets")
    
    def get_buffer_status(self) -> Dict[str, Any]:
        """Get current buffer status"""
        with self._lock:
            return {
                'buffer_size': len(self._buffer),
                'max_buffer_size': self.buffer_depth_packets,
                'expected_sequence': self._expected_sequence,
                'last_output_sequence': self._last_output_sequence,
                'buffer_depth_ms': self.buffer_depth_ms,
                'stats': self._stats.copy()
            }
    
    def clear_buffer(self):
        """Clear all buffered packets"""
        with self._lock:
            self._buffer.clear()
            logger.info("Jitter buffer cleared")
    
    def reset_sequence(self):
        """Reset sequence tracking"""
        with self._lock:
            self._expected_sequence = 0
            self._last_output_sequence = -1
            self._base_timestamp = 0
            logger.info("Jitter buffer sequence reset")

class EventReplayBuffer:
    """
    Circular buffer for RTP packet history replay
    Enables recovery from temporary network interruptions
    """
    
    def __init__(self, buffer_size: int = 100, ttl_seconds: int = 30):
        self.buffer_size = buffer_size
        self.ttl_seconds = ttl_seconds
        
        # Circular buffer using deque
        self._buffer: deque = deque(maxlen=buffer_size)
        self._lock = threading.RLock()
        
        # Cleanup tracking
        self._last_cleanup = time.time()
        self._cleanup_interval = 5.0  # seconds
        
        # Statistics
        self._stats = {
            'packets_stored': 0,
            'packets_replayed': 0,
            'packets_expired': 0,
            'replay_requests': 0,
            'buffer_overflows': 0
        }
        
        logger.info(f"EventReplayBuffer initialized: size={buffer_size}, ttl={ttl_seconds}s")
    
    def store_packet(self, packet: BufferedAudioPacket):
        """Store packet in replay buffer"""
        with self._lock:
            # Add timestamp for TTL tracking
            replay_packet = {
                'packet': packet,
                'stored_time': time.time(),
                'replayed': False
            }
            
            # Check if buffer will overflow
            if len(self._buffer) >= self.buffer_size:
                self._stats['buffer_overflows'] += 1
            
            self._buffer.append(replay_packet)
            self._stats['packets_stored'] += 1
            
            # Periodic cleanup
            if time.time() - self._last_cleanup > self._cleanup_interval:
                self._cleanup_expired_packets()
    
    def replay_packets(
        self, 
        session_id: str, 
        start_sequence: int, 
        end_sequence: int
    ) -> List[BufferedAudioPacket]:
        """Replay packets within sequence range"""
        with self._lock:
            self._stats['replay_requests'] += 1
            replayed_packets = []
            
            current_time = time.time()
            
            for replay_entry in self._buffer:
                packet = replay_entry['packet']
                stored_time = replay_entry['stored_time']
                
                # Check TTL
                if current_time - stored_time > self.ttl_seconds:
                    continue
                
                # Check session match
                if packet.session_id != session_id:
                    continue
                
                # Check sequence range
                if self._sequence_in_range(packet.sequence_number, start_sequence, end_sequence):
                    replayed_packets.append(packet)
                    replay_entry['replayed'] = True
                    self._stats['packets_replayed'] += 1
            
            logger.info(f"Replayed {len(replayed_packets)} packets for session {session_id}, "
                       f"seq_range={start_sequence}-{end_sequence}")
            
            return sorted(replayed_packets, key=lambda p: p.sequence_number)
    
    def _sequence_in_range(self, seq: int, start: int, end: int) -> bool:
        """Check if sequence number is within range, handling wraparound"""
        if start <= end:
            return start <= seq <= end
        else:
            # Handle wraparound case
            return seq >= start or seq <= end
    
    def _cleanup_expired_packets(self):
        """Remove expired packets from buffer"""
        with self._lock:
            current_time = time.time()
            expired_count = 0
            
            # Remove expired packets from front of deque
            while self._buffer:
                replay_entry = self._buffer[0]
                if current_time - replay_entry['stored_time'] > self.ttl_seconds:
                    self._buffer.popleft()
                    expired_count += 1
                else:
                    break
            
            if expired_count > 0:
                self._stats['packets_expired'] += expired_count
                logger.debug(f"Cleaned up {expired_count} expired packets")
            
            self._last_cleanup = current_time
    
    def get_buffer_status(self) -> Dict[str, Any]:
        """Get replay buffer status"""
        with self._lock:
            return {
                'buffer_size': len(self._buffer),
                'max_buffer_size': self.buffer_size,
                'ttl_seconds': self.ttl_seconds,
                'stats': self._stats.copy()
            }
    
    def clear_buffer(self):
        """Clear all buffered packets"""
        with self._lock:
            self._buffer.clear()
            logger.info("Replay buffer cleared")
    
    def force_cleanup(self):
        """Force cleanup of expired packets"""
        with self._lock:
            self._cleanup_expired_packets()