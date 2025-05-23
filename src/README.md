# Speech Session Module (`speech_session_vosk.py`)

## 1. Overview

The `speech_session_vosk.py` module provides a session-based, full-duplex speech recognition (STT) and text-to-speech (TTS) engine. It is designed for integration into voice response systems, such as those handling telephony calls (e.g., via OpenSIPS).

This module uses [Vosk](https://alphacephei.com/vosk/) for speech-to-text and a [Piper](https://github.com/rhasspy/piper) client for text-to-speech, enabling interactive voice conversations. It manages the complexities of audio processing, voice activity detection, STT/TTS communication, and session state.

## 2. Core Components (Classes)

The module is composed of several key classes that work together:

*   **`SmartSpeech`**:
    *   The central orchestrator for an STT/TTS session.
    *   It manages the overall lifecycle, including receiving audio input, coordinating VAD and STT processing, handling final transcripts, simulating application/LLM logic, and initiating TTS responses.
    *   It integrates all other components.

*   **`AudioProcessor`**:
    *   Handles raw audio processing tasks for incoming audio destined for STT.
    *   This includes decoding PCMU (G.711 mu-law) audio, cleaning the audio signal (e.g., removing NaN/Inf values), normalizing volume, and resampling it to the target sample rate required by the Vosk STT engine (typically 16kHz).

*   **`VADProcessor`**:
    *   Performs voice activity detection on the processed audio stream.
    *   It buffers audio, identifies speech segments, and manages speech/silence state transitions using configurable thresholds to robustly detect the start and end of user speech.

*   **`TranscriptHandler`**:
    *   Manages partial and final transcripts received from the Vosk STT engine.
    *   It provides callbacks that `SmartSpeech` uses to react to these transcription events.

*   **`TTSProcessor`**:
    *   Handles text-to-speech synthesis using a Piper TTS client.
    *   It takes text input, communicates with the Piper server, and processes the received TTS audio.
    *   This processing includes resampling the TTS audio to the required output format (typically 8kHz for PCMU) and encoding it to PCMU.
    *   The processed audio is then queued for playback.

*   **`VoskClient`** (Utility, defined externally but used by `SmartSpeech`):
    *   A wrapper for WebSocket communication with the Vosk STT server. It handles connection management and sending/receiving STT messages.

*   **`PiperClient`** (Utility, defined externally but used by `TTSProcessor`):
    *   A client for interacting with the Piper TTS service, managing WebSocket communication for speech synthesis.

## 3. Workflow

The typical flow of operations within a `SmartSpeech` session is as follows:

1.  **Audio Input**: `SmartSpeech` receives audio packets (e.g., PCMU from an RTP stream via an external call object).
2.  **Preprocessing**: The `AudioProcessor` (within `SmartSpeech`) decodes the PCMU audio, converts it to a suitable tensor format, and resamples it for the STT engine (e.g., to 16kHz).
3.  **VAD**: The `VADProcessor` analyzes the audio stream to detect human speech, distinguishing it from silence or noise. It determines segments of audio that likely contain speech.
4.  **STT**: Audio segments identified as speech are sent to the Vosk STT server via the `VoskClient`.
5.  **Transcription**: The `TranscriptHandler` receives partial and final transcription results from Vosk.
6.  **Application Logic (Simulated)**: Upon receiving a final transcript, `SmartSpeech`'s `_handle_final_transcript` method is triggered. Currently, this method simulates generating a response text (as if from a Language Model or business logic).
7.  **TTS Initiation**: The generated response text is passed to the `TTSProcessor`.
8.  **VAD Reset & Queue Drain**: Before TTS audio generation, `SmartSpeech` resets the `VADProcessor` state (to prepare for user barge-in) and the `TTSProcessor` drains any residual audio from the outgoing RTP queue.
9.  **Synthesis**: The `TTSProcessor` uses the `PiperClient` to connect to a Piper TTS server and synthesize the response text into an audio stream (typically 16-bit PCM at a rate like 22050Hz).
10. **Output Audio Processing**: The `TTSProcessor` receives the synthesized audio, resamples it to the final target rate (e.g., 8kHz for telephony), and encodes it into PCMU format.
11. **Playback**: The processed PCMU audio chunks are put onto an RTP queue (provided to `SmartSpeech` during initialization) to be sent back to the user.

## 4. Configuration

The module's behavior is controlled by various configuration parameters, typically loaded via a central configuration system (represented by `cfg` in the code, using `Config.get("vosk", cfg)`).

Key configurable parameters include:

*   **Vosk STT Settings**:
    *   `url`: WebSocket URL of the Vosk STT server (e.g., `ws://localhost:2700`).
    *   `sample_rate`: Target sample rate for STT processing (e.g., `16000`).
    *   `websocket_timeout`: Timeout for WebSocket operations with Vosk.
    *   `channels`: Number of audio channels (typically `1`).
    *   `send_eof`: Boolean, whether to send an EOF signal to Vosk.
*   **VAD Settings**:
    *   `bypass_vad`: Boolean, to disable VAD and send all audio to STT.
    *   `vad_threshold`: Sensitivity threshold for VAD.
    *   `vad_min_speech_ms`: Minimum duration of speech to be considered valid.
    *   `vad_min_silence_ms`: Minimum duration of silence to mark end of speech.
    *   `vad_buffer_chunk_ms`: Size of audio chunks processed by VAD.
    *   `speech_detection_threshold`: Consecutive speech packets to activate speech mode.
    *   `silence_detection_threshold`: Consecutive silence packets to deactivate speech mode.
*   **Piper TTS Settings**:
    *   `TTS_HOST`: Hostname of the Piper TTS server.
    *   `TTS_PORT`: Port number of the Piper TTS server.
    *   `TTS_VOICE`: Name of the voice to be used for synthesis (e.g., `tr_TR-fahrettin-medium`).
    *   (TTS target output rate is hardcoded to 8000 Hz for PCMU).
*   **General**:
    *   `debug`: Boolean, enables detailed debug logging throughout the module.

## 5. Dependencies

The module relies on several Python libraries and external services:

*   **Python Libraries**:
    *   `websockets`: For asynchronous WebSocket communication with Vosk and Piper servers.
    *   `torch`, `torchaudio`: For audio tensor operations, resampling, and potentially VAD models.
    *   `audioop`: A standard Python module for audio operations, specifically `lin2ulaw` for PCMU encoding.
    *   `json`: For parsing messages from the Vosk STT server.
    *   `logging`: For structured logging.
    *   `asyncio`: For asynchronous operations.
    *   `queue`: For managing the RTP audio output queue.
    *   `typing`: For type hinting.
    *   `traceback`: For detailed exception logging.
    *   `random`: Used for simulating LLM responses.
    *   (Note: `numpy` is not directly imported but NumPy arrays are handled as intermediate data types from `pcmu_decoder`.)

*   **External Services**:
    *   **Vosk STT Server**: A running instance of a Vosk STT server, accessible via WebSocket.
    *   **Piper TTS Server**: A running instance of a Piper TTS server, accessible via WebSocket.

*   **Internal Project Modules**:
    *   `codec`, `pcmu_decoder`: For audio codec handling.
    *   `vad_detector`: Provides the VAD model/logic.
    *   `config`: For accessing configuration parameters.
    *   `ai`: Provides the base `AIEngine` class.
    *   `vosk_client`, `piper_client`: Client implementations for Vosk and Piper services.

## 6. Error Handling and Logging

*   The module incorporates error handling using `try-except` blocks in critical operations, such as network communication, audio processing, and task management.
*   Detailed logging is implemented throughout the module, using the standard `logging` library.
*   Log messages include a `session_id` for easier traceability of operations within a specific call or session.
*   The verbosity of logging can be controlled by the `debug` configuration flag, which enables more detailed `DEBUG` level logs. The `set_log_level` method in `SmartSpeech` can also be used to dynamically change the logging level.
*   Exceptions are generally logged with tracebacks (`exc_info=True`) to aid in debugging.

## 7. Usage (Conceptual)

In a typical application (e.g., a SIP-based voice bot):

1.  An instance of `SmartSpeech` is created when a new call session begins. It's initialized with a `call` object (representing the telephony call and providing an RTP queue for outgoing audio) and a configuration object `cfg`.
2.  The `SmartSpeech.start()` method is called to connect to the Vosk server and prepare for processing.
3.  As audio packets arrive from the user (e.g., via RTP), they are fed into the `SmartSpeech.send(audio_bytes)` method.
4.  The `SmartSpeech` instance internally processes this audio, performs VAD, gets transcripts, simulates LLM responses, and triggers TTS via `TTSProcessor`.
5.  The `TTSProcessor` generates audio and puts it onto the RTP queue provided by the `call` object for playback to the user.
6.  This cycle continues for the duration of the interaction.
7.  When the call ends, the `SmartSpeech.close()` method is called to gracefully shut down the connections, cancel ongoing tasks, and clean up resources.

The `SmartSpeech` class acts as an `AIEngine`, abstracting the complexities of the STT/TTS pipeline for the calling application.
The title of the README was also updated from "# Speech Session Vosk (`speech_session_vosk.py`)" to "# Speech Session Module (`speech_session_vosk.py`)" as "Vosk" was specific to the old class name.The class `VoskSTT` in `src/speech_session_vosk.py` has been renamed to `SmartSpeech`. This change has been applied to the class definition, constructor logs, method logs, and comments within the Python file.

Additionally, the `src/README.md` file has been updated to reflect this name change. All occurrences of "VoskSTT" that referred to the class have been replaced with "SmartSpeech". The title of the README was also updated to be more generic: "# Speech Session Module (`speech_session_vosk.py`)".

The changes ensure consistency in naming across the Python module and its documentation.
