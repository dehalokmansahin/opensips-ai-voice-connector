import asyncio
import wave
from src.speech_session_vosk import VoskSTT
from aiortc.sdp import SessionDescription
import numpy as np
import logging
# Removed queue import as it's no longer used for input simulation
# from queue import Queue 
import g711 # Use g711 library
import sounddevice as sd # Import sounddevice
# Use standard queue for thread safety between sync callback and async task
from queue import Queue as SyncQueue 
# Remove signal import as it's not supported on Windows event loop
# import signal 

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
        except queue.Empty: # Catch the timeout from queue.get
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
        except queue.Empty:
            break
            
    logging.info("Audio queue processor finished.")

# --- Main Function --- 
async def main():
    call = DummyCall()

    cfg = {
        "vosk": {
            "url": "ws://localhost:2700",
            "sample_rate": 16000, # VoskSTT internal target rate
            "max_retries": 3,
            "retry_delay": 2.0,
            "websocket_timeout": 30.0,
            "bypass_vad": False, 
            "vad_threshold": 0.12, 
            "vad_min_speech_ms": 40, 
            "vad_min_silence_ms": 500, # Increased silence duration might help finalize transcripts
            "vad_buffer_chunk_ms": 750, 
            "send_eof": True,
            "debug": True 
        }
    }
    # Remove WAV file loading
    # audio_file_path = "C:/Cursor/opensips-ai-voice-connector/src/test.wav"
    # try:
    #     waveform, sample_rate = torchaudio.load(audio_file_path)
    #     logging.info(f"Loaded audio file: {audio_file_path}")
    # except Exception as e:
    #     logging.error(f"Failed to load audio file {audio_file_path}: {e}")
    #     return

    # Transcript callbacks (optional but recommended)
    # async def on_partial_transcript(text):
    #     logging.info(f"Partial transcript: {text}")
    # async def on_final_transcript(text):
    #     logging.info(f"Final transcript: {text}")

    stt = VoskSTT(call, cfg)
    stt.set_log_level(logging.INFO) 
    
    # Set callbacks if defined
    # stt.transcript_handler.on_partial_transcript = on_partial_transcript
    # stt.transcript_handler.on_final_transcript = on_final_transcript
    
    await stt.start()
    if not stt.vosk_client.is_connected:
         logging.error("Failed to start Vosk STT session. Exiting.")
         return

    # Start the queue processing task, passing the sync queue
    queue_processor_task = asyncio.create_task(process_audio_queue(stt, call, sync_audio_queue))

    # --- Setup Microphone Stream --- 
    target_mic_samplerate = 8000
    block_duration_ms = 20 # Process audio in 20ms chunks like RTP
    mic_blocksize = int(target_mic_samplerate * (block_duration_ms / 1000.0))
    
    stream = None
    stop_event = asyncio.Event() # We can still use the event for other potential stops

    # Remove signal handler function
    # def signal_handler():
    #     logging.info("Stop signal received, shutting down.")
    #     stop_event.set()

    # Remove signal handler registration loop
    # loop = asyncio.get_running_loop()
    # for sig in (signal.SIGINT, signal.SIGTERM):
    #     loop.add_signal_handler(sig, signal_handler)

    # Wrap the main streaming part in try/except KeyboardInterrupt
    try:
        try:
            logging.info(f"Starting microphone stream: {target_mic_samplerate} Hz, {mic_blocksize} frames/block")
            # Ensure default device supports 8kHz mono float32
            sd.check_input_settings(samplerate=target_mic_samplerate, channels=1, dtype='float32') # Check if supported
            stream = sd.InputStream(
                samplerate=target_mic_samplerate,
                blocksize=mic_blocksize, 
                channels=1, 
                dtype='float32', 
                callback=sounddevice_callback
            )
            stream.start()
            logging.info("Microphone stream started. Press Ctrl+C to stop.")
            
            # Keep running indefinitely (or until KeyboardInterrupt)
            # stop_event.wait() is not strictly needed for Ctrl+C but can be kept 
            # if you want another way to signal stop programmatically.
            # For simple Ctrl+C, an infinite loop or just waiting on the task works too.
            # Let's wait on the queue processor task to keep the main coroutine alive.
            # await stop_event.wait()
            await queue_processor_task # Wait for the processor task (which runs until call.terminated)

        except sd.PortAudioError as pae:
             logging.error(f"PortAudio error: {pae}")
             logging.error("Common causes: Sample rate not supported by device, or device unavailable.")
             # Try to list devices for debugging
             try:
                 logging.info("Available audio devices:")
                 logging.info(sd.query_devices())
             except Exception:
                 logging.error("Could not query audio devices.")
        except Exception as e:
            logging.error(f"Error during microphone streaming: {e}", exc_info=True)
            
    except KeyboardInterrupt:
        logging.info("Ctrl+C pressed, initiating shutdown...")
        # The finally block will handle the shutdown
        pass # Exception is caught, proceed to finally
        
    finally:
        logging.info("Shutdown sequence initiated...") # Added log
        logging.info("Stopping microphone stream...")
        if stream:
            stream.stop()
            stream.close()
            logging.info("Microphone stream stopped.")
        
        # Signal the queue processor to stop and wait for it
        logging.info("Stopping audio queue processor...")
        call.terminated = True # Signal queue processor loop to exit
        try:
            # Put None as a sentinel value into the standard queue
            # This doesn't need await or timeout as put() on sync queue is blocking 
            # but should be fast if queue is not full (which it shouldn't be)
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

        # Close STT session
        logging.info("Closing STT session...")
        await stt.close()
        logging.info("STT session closed.")

# Remove old file processing loop
# num_bytes = len(pcmu_bytes)
# for i in range(0, num_bytes, chunk_size_bytes):
# ... (rest of loop) ...

if __name__ == "__main__":
    # Removed the outer try/except KeyboardInterrupt here, 
    # it's handled within main() now.
    # try:
    asyncio.run(main())
    # except KeyboardInterrupt:
    #     logging.info("Script interrupted by user.")
