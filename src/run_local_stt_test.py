import asyncio
import wave
from speech_session_vosk import VoskSTT
from aiortc.sdp import SessionDescription
import numpy as np
import logging
import g711 # Use g711 library
import sounddevice as sd # Import sounddevice
from queue import Queue as SyncQueue, Empty
import threading  # For audio output thread
import traceback  # Add traceback for detailed error reporting

# Configure logging
logging.basicConfig(level=logging.INFO,  # Change level to DEBUG
                    format='%(asctime)s - %(levelname)s - %(message)s')
                    
logging.info("Starting OpenSIPS AI Voice Connector test with Vosk and Piper")

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

# Dummy Call object with RTP queue for TTS output
class DummyCall:
    def __init__(self):
        self.b2b_key = "test-session-123"
        self.mi_conn = None
        self.sdp = sdp
        self.flavor = "vosk_piper"  # Updated to match the new engine name
        self.to = "sip:destination@example.com"
        self.cfg = {"is_test_mode": True}
        self.rtp = SyncQueue()  # This queue will receive TTS output
        self.client_addr = "127.0.0.1"
        self.client_port = 4000
        self.terminated = False

# --- Sounddevice Callback and Queue --- 
# Use standard Queue for communication between sync callback and async task
sync_audio_queue = SyncQueue()

def sounddevice_callback(indata, frames, time, status):
    """This is called (from a separate thread) for each audio block."""
    if status:
        logging.warning(f"Sounddevice status: {status}")
    # Assuming indata is float32 mono 8kHz as requested from InputStream
    # Ensure it's 1D for encode_ulaw
    indata_1d = indata.flatten()
    try:
        pcmu_bytes = g711.encode_ulaw(indata_1d)
        # Put data into the standard queue (thread-safe)
        sync_audio_queue.put_nowait(pcmu_bytes)
        # logging.debug(f"Queued {len(pcmu_bytes)} PCMU bytes from mic") # DEBUG - Can be noisy
    except Exception as e:
        logging.error(f"Error encoding mic data to PCMU: {e}", exc_info=True)

async def process_audio_queue(stt: VoskSTT, call: DummyCall, sync_queue: SyncQueue):
    """Reads from the standard queue and sends data to VoskSTT."""
    logging.info("Audio queue processor started.")
    loop = asyncio.get_running_loop()
    while not call.terminated:
        try:
            # Use run_in_executor to wait for item from sync queue without blocking async loop
            # Use a short timeout to prevent waiting forever if the stop signal isn't put
            pcmu_bytes = await loop.run_in_executor(
                None, # Use default executor (ThreadPoolExecutor)
                lambda: sync_queue.get(timeout=0.1) # Blocking get with timeout
            ) 
            
            if pcmu_bytes is None: # Signal to stop
                logging.info("Stop signal received in audio queue.")
                sync_queue.task_done() # Mark the None item as processed
                break
                
            # logging.debug(f"Sending {len(pcmu_bytes)} PCMU bytes from queue to STT") # DEBUG - Can be noisy
            await stt.send(pcmu_bytes)
            sync_queue.task_done()
        except asyncio.CancelledError:
            logging.info("Audio queue processor cancelled.")
            break
        except Empty: # Catch the timeout from queue.get
            # Queue was empty, just continue waiting
            await asyncio.sleep(0.01) # Small sleep to yield control
            continue
        except Exception as e:
            logging.error(f"Error processing audio queue: {e}", exc_info=True)
            # Avoid busy-looping on error
            await asyncio.sleep(0.1)
            
    # Drain the queue in case the loop exited while items remained (e.g., due to call.terminated)
    logging.info("Draining remaining items from sync queue...")
    while True:
        try:
            sync_queue.get_nowait()
            sync_queue.task_done()
        except Empty:
            break
            
    logging.info("Audio queue processor finished.")

# --- Audio Output Processing Function ---
def tts_output_processor(call: DummyCall):
    """Process audio output (TTS) from the RTP queue and play via sounddevice."""
    logging.info("TTS output processor started.")
    
    # Create output stream for 8kHz mono audio
    output_stream = sd.OutputStream(
        samplerate=8000,  # PCMU is always 8000 Hz
        channels=1,
        dtype='float32',
        blocksize=160  # Standard 20ms RTP packet size for 8kHz audio
    )
    
    try:
        output_stream.start()
        logging.info("Audio output stream started.")
        
        # Process RTP queue until call is terminated
        while not call.terminated:
            try:
                # Get PCMU audio data (with short timeout to check termination flag)
                pcmu_bytes = call.rtp.get(timeout=0.1)
                
                # Decode PCMU to float32 (expected by sounddevice)
                float_samples = g711.decode_ulaw(pcmu_bytes)  # Assuming this returns float32 samples
                
                # Ensure data is in right format for sounddevice
                if isinstance(float_samples, np.ndarray):
                    # Make sure the data is shaped as expected (mono channel)
                    if float_samples.ndim > 1:
                        float_samples = float_samples.flatten()
                else:
                    # Convert to numpy array if needed
                    float_samples = np.array(float_samples, dtype=np.float32)
                
                # Write to audio output stream
                output_stream.write(float_samples)
                
                # Mark item as processed
                call.rtp.task_done()
                
            except Empty:
                # No data in queue, continue checking
                continue
            except Exception as e:
                logging.error(f"Error processing TTS output: {e}", exc_info=True)
                # Avoid busy-looping on error
                import time
                time.sleep(0.1)
                
    except Exception as e:
        logging.error(f"Error in TTS output processor: {e}", exc_info=True)
    finally:
        # Clean up resources
        try:
            if output_stream.active:
                output_stream.stop()
            output_stream.close()
            logging.info("Audio output stream closed.")
        except Exception as e:
            logging.error(f"Error closing audio output stream: {e}", exc_info=True)
        
        logging.info("TTS output processor finished.")

