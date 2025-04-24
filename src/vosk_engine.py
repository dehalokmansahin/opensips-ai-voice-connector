#!/usr/bin/env python
#
# Copyright (C) 2024 SIP Point Consulting SRL
#
# This file is part of the OpenSIPS AI Voice Connector project
# (see https://github.com/OpenSIPS/opensips-ai-voice-connector-ce).
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#

"""
Vosk STT implementation for the AIEngine interface
"""

import logging
import asyncio
import webrtcvad
from enum import Enum
from codec import UnsupportedCodec, CODECS

from ai import AIEngine
from stt_vosk import VoskSTT
from config import Config


class SpeechState(Enum):
    """State of the speech detection"""
    SILENCE = 0
    SPEAKING = 1
    POSSIBLE_END = 2
    BARGE_IN = 3  # New state for barge-in detection


class VoskSTTEngine(AIEngine):
    """
    Implementation of the AIEngine interface for Vosk STT
    """

    def __init__(self, call, cfg):
        """
        Initialize the VoskSTTEngine with the call and configuration
        
        Args:
            call: The Call object
            cfg: Configuration dictionary
        """
        self.call = call
        self.cfg = cfg
        self.config = Config.get("vosk")
        
        # VAD settings
        self.use_vad = self.config.getboolean("use_vad", "VOSK_USE_VAD", True)
        self.vad_aggressiveness = int(self.config.get("vad_aggressiveness", "VOSK_VAD_AGGRESSIVENESS", "2"))
        self.silence_frames_threshold = int(self.config.get("silence_frames_threshold", "VOSK_SILENCE_FRAMES", "10"))
        self.speech_frames_threshold = int(self.config.get("speech_frames_threshold", "VOSK_SPEECH_FRAMES", "3"))
        
        # Barge-in settings
        self.enable_barge_in = self.config.getboolean("enable_barge_in", "VOSK_ENABLE_BARGE_IN", True)
        self.barge_in_threshold = int(self.config.get("barge_in_threshold", "VOSK_BARGE_IN_THRESHOLD", "5"))
        self.is_tts_playing = False
        self.barge_in_callback = None
        
        # WebRTC VAD initialization
        self.vad = None
        if self.use_vad:
            try:
                self.vad = webrtcvad.Vad(self.vad_aggressiveness)
                logging.info(f"WebRTC VAD initialized with aggressiveness level {self.vad_aggressiveness}")
            except Exception as e:
                logging.error(f"Failed to initialize WebRTC VAD: {str(e)}")
                self.vad = None
                self.use_vad = False
        
        # State variables
        self.speech_state = SpeechState.SILENCE
        self.silence_frames = 0
        self.speech_frames = 0
        self.last_transcript = ""
        self.codec = None
        self.stt_client = None
        self.task = None
        self.sample_rate = 8000  # Default for PCMU/PCMA
        
        # Audio buffer - used for debugging/saving audio if needed
        self.buffer_audio = self.config.getboolean("buffer_audio", "VOSK_BUFFER_AUDIO", False)
        self.audio_buffer = bytearray() if self.buffer_audio else None
        
        # Process results async
        self.processing_queue = asyncio.Queue()
        
    def choose_codec(self, sdp):
        """
        Choose a compatible codec from the SDP
        
        Args:
            sdp: Session Description
            
        Returns:
            Codec: The selected codec
            
        Raises:
            UnsupportedCodec: If no compatible codec is found
        """
        # Prefer PCMU/PCMA (8kHz) for telephony
        codec_priorities = ["PCMU", "PCMA", "opus"]
        
        for codec_name in codec_priorities:
            for codec in sdp.media[0].rtp.codecs:
                if codec.name.upper() == codec_name:
                    if codec_name == "PCMU":
                        self.codec = CODECS["pcmu"](codec)
                        if codec.clockRate:
                            self.sample_rate = codec.clockRate
                        return self.codec
                    elif codec_name == "PCMA":
                        self.codec = CODECS["pcma"](codec)
                        if codec.clockRate:
                            self.sample_rate = codec.clockRate
                        return self.codec
                    elif codec_name == "opus":
                        self.codec = CODECS["opus"](codec)
                        if codec.clockRate:
                            self.sample_rate = codec.clockRate
                        return self.codec
        
        raise UnsupportedCodec("No supported codec found for Vosk STT")
    
    async def start(self):
        """
        Start the STT engine and create the WebSocket connection
        """
        logging.info("Starting Vosk STT engine")
        
        self.stt_client = VoskSTT(callback_func=self._handle_transcription)
        await self.stt_client.connect()
        
        # Start processing results
        self.task = asyncio.create_task(self._process_results())
        
        logging.info("Vosk STT engine started")
    
    async def send(self, audio):
        """
        Process incoming audio and send to Vosk
        
        Args:
            audio: Raw audio bytes from the codec
        """
        # Apply VAD if enabled
        if self.use_vad and len(audio) > 0 and self.vad:
            is_speech = self._detect_speech(audio)
            self._update_speech_state(is_speech)
            
            # Check for barge-in condition
            if self.enable_barge_in and self.is_tts_playing:
                if (self.speech_state == SpeechState.BARGE_IN and 
                    self.speech_frames >= self.barge_in_threshold):
                    await self._handle_barge_in()
        
        # Buffer audio if enabled (for debugging)
        if self.buffer_audio and audio:
            self.audio_buffer.extend(audio)
        
        # Send audio to Vosk regardless of VAD to allow its internal processing
        if self.stt_client:
            await self.stt_client.transcribe(audio)
            
            # Yield control to allow other tasks to run
            await asyncio.sleep(0)
    
    def _detect_speech(self, audio):
        """
        Use WebRTC VAD to detect speech in audio frame
        
        Args:
            audio: Raw audio bytes
            
        Returns:
            bool: True if speech is detected, False otherwise
        """
        try:
            # WebRTC VAD requires specific frame sizes
            # For 8kHz: frames should be 10, 20, or 30ms (80, 160, or 240 bytes for 16-bit PCM)
            # For now, we'll use 20ms frames (160 bytes for 8kHz)
            
            # Make sure we have enough audio data
            if len(audio) < 160:
                return False
                
            # Use just a 20ms frame from the data
            frame = audio[:160]
            
            # Check if the frame contains speech
            return self.vad.is_speech(frame, self.sample_rate)
        except Exception as e:
            logging.warning(f"Error in speech detection: {str(e)}")
            return False
    
    def _update_speech_state(self, is_speech):
        """
        Update the speech state based on VAD result
        
        Args:
            is_speech: Whether the current frame contains speech
        """
        if is_speech:
            # Reset silence counter when speech is detected
            self.silence_frames = 0
            self.speech_frames += 1
            
            # Transition to SPEAKING state after enough speech frames
            if self.speech_frames >= self.speech_frames_threshold:
                if self.speech_state != SpeechState.SPEAKING:
                    logging.debug("Speech detected")
                    
                    # If TTS is playing and we detect speech, this might be a barge-in
                    if self.is_tts_playing and self.enable_barge_in:
                        self.speech_state = SpeechState.BARGE_IN
                        logging.debug("Potential barge-in detected")
                    else:
                        self.speech_state = SpeechState.SPEAKING
        else:
            # In silence, increment silence counter and reset speech counter
            self.silence_frames += 1
            self.speech_frames = 0
            
            # Handle state transitions based on silence duration
            if self.speech_state == SpeechState.SPEAKING or self.speech_state == SpeechState.BARGE_IN:
                if self.silence_frames >= 2:  # Quick transition to possible end
                    self.speech_state = SpeechState.POSSIBLE_END
                    logging.debug("Possible end of speech detected")
            elif self.speech_state == SpeechState.POSSIBLE_END:
                if self.silence_frames >= self.silence_frames_threshold:
                    self.speech_state = SpeechState.SILENCE
                    logging.debug("End of speech confirmed")
    
    async def _handle_transcription(self, text, final=False):
        """
        Handle transcription results from Vosk
        
        Args:
            text: Transcribed text
            final: Whether this is a final result
        """
        # Only process final results or significant partials
        if final or (len(text) > len(self.last_transcript) + 5):
            self.last_transcript = text
            await self.processing_queue.put((text, final))
    
    async def _process_results(self):
        """
        Process transcription results from the queue
        """
        while True:
            try:
                text, final = await self.processing_queue.get()
                
                # Log the transcription
                log_prefix = "Final" if final else "Partial"
                logging.info(f"{log_prefix} transcription: {text}")
                
                # Only process results if they're not from the TTS audio bleeding into the mic
                # This helps prevent the system from responding to its own voice
                if self.is_tts_playing and not self.speech_state == SpeechState.BARGE_IN:
                    logging.debug("Ignoring transcription during TTS playback")
                    self.processing_queue.task_done()
                    continue
                
                # With more advanced VAD state tracking, we can determine when to process
                # a result based on both the VAD state and the final flag from Vosk
                
                # Example of using VAD state with transcription:
                if final and text and (not self.use_vad or 
                                       self.speech_state in [SpeechState.POSSIBLE_END, SpeechState.SILENCE]):
                    # In a real implementation, you'd likely send this to your AI system
                    logging.info(f"Processing final transcription: {text}")
                    
                    # You might want to inject a TTS response here
                    # await self.call.ai.inject_tts_response("I heard: " + text)
                    
                # Mark as done
                self.processing_queue.task_done()
                
                # Allow other tasks to run
                await asyncio.sleep(0)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"Error processing transcription: {str(e)}")
    
    async def close(self):
        """
        Clean up resources and close connections
        """
        logging.info("Closing Vosk STT engine")
        
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        
        if self.stt_client:
            await self.stt_client.close()
            
        if self.buffer_audio and self.audio_buffer:
            # Optionally save the audio buffer for debugging
            logging.info(f"Collected {len(self.audio_buffer)} bytes of audio")
            
        logging.info("Vosk STT engine closed")

    async def _handle_barge_in(self):
        """
        Handle barge-in detection by stopping TTS playback
        """
        logging.info(f"Barge-in detected with {self.speech_frames} speech frames, stopping TTS playback")
        self.speech_state = SpeechState.SPEAKING
        
        # Reset TTS playing flag
        was_playing = self.is_tts_playing
        self.is_tts_playing = False
        
        # Call the barge-in callback if registered
        if self.barge_in_callback and was_playing:
            asyncio.create_task(self.barge_in_callback())
        
        # Clear any existing transcription
        self.last_transcript = ""
        
        # You might want to implement more sophisticated barge-in handling
        # such as clearing the audio processing pipeline, etc.

    def register_barge_in_callback(self, callback):
        """
        Register a callback function to be called when barge-in is detected
        
        Args:
            callback: Async function to call on barge-in
        """
        self.barge_in_callback = callback
    
    def set_tts_playing(self, is_playing):
        """
        Set the TTS playing state for barge-in detection
        
        Args:
            is_playing: Whether TTS is currently playing
        """
        self.is_tts_playing = is_playing
        if is_playing:
            logging.debug("TTS playback started, barge-in detection enabled")
        else:
            logging.debug("TTS playback ended, barge-in detection disabled") 