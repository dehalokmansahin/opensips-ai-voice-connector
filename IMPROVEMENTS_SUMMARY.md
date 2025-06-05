# OpenSIPS AI Voice Connector - VAD/STT/TTS Flow Improvements

## Problem Analysis

Based on the provided logs, the main issues identified were:

1. **Speech detection without final transcripts**: VAD would detect speech start/end events, partial transcripts would be received from Vosk, but no final transcripts were generated, preventing TTS activation.

2. **Timeout-related logic gaps**: The system lacked timeout mechanisms to handle cases where Vosk doesn't provide timely final transcripts.

3. **Concurrency issues**: Poor yielding in asyncio tasks could cause blocking.

4. **State management problems**: VAD state wasn't properly synchronized with transcript handling.

5. **Ambient noise and microphone level variations**: Different environments caused inconsistent VAD performance.

6. **Echo from TTS audio**: The TTS voice would sometimes echo back through the microphone and be detected as user speech.

## Key Improvements Implemented

### 1. **Timeout-Based Final Transcript Generation**

Added three timeout mechanisms:

- **Speech Timeout** (10s default): Forces final transcript if user speaks too long
- **Silence Timeout** (3s default): Forces final transcript after prolonged silence
- **Stale Partial Timeout** (2.5s default): Promotes unchanged partial transcripts to final

**Implementation:**
- New `_monitor_vad_timeouts()` background task in `SmartSpeech`
- New `_force_final_transcript()` method for timeout-based transcript generation
- Enhanced `VADProcessor` with timing tracking methods

### 2. **Enhanced VAD State Management**

**VADProcessor improvements:**
- Added speech timing tracking (`speech_start_time`, `last_speech_activity_time`)
- Improved state reset logic with better buffer management
- Fixed logical errors in `_process_buffer()` method
- Added timeout detection methods (`has_speech_timeout()`, `has_silence_timeout()`)

### 3. **Improved Transcript Handling**

**TranscriptHandler enhancements:**
- Added partial transcript timing tracking
- New `has_stale_partial()` method to detect stuck partials
- Enhanced timestamp tracking for timeout detection
- Better state clearing methods

### 4. **Better Concurrency and Error Handling**

- Added proper asyncio yielding in audio processing loops
- Enhanced task cancellation and cleanup in `close()` method
- Improved error recovery and state management
- Better handling of background tasks (timeout monitor)

### 5. **Configurable Parameters**

Added new configuration options:
```
speech_timeout_seconds: 10.0      # Maximum speech duration
silence_timeout_seconds: 3.0      # Maximum silence after speech  
stale_partial_timeout_seconds: 2.5 # Maximum unchanged partial time
```

### 6. **Adaptive VAD with Ambient Noise Calibration**

Added a new `AdaptiveVADDetector` that extends the standard Silero VAD with:

- **Dynamic threshold adjustment**: Automatically calibrates VAD sensitivity based on audio characteristics
- **Noise floor analysis**: Measures background noise levels to optimize detection
- **Signal-to-noise ratio (SNR) calculation**: Adjusts thresholds based on SNR
- **Audio history tracking**: Maintains a sliding window of recent audio to inform calibration

**Implementation:**
- New `AdaptiveVADDetector` class that extends `VADDetector`
- Configurable calibration window and parameters
- Detailed logging of calibration decisions

### 7. **Echo Cancellation for TTS Audio**

Added echo cancellation to prevent TTS audio from being detected as user speech:

- **TTS audio registration**: Tracks TTS audio to identify potential echoes
- **WebRTC VAD integration**: Uses webrtcvad as a secondary confirmation for speech during potential echo periods
- **Cooldown periods**: Implements silence periods after TTS to avoid false detections
- **TTS state tracking**: Coordinates between TTS and VAD components

**Implementation:**
- Integration between `TTSProcessor` and `AdaptiveVADDetector`
- WebRTC VAD for echo verification
- Configurable cooldown periods and aggressiveness settings

## Code Changes Summary

### Files Modified/Added:

1. **`src/speech_session_vosk.py`**:
   - Enhanced `VADProcessor` class with timing and timeout detection
   - Added timeout monitoring task to `SmartSpeech` class
   - Improved `TranscriptHandler` with partial timing tracking
   - Added configurable timeout parameters
   - Enhanced error handling and state management

