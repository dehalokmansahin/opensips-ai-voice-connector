import asyncio
import wave
from speech_session_vosk import VoskSTT
from aiortc.sdp import SessionDescription
import torchaudio
import numpy as np
import torch
import logging
from queue import Queue

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

# Dummy Call objesi - Use Queue instead of asyncio.Queue to match production
class DummyCall:
    def __init__(self):
        self.b2b_key = "test-session-123"
        self.mi_conn = None
        self.sdp = sdp
        self.flavor = "vosk"
        self.to = "sip:destination@example.com"
        self.cfg = {"is_test_mode": True}
        self.rtp = Queue()  # Use the same Queue type as in production (from queue module)
        self.client_addr = "127.0.0.1"
        self.client_port = 4000
        self.terminated = False

async def main():
    call = DummyCall()

    cfg = {
        "vosk": {
            "url": "ws://localhost:2700",
            "sample_rate": 16000,
            "max_retries": 3,
            "retry_delay": 2.0,
            "websocket_timeout": 30.0,
            # Set bypass_vad to False to test VAD functionality with small chunks
            "bypass_vad": False,
            "vad_threshold": 0.12,  # Slightly more sensitive
            "vad_min_speech_ms": 40,  # Appropriate for multiple 20ms chunks
            "vad_min_silence_ms": 200,
            # Adjust VAD buffer settings for small chunks
            "vad_buffer_max_seconds": 1.0,  # Maximum buffer size
            "vad_buffer_flush_threshold": 0.2,  # More responsive flush
            "send_eof": True,
            "debug": True  # Enable debug for more verbose logging
        }
    }
    logging.info("Starting test: Loading audio file")
    waveform, sample_rate = torchaudio.load("C:/Cursor/opensips-ai-voice-connector/src/test.wav")
    logging.info(f"Loaded test.wav: {waveform.shape}, sample_rate={sample_rate}Hz")

    # Transkript callback'lerini tanımla
    async def on_partial_transcript(text):
        logging.info(f"Partial transcript: {text}")

    async def on_final_transcript(text):
        logging.info(f"Final transcript: {text}")

    stt = VoskSTT(call, cfg)
    stt.set_log_level(logging.DEBUG)  # Set to debug level for more detailed logs
    
    # Callback'leri ayarla
    stt.on_partial_transcript = on_partial_transcript
    stt.on_final_transcript = on_final_transcript
    
    # STT motorunu başlat (artık kendi içinde queue processor'ı da başlatacak)
    await stt.start()

    # --- Ses verisini hazırlama ve kuyruğa koyma --- 
    if waveform.size(0) > 1:
        waveform = waveform.mean(dim=0, keepdim=True)
        logging.info("Converted audio to mono")

    target_sample_rate = cfg['vosk']['sample_rate']
    if sample_rate != target_sample_rate:
        logging.info(f"Resampling from {sample_rate}Hz to {target_sample_rate}Hz")
        resampler_16k = torchaudio.transforms.Resample(orig_freq=sample_rate, new_freq=target_sample_rate)
        waveform_16k = resampler_16k(waveform)
        logging.info(f"Resampled to {target_sample_rate}Hz tensor shape: {waveform_16k.shape}")
    else:
        waveform_16k = waveform

    if waveform_16k.dim() > 1 and waveform_16k.size(0) == 1:
        waveform_16k = waveform_16k.squeeze(0)

    max_amplitude = torch.max(torch.abs(waveform_16k))
    if max_amplitude > 0 and max_amplitude < 0.8:
        gain = 0.8 / max_amplitude
        waveform_16k = waveform_16k * gain
        logging.info(f"Pre-amplified {target_sample_rate}Hz waveform by factor {gain:.2f}")

    # Use 20ms chunks to simulate real RTP packets from telephony systems
    chunk_duration_ms = 20  # Standard RTP packet size in telephony (G.711)
    chunk_size = int(target_sample_rate * (chunk_duration_ms / 1000.0))
    logging.info(f"Using chunk size: {chunk_size} samples ({chunk_duration_ms}ms) for {target_sample_rate}Hz audio")

    # Process audio in small chunks like real RTP packets
    num_samples = waveform_16k.size(0)
    for i in range(0, num_samples, chunk_size):
        chunk_tensor = waveform_16k[i:i + chunk_size]
        
        if chunk_tensor.numel() > 0:
            logging.debug(f"Putting float tensor chunk to queue: shape={chunk_tensor.shape}")
            # Put directly to queue without await since it's a standard Queue
            call.rtp.put(chunk_tensor)
        else:
            logging.warning(f"Skipping empty tensor chunk at index {i}")
            
        # Simulate real-time delay with precise timing
        await asyncio.sleep(chunk_duration_ms / 1000.0)

    # --- Allow some time for processing the last chunks --- 
    logging.info("Finished putting audio into queue. Waiting for processing...")
    await asyncio.sleep(2.0)  # Allow time for processing final chunks

    # Temiz kapanış için yeterli süre ver
    logging.info("Waiting for final processing to complete...")
    await asyncio.sleep(1.0)

    # STT motorunu kapat
    await stt.close()
    logging.info("STT session closed.")

if __name__ == "__main__":
    asyncio.run(main())
