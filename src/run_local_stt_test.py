import asyncio
import wave
from speech_session_vosk import VoskSTT
from aiortc.sdp import SessionDescription
import torchaudio
import numpy as np
import torch
import logging
# Removed queue import as it's no longer used for input simulation
# from queue import Queue 
import g711 # Use g711 library

# Configure logging
logging.basicConfig(level=logging.DEBUG, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

TEST_SDP = """v=0
o=- 0 0 IN IP4 127.0.0.1
s=-
c=IN IP4 127.0.0.1
t=0 0
m=audio 49170 RTP/AVP 0 8 96
a=rtpmap:0 PCMU/8000
a=rtpmap:8 PCMA/8000
a=rtpmap:96 opus/48000/2
"""
sdp = SessionDescription.parse(TEST_SDP)

# Dummy Call objesi - rtp queue is no longer used for input by VoskSTT
class DummyCall:
    def __init__(self):
        self.b2b_key = "test-session-123"
        self.mi_conn = None
        self.sdp = sdp
        self.flavor = "vosk"
        self.to = "sip:destination@example.com"
        self.cfg = {"is_test_mode": True}
        # self.rtp = Queue() # No longer needed for input simulation
        self.client_addr = "127.0.0.1"
        self.client_port = 4000
        self.terminated = False

async def main():
    call = DummyCall()

    cfg = {
        "vosk": {
            "url": "ws://localhost:2700",
            "sample_rate": 16000, # VoskSTT internal target rate
            "max_retries": 3,
            "retry_delay": 2.0,
            "websocket_timeout": 30.0,
            "bypass_vad": False, # Test VAD
            "vad_threshold": 0.12, 
            "vad_min_speech_ms": 40, 
            "vad_min_silence_ms": 200,
            "vad_buffer_chunk_ms": 750, # Use the VAD buffering
            # Removed vad_buffer_max_seconds and vad_buffer_flush_threshold as they might be outdated/removed
            "send_eof": True,
            "debug": True 
        }
    }
    # Ensure the path to your test audio file is correct
    audio_file_path = "C:/Cursor/opensips-ai-voice-connector/src/test.wav"
    try:
        waveform, sample_rate = torchaudio.load(audio_file_path)
        logging.info(f"Loaded audio file: {audio_file_path}")
    except Exception as e:
        logging.error(f"Failed to load audio file {audio_file_path}: {e}")
        return

    # Transkript callback'lerini tanımla
    async def on_partial_transcript(text):
        logging.info(f"Partial transcript: {text}")

    async def on_final_transcript(text):
        logging.info(f"Final transcript: {text}")

    stt = VoskSTT(call, cfg)
    stt.set_log_level(logging.INFO) # Set to INFO or DEBUG as needed
    
    # Callback'leri ayarla
    stt.transcript_handler.on_partial_transcript = on_partial_transcript
    stt.transcript_handler.on_final_transcript = on_final_transcript
    
    # STT motorunu başlat
    await stt.start()

    # --- Ses verisini hazırlama ve gönderme (8kHz PCMU bytes) ---
    if waveform.size(0) > 1:
        waveform = waveform.mean(dim=0, keepdim=True)
        logging.info("Converted audio to mono")

    target_input_sample_rate = 8000 # We need 8kHz input for the STT process initially
    if sample_rate != target_input_sample_rate:
        logging.info(f"Resampling from {sample_rate}Hz to {target_input_sample_rate}Hz")
        resampler_8k = torchaudio.transforms.Resample(orig_freq=sample_rate, new_freq=target_input_sample_rate)
        waveform_8k = resampler_8k(waveform) # This is a float32 tensor
        logging.info(f"Resampled to {target_input_sample_rate}Hz tensor shape: {waveform_8k.shape}")
    else:
        waveform_8k = waveform # Already a float32 tensor

    if waveform_8k.dim() > 1 and waveform_8k.size(0) == 1:
        waveform_8k = waveform_8k.squeeze(0)

    # Convert the 8kHz float32 tensor directly to a NumPy array
    # No need to convert to int16 first
    pcm32_samples_np = waveform_8k.numpy()
    logging.debug(f"Converted 8kHz tensor to float32 NumPy array, shape: {pcm32_samples_np.shape}")

    # Encode float32 NumPy array to PCMU bytes using g711
    try:
        # g711.encode_ulaw expects a float32 NumPy array
        pcmu_bytes = g711.encode_ulaw(pcm32_samples_np)
        logging.info(f"Encoded float32 audio ({len(pcm32_samples_np)} samples) to {len(pcmu_bytes)} bytes of PCMU data (g711)")
    except Exception as e:
        logging.error(f"Failed to encode audio to PCMU using g711: {e}", exc_info=True)
        await stt.close()
        return

    # Send 20ms chunks of PCMU bytes
    chunk_duration_ms = 20 
    chunk_size_bytes = int(target_input_sample_rate * (chunk_duration_ms / 1000.0)) # 160 bytes for 8kHz PCMU
    logging.info(f"Using PCMU chunk size: {chunk_size_bytes} bytes ({chunk_duration_ms}ms)")

    # Process audio in small chunks
    num_bytes = len(pcmu_bytes)
    for i in range(0, num_bytes, chunk_size_bytes):
        chunk_bytes = pcmu_bytes[i:i + chunk_size_bytes]
        
        if len(chunk_bytes) > 0:
            # Pad the last chunk if it's smaller than expected (using standard PCMU silence 0xFF)
            if len(chunk_bytes) < chunk_size_bytes:
                 padding_needed = chunk_size_bytes - len(chunk_bytes)
                 chunk_bytes += bytes([0xFF] * padding_needed) 
                 logging.debug(f"Padded last chunk with {padding_needed} bytes of silence")

            logging.debug(f"Sending PCMU chunk: {len(chunk_bytes)} bytes")
            await stt.send(chunk_bytes) 
        else:
            logging.warning(f"Skipping empty byte chunk at index {i}")
            
        await asyncio.sleep(chunk_duration_ms / 1000.0)

    # --- Allow some time for processing the last chunks --- 
    logging.info("Finished sending audio bytes. Waiting for final processing...")
    
    # Wait a bit longer to ensure VAD buffer is processed and final transcript is received
    await asyncio.sleep(2.0) 

    # STT motorunu kapat
    await stt.close()
    logging.info("STT session closed.")

if __name__ == "__main__":
    asyncio.run(main())