# --- Main Function --- 
async def main():
    call = DummyCall()

    # Updated configuration with both STT and TTS settings
    cfg = {
        "vosk_piper": {  # This is the engine name
            "vosk": {  # Nested vosk config
                "url": "ws://localhost:2700",
                "sample_rate": 16000,
                "max_retries": 3,
                "retry_delay": 2.0,
                "websocket_timeout": 30.0,
                "bypass_vad": False, 
                "vad_threshold": 0.12, 
                "vad_min_speech_ms": 40, 
                "vad_min_silence_ms": 500,
                "vad_buffer_chunk_ms": 750, 
                "send_eof": True,
                "debug": False
            },
            "piper_tts": {  # Nested piper_tts config
                "host": "localhost",
                "port": 10200,  # Wyoming Piper default port
                "voice": "tr_TR-fahrettin-medium"  # Adjust to match your available voice
            },
            "debug": False
        }
    }
    
    logging.debug(f"Configuration structure: {cfg}")
    
    try:
        stt = VoskSTT(call, cfg)
        stt.set_log_level(logging.INFO)
        
        await stt.start()
        if not stt.vosk_client.is_connected:
             logging.error("Failed to start Vosk STT session. Exiting.")
             return

        # Start the microphone queue processing task
        queue_processor_task = asyncio.create_task(process_audio_queue(stt, call, sync_audio_queue))
        
        # Start the TTS output processor in a separate thread
        tts_output_thread = threading.Thread(
            target=tts_output_processor,
            args=(call,),
            daemon=True  # Make it a daemon so it exits when main thread exits
        )
        tts_output_thread.start()
        logging.info("TTS output processor thread started.")

        # --- Setup Microphone Stream --- 
        target_mic_samplerate = 8000
        block_duration_ms = 20 # Process audio in 20ms chunks like RTP
        mic_blocksize = int(target_mic_samplerate * (block_duration_ms / 1000.0))
        
        stream = None
        stop_event = asyncio.Event()

        try:
            try:
                logging.info(f"Starting microphone stream: {target_mic_samplerate} Hz, {mic_blocksize} frames/block")
                # Ensure default device supports 8kHz mono float32
                sd.check_input_settings(samplerate=target_mic_samplerate, channels=1, dtype='float32')
                stream = sd.InputStream(
                    samplerate=target_mic_samplerate,
                    blocksize=mic_blocksize, 
                    channels=1, 
                    dtype='float32', 
                    callback=sounddevice_callback
                )
                stream.start()
                logging.info("Microphone stream started. Press Ctrl+C to stop.")
                logging.info("Speak into your microphone to test both STT and TTS!")
                
                await queue_processor_task

            except sd.PortAudioError as pae:
                 logging.error(f"PortAudio error: {pae}")
                 logging.error("Common causes: Sample rate not supported by device, or device unavailable.")
                 try:
                     logging.info("Available audio devices:")
                     logging.info(sd.query_devices())
                 except Exception:
                     logging.error("Could not query audio devices.")
            except Exception as e:
                logging.error(f"Error during microphone streaming: {e}", exc_info=True)
            
        except KeyboardInterrupt:
            logging.info("Ctrl+C pressed, initiating shutdown...")
        
        finally:
            logging.info("Shutdown sequence initiated...")
            logging.info("Stopping microphone stream...")
            if stream:
                stream.stop()
                stream.close()
                logging.info("Microphone stream stopped.")
            
            # Signal the queue processor to stop and wait for it
            logging.info("Stopping audio queue processor...")
            call.terminated = True
            try:
                sync_audio_queue.put(None)
            except Exception as e:
                 logging.error(f"Error putting stop signal in sync queue: {e}")
                 
            if queue_processor_task:
                try:
                    await asyncio.wait_for(queue_processor_task, timeout=2.0)
                except asyncio.TimeoutError:
                    logging.warning("Queue processor task did not finish promptly, cancelling.")
                    queue_processor_task.cancel()
                except Exception as e:
                     logging.error(f"Error waiting for queue processor task: {e}")

            # Wait for TTS thread to finish (should exit due to call.terminated flag)
            logging.info("Waiting for TTS output processor to finish...")
            try:
                # Only wait a short time to avoid hanging if the thread is stuck
                tts_output_thread.join(timeout=2.0)
                if tts_output_thread.is_alive():
                    logging.warning("TTS output thread did not finish promptly.")
            except Exception as e:
                logging.error(f"Error waiting for TTS output thread: {e}")

            # Close STT session
            logging.info("Closing STT session...")
            await stt.close()
            logging.info("STT session closed.")

    except Exception as e:
        logging.error(f"Error initializing VoskSTT: {e}")
        logging.error(f"Traceback: {traceback.format_exc()}")
        return

if __name__ == "__main__":
    asyncio.run(main())
