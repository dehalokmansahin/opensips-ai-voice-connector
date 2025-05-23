# `speech_session_vosk.py` Module Workflow

## 1. Overview

The `speech_session_vosk.py` module provides a full-duplex (two-way) voice conversation system. It uses the [Vosk Toolkit](https://alphacephei.com/vosk/) for Speech-to-Text (STT) and [Piper TTS](https://github.com/rhasspy/piper) for Text-to-Speech (TTS).

This module is designed to be integrated into a larger voice response system, particularly one that handles audio input/output via RTP (Real-time Transport Protocol), common in telephony setups. It orchestrates the flow of audio, VAD (Voice Activity Detection), STT, and TTS to enable a conversational experience.

## 2. Core Components (Classes)

The module is structured around several key Python classes within `speech_session_vosk.py`:

*   **`SmartSpeech`**:
    *   This is the main engine and orchestrator of the entire speech session.
    *   It manages the lifecycle of STT and TTS services, including connecting to them and handling their states.
    *   It coordinates interactions between all other helper components.
    *   It implements the `AIEngine` interface (from `ai.py`).

*   **`AudioProcessor`**:
    *   Responsible for processing incoming raw audio data from the user.
    *   Typically, this audio is in PCMU format (G.711 µ-law, common in telephony, 8kHz sample rate).
    *   It decodes PCMU to PCM, resamples it to 16kHz (required by Vosk for STT), normalizes volume, and cleans the audio signal.
    *   Outputs audio as 16-bit integer PCM bytes suitable for STT.

*   **`VADProcessor`**:
    *   Manages Voice Activity Detection. It buffers the processed audio from `AudioProcessor`.
    *   When a sufficient chunk of audio is collected, it uses an underlying `VADDetector` (Silero VAD) to determine if speech is present.
    *   Based on configured thresholds for speech duration and silence, it decides when to start and stop sending audio to the STT engine (`VoskClient`). This prevents sending continuous silence and helps in segmenting user utterances.

*   **`TranscriptHandler`**:
    *   Receives and processes JSON messages containing transcription results from the Vosk STT server.
    *   It distinguishes between partial (interim) transcripts and final transcripts.
    *   It makes the latest transcripts available and triggers callbacks (specifically in `SmartSpeech`) when a final transcript is ready.

*   **`TTSProcessor`**:
    *   Manages Text-to-Speech audio generation.
    *   It uses an external `PiperClient` to connect to a Piper TTS server and request speech synthesis for a given text.
    *   The audio received from Piper (typically 22.05kHz, 16-bit PCM) is then processed:
        *   Resampled to 8kHz (common for telephony RTP streams).
        *   Converted to PCMU format.
    *   The processed PCMU audio chunks are put into an RTP queue (provided to `SmartSpeech`) for playback to the user.
    *   Crucially, it also handles "barge-in" requests: if the user starts speaking while TTS is playing, this processor can be interrupted to stop the playback.

### Related External Components:

These are separate classes, often in their own files, that the core components rely on:

*   **`VADDetector` (`vad_detector.py`)**:
    *   A wrapper around the Silero VAD model. It takes an audio chunk and returns whether speech is detected. Used by `VADProcessor`.
*   **`VoskClient` (`vosk_client.py`)**:
    *   Manages the WebSocket connection and communication protocol with the Vosk STT server.
*   **`PiperClient` (`piper_client.py`)**:
    *   (Assumed to exist, as `TTSProcessor` uses it) Manages the connection and synthesis requests to the Piper TTS server.

## 3. Workflow / Data Flow

The system operates asynchronously, handling user speech and system responses concurrently.

### Incoming Audio (User Speaking)

1.  **Audio Reception**: `SmartSpeech.send(audio_bytes)` is the entry point. It receives raw audio bytes (e.g., PCMU from an RTP stream).
2.  **Audio Processing**: The `audio_bytes` are passed to `AudioProcessor`.
    *   `AudioProcessor` decodes PCMU to raw PCM, resamples it from 8kHz to 16kHz, converts it to a float32 tensor, performs normalization (adjusts volume), and finally converts it to 16-bit integer PCM bytes.
3.  **VAD Buffering**: The 16kHz PCM audio bytes are sent to `VADProcessor.add_audio()`.
    *   `VADProcessor` accumulates these bytes in an internal buffer.
4.  **VAD Decision**: Once the buffer in `VADProcessor` reaches a configured size (e.g., 600ms of audio):
    *   It converts the buffer to a tensor and passes it to the `VADDetector` (Silero VAD).
    *   `VADDetector.is_speech()` returns `True` or `False`.
5.  **Sending to STT**:
    *   `VADProcessor` maintains a state (`speech_active`). If the VAD detector indicates speech for a configured number of consecutive chunks (making `speech_active` true), `VADProcessor` provides the buffered audio chunk.
    *   `SmartSpeech` then sends this audio chunk via `VoskClient` to the Vosk STT server over a WebSocket connection.

### Receiving Transcripts

1.  **Listening Loop**: `SmartSpeech.receive_transcripts()` runs as an asynchronous task, continuously listening for messages from the `VoskClient`.
2.  **Message Handling**: When `VoskClient` receives a message (which is a JSON string from Vosk):
    *   It's passed to `TranscriptHandler.handle_message()`.
    *   `TranscriptHandler` parses the JSON. It updates its internal state for `last_partial_transcript` or `last_final_transcript`.
3.  **Final Transcript Trigger**: If a final transcript ("text" field in Vosk JSON) is received and is non-empty:
    *   `TranscriptHandler` invokes the `SmartSpeech._handle_final_transcript()` callback method.

### Generating Spoken Response (TTS)

1.  **Handling Final Transcript**: `SmartSpeech._handle_final_transcript()` is triggered:
    *   It first ensures any previously active TTS task is cancelled (e.g., if user barged-in or if transcripts are arriving very fast).
    *   **LLM Interaction (Simulated)**: It currently uses a placeholder (random sentence selection) to simulate getting a text response from a Language Model (LLM) based on the `final_text`. In a real system, this would involve calling an LLM API.
    *   **VAD Reset**: It calls `VADProcessor.reset_vad_state()` to clear VAD history and prepare for detecting new user speech, especially to allow barge-in on the upcoming TTS.
    *   **Initiate TTS**: It calls `TTSProcessor.generate_and_queue_tts_audio()` with the text response from the LLM. This TTS generation runs as a new `asyncio.Task`, allowing `SmartSpeech` to remain responsive.
2.  **TTS Processing by `TTSProcessor`**:
    *   Connects to the Piper TTS server using `PiperClient`.
    *   Sends the text and voice parameters to Piper for synthesis.
    *   Receives audio chunks from Piper (typically 16-bit PCM at 22.05kHz).
    *   For each chunk:
        *   Resamples the audio to 8kHz (if `tts_target_output_rate` is 8000).
        *   Converts the 16-bit PCM audio to PCMU (G.711 µ-law) format.
        *   Packetizes the PCMU audio into appropriate chunk sizes (e.g., 160 bytes for 20ms packets).
    *   Puts these PCMU audio packets into the `rtp_queue` (which was provided to `SmartSpeech`). The external telephony system is expected to read from this queue and stream the audio back to the user.

### Barge-In (User Interrupts TTS)

Barge-in allows the user to speak and interrupt the system's TTS playback.

1.  **User Speaks During TTS**: If the user starts speaking while TTS audio is being generated and queued by `TTSProcessor`:
    *   The user's incoming audio still flows through `SmartSpeech.send()` -> `AudioProcessor` -> `VADProcessor`.
2.  **VAD Detects User Speech**: `VADProcessor` detects speech in the user's audio.
3.  **TTS Interruption Signal**:
    *   `SmartSpeech._handle_processed_audio()` (which receives VAD results) checks if a TTS task (`self.tts_task`) is active.
    *   If active, it calls `self.tts_processor.interrupt()`.
    *   It also cancels the `self.tts_task` (the `asyncio.Task` running `TTSProcessor.generate_and_queue_tts_audio()`).
4.  **`TTSProcessor` Handles Interruption**:
    *   `TTSProcessor.interrupt()`:
        *   Sets an internal `_interrupt_event`.
        *   Immediately drains any audio packets already placed in its `rtp_queue` by the current TTS process.
    *   The `generate_and_queue_tts_audio()` method in `TTSProcessor` checks this `_interrupt_event` at various points (e.g., before sending new data to Piper, in its audio processing callback). If the event is set, it stops its operations and cleans up (e.g., by raising `asyncio.CancelledError` which is then caught).

## 4. Configuration

Key parameters for the system are loaded by `SmartSpeech._load_config()` from a configuration object (typically an instance of `config.Config`). These include:

*   Vosk server URL (`url`) and STT audio parameters (`sample_rate`, `channels`).
*   VAD parameters: `bypass_vad`, `vad_threshold`, `vad_min_speech_ms`, `vad_min_silence_ms`, `vad_buffer_chunk_ms`, `speech_detection_threshold`, `silence_detection_threshold`.
*   Piper TTS server details: `TTS_HOST`, `TTS_PORT`, `TTS_VOICE`.
*   General behavior: `debug` logging, `send_eof` to Vosk.

These settings allow tuning the system's sensitivity, responsiveness, and connection details without modifying the core code.

## 5. Key Files

*   **`speech_session_vosk.py`**: Contains the `SmartSpeech` class and its helper components (`AudioProcessor`, `VADProcessor`, `TranscriptHandler`, `TTSProcessor`). This is the central file for the voice session logic.
*   **`vad_detector.py`**: Implements the `VADDetector` class, which is a wrapper for the Silero VAD model, providing the actual speech detection capability.
*   **`vosk_client.py`**: Implements the `VoskClient` class, responsible for managing the WebSocket connection and communication with the Vosk STT server.
*   **`piper_client.py`** (assumed): Would implement a `PiperClient` class for interacting with the Piper TTS server.
*   **`config.py`** (assumed): Provides the `Config` class used for loading application settings.
*   **`codec.py`** (assumed): Handles SDP parsing and codec definitions (like PCMU).
*   **`ai.py`** (assumed): Provides the base `AIEngine` class.

This structure separates concerns: client communication, VAD model specifics, and the main session orchestration logic are in different modules, making the system more modular and maintainable.