2. **`src/README.md`**:
   - Added comprehensive troubleshooting guide in Turkish
   - Updated documentation with new features and configuration options
   - Added performance tuning recommendations

3. **`src/speech_processing/adaptive_vad.py`** (New):
   - Created `AdaptiveVADDetector` class extending `VADDetector`
   - Implemented calibration logic for ambient noise adaptation
   - Added echo cancellation using webrtcvad
   - Added TTS audio registration and tracking

4. **`src/speech_processing/tts_processor.py`**:
   - Added integration with VAD for echo cancellation
   - Added TTS state notification (start/end)

5. **`src/speech_processing/speech_session_manager.py`**:
   - Updated to use `AdaptiveVADDetector` when enabled
   - Added configuration for adaptive VAD parameters
   - Enhanced TTS-VAD coordination

6. **`requirements.txt`**:
   - Added webrtcvad dependency for echo cancellation

### Key Methods Added/Modified:

- `VADProcessor.has_speech_timeout()`
- `VADProcessor.has_silence_timeout()`
- `TranscriptHandler.has_stale_partial()`
- `TranscriptHandler.clear_transcripts()`
- `SmartSpeech._monitor_vad_timeouts()`
- `SmartSpeech._force_final_transcript()`
- `AdaptiveVADDetector._update_calibration()`
- `AdaptiveVADDetector._should_ignore_due_to_echo()`
- `AdaptiveVADDetector.register_tts_audio()`
- `AdaptiveVADDetector.tts_finished()`
- `TTSProcessor.generate_and_queue_tts_audio()` - Updated to notify VAD of TTS activity

## Testing Recommendations

1. **Test speech timeout**: Speak continuously for more than 10 seconds
2. **Test silence timeout**: Speak, then remain silent for more than 3 seconds
3. **Test stale partial handling**: Create scenarios where Vosk provides partials but no finals
4. **Test barge-in functionality**: Interrupt TTS with speech
5. **Test error recovery**: Disconnect/reconnect Vosk server during operation
6. **Test adaptive calibration**: Test in both quiet and noisy environments
7. **Test echo cancellation**: Ensure TTS audio doesn't trigger false VAD detections
8. **Test microphone sensitivity**: Try with different microphone input levels

## Configuration Examples

### For Quick Response Environments:
```yaml
speech_timeout_seconds: 8.0
silence_timeout_seconds: 2.0
stale_partial_timeout_seconds: 2.0
vad_threshold: 0.2
speech_detection_threshold: 1
silence_detection_threshold: 1
```

### For Noisy Environments:
```yaml
speech_timeout_seconds: 12.0
silence_timeout_seconds: 4.0
stale_partial_timeout_seconds: 3.0
vad_threshold: 0.3
speech_detection_threshold: 2
silence_detection_threshold: 2
```

### For Echo Cancellation and Adaptive VAD:
```yaml
use_adaptive_vad: true
auto_calibration: true
webrtc_aggressiveness: 2  # 0-3, higher is more aggressive
calibration_window_ms: 5000
```

## Expected Behavior After Improvements

1. **Consistent TTS activation**: Even when Vosk doesn't provide final transcripts, the system will generate them via timeouts
2. **Better responsiveness**: Reduced latency between speech end and TTS start
3. **Improved stability**: Better error recovery and state management
4. **Enhanced logging**: More detailed logs for troubleshooting
5. **Configurable behavior**: Tunable parameters for different environments
6. **Adaptive noise handling**: Better performance across different environments
7. **Reduced false activations**: Echo cancellation prevents TTS audio from being detected as user speech
8. **More consistent detection**: Calibration adjusts for quiet or loud speakers

## Monitoring and Debugging

**Key log messages to watch for:**
- `Speech timeout detected. Forcing final transcript generation.`
- `Silence timeout detected. Forcing final transcript generation.`
- `Stale partial transcript detected. Promoting to final.`
- `Forcing final transcript from partial due to [reason]`
- `VAD timeout monitor task cancelled.`
- `High noise environment detected. Increasing threshold to X.XX`
- `Low noise environment detected. Decreasing threshold to X.XX`
- `Registered TTS audio with VAD detector for echo cancellation`
- `WebRTC VAD detected X/Y speech frames during TTS/cooldown`

These improvements should significantly enhance the robustness of the voice activity detection system, especially in varying acoustic environments and when dealing with TTS audio echoes. 