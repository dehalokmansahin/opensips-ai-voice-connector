#!/usr/bin/env python3

import asyncio
import websockets
import numpy as np
from scipy import signal
import soundfile as sf

async def run_test(uri):

    try:
        # Load audio using soundfile (handles various formats including mu-law)
        audio_data, sample_rate = sf.read("test.wav", dtype='int16') # Read as int16
        channels = 1 if audio_data.ndim == 1 else audio_data.shape[1]

        print(f"Audio file: test.wav")
        print(f"Original Sample rate: {sample_rate} Hz")
        print(f"Original Channels: {channels}")
        
        # Check if format needs conversion (rate or channels)
        needs_conversion = (sample_rate != 16000 or channels != 1)
        
        # Use the loaded audio_data (NumPy array)
        np_data = audio_data 

        # Process audio data if conversion is needed
        if needs_conversion:
            print("Converting audio to 16kHz mono PCM format...")

            # Convert to mono if needed by averaging channels
            if channels > 1:
                print(f"Converting from {channels} channels to mono...")
                if np_data.ndim > 1: # Should already be the case if channels > 1
                    np_data = np.mean(np_data, axis=1).astype(np.int16)
                # No need for interleaved handling, soundfile gives separate dimensions

            # --- Start of Resampling Logic (Keep the improved float32 logic) ---
            # Ensure data is float32 for resampling
            # Normalize int16 data
            if np.issubdtype(np_data.dtype, np.integer):
                max_val = np.iinfo(np_data.dtype).max
                np_data_float = np_data.astype(np.float32) / max_val
            else: # Should already be int16 from sf.read, but handle defensively
                 np_data_float = np_data.astype(np.float32)

            # Resample if needed
            if sample_rate != 16000:
                print(f"Resampling from {sample_rate}Hz to 16000Hz...")
                gcd = np.gcd(sample_rate, 16000)
                up = 16000 // gcd
                down = sample_rate // gcd
                np_data_float = signal.resample_poly(np_data_float, up, down)
            
            # Convert back to int16 for Vosk
            np_data_float = np.clip(np_data_float, -1.0, 1.0) 
            processed_data_int16 = (np_data_float * 32767).astype(np.int16)
            # --- End of Resampling Logic ---

            # Convert final int16 data to bytes
            processed_data = processed_data_int16.tobytes()
            final_sample_rate = 16000  # Set to target rate

            # Send processed data
            async with websockets.connect(uri) as websocket:
                await websocket.send('{ "config" : { "sample_rate" : %d } }' % (final_sample_rate))
                chunk_size = int(final_sample_rate * 0.2) * 2
                for i in range(0, len(processed_data), chunk_size):
                    chunk = processed_data[i:i + chunk_size]
                    if not chunk:
                        break
                    await websocket.send(chunk)
                    print(await websocket.recv())
                await websocket.send('{"eof" : 1}')
                print(await websocket.recv())

        else:
            # No conversion needed, send original data directly
            processed_data = np_data.tobytes() # np_data is the original int16 data
            final_sample_rate = sample_rate # Original rate is already 16000
            async with websockets.connect(uri) as websocket:
                await websocket.send('{ "config" : { "sample_rate" : %d } }' % (final_sample_rate))
                chunk_size = int(final_sample_rate * 0.2) * 2 # Use sample_rate (16000), width is 2 bytes (int16)
                for i in range(0, len(processed_data), chunk_size):
                    chunk = processed_data[i:i + chunk_size]
                    if not chunk:
                         break
                    await websocket.send(chunk)
                    print(await websocket.recv())
                await websocket.send('{"eof" : 1}')
                print(await websocket.recv())
            
    except FileNotFoundError:
        print(f"Error: The file 'test.wav' was not found.")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(run_test('ws://localhost:2700'))