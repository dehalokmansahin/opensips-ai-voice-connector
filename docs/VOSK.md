# Vosk STT Engine (`src/stt_vosk.py`) Method Documentation

This document describes the methods within the `VoskSTT` class, which handles real-time speech-to-text transcription using a Vosk server via WebSocket.

## `VoskSTT` Class Methods

### `_load_configuration(self, cfg)`
*   **Purpose:** Loads configuration settings required for the Vosk STT engine.
*   **Functionality:**
    *   Detects if the input `cfg` is a `ConfigParser` object or a standard configuration object (like the one provided by `config.py`).
    *   Reads values for `url` (Vosk server WebSocket URL), `sample_rate` (target sample rate Vosk expects), and `max_queue_size` (buffer for outgoing audio).
    *   Prioritizes values from the configuration object/file section (`[vosk]`).
    *   Uses environment variables (`VOSK_URL`, `VOSK_SAMPLE_RATE`, `VOSK_MAX_QUEUE_SIZE`) as fallbacks if values are not found in the config object.
    *   Performs basic validation (e.g., ensuring URL is present, converting rates/sizes to integers).
    *   Returns a dictionary containing the loaded configuration values.
*   **Type:** Private helper method.

### `__init__(self, call, cfg)`
*   **Purpose:** Initializes the `VoskSTT` engine instance for a specific call.
*   **Functionality:**
    *   Calls `_load_configuration` to get settings.
    *   Stores the `call` object and configuration values (`vosk_server_url`, `target_sample_rate`, `max_queue_size`).
    *   Extracts the `b2b_key` from the call for logging.
    *   If a `call` object with SDP (Session Description Protocol) information is provided, calls `choose_codec` to select the appropriate audio codec.
    *   If no call/SDP is available (e.g., testing), creates a dummy codec assuming direct PCM input matching the target sample rate.
    *   Initializes state variables:
        *   `websocket`: Holds the WebSocket connection object (initially `None`).
        *   `connection_task`, `receive_task`, `send_task`: Placeholders for the asyncio tasks managing the connection, receiving transcriptions, and sending audio (initially `None`).
        *   `send_queue`: An `asyncio.Queue` to buffer audio chunks *to* be sent to Vosk.
        *   `transcription_queue`: An `asyncio.Queue` to store transcription results received *from* Vosk.
        *   `is_active`: Boolean flag indicating if the engine is running (initially `False`).
        *   `stop_event`: An `asyncio.Event` used to signal tasks to stop gracefully.
    *   Initializes reconnection logic variables (`consecutive_errors`, `reconnection_attempts`).
*   **Type:** Constructor.

### `choose_codec(self, sdp)`
*   **Purpose:** Selects the most suitable audio codec from the call's SDP, ensuring compatibility with the target Vosk sample rate.
*   **Functionality:**
    *   Parses available codecs from the SDP using `get_codecs`.
    *   Prioritizes preferred codecs (`pcma`, `pcmu` - G.711 variants) as they are easily convertible to PCM.
    *   Iterates through preferred codecs found in the SDP.
    *   **Crucially, checks if the `sample_rate` of the selected codec matches the `self.target_sample_rate` configured for Vosk.**
    *   If the rates do **not** match, it logs a warning and skips that codec (since resampling is no longer implemented).
    *   If rates match, it checks if the codec has a `decode` method (defined in `codec.py`). Logs a warning if not, assuming raw pass-through is acceptable (only valid if the incoming audio is already PCM at the target rate).
    *   Returns the chosen and validated `codec` object.
    *   Raises `UnsupportedCodec` error if no suitable codec with a matching sample rate is found in the SDP.
*   **Type:** Public instance method (called by `__init__`).

### `_connect_and_manage(self)`
*   **Purpose:** Manages the lifecycle of the WebSocket connection to the Vosk server, including connection, task management, and reconnection logic.
*   **Functionality:**
    *   Runs in a loop as long as the engine `is_active` and the `stop_event` is not set.
    *   Attempts to connect to `self.vosk_server_url` using `websockets.connect` with a timeout.
    *   On successful connection:
        *   Stores the connection in `self.websocket`.
        *   Resets error/reconnection counters.
        *   Sends an initial configuration message to Vosk specifying the `sample_rate`.
        *   Creates and starts the `_send_loop` and `_receive_loop` asyncio tasks.
        *   Waits for either the send or receive task to complete (indicating potential closure or error).
        *   Cleans up any pending tasks upon completion of one.
        *   Handles exceptions from completed tasks (e.g., `ConnectionClosed`).
    *   On connection failure or disconnection:
        *   Catches various exceptions (`InvalidURI`, `WebSocketException`, `ConnectionRefusedError`, `OSError`, etc.).
        *   Increments `consecutive_errors`.
        *   Cleans up websocket object and any potentially running send/receive tasks.
        *   Implements exponential backoff with jitter for reconnection attempts.
        *   Limits the number of reconnection attempts (e.g., 5). If limit is reached, sets `is_active` to `False` and stops trying.
        *   Listens for the `stop_event` during the backoff delay to allow graceful shutdown.
    *   Ensures cleanup (closing websocket) when the loop exits.
*   **Type:** Private async instance method (run as a task).

### `_send_loop(self)`
*   **Purpose:** Continuously takes audio data from the `send_queue` and sends it to the connected Vosk WebSocket server.
*   **Functionality:**
    *   Runs in a loop as long as the engine `is_active`, the `stop_event` is not set, and a `websocket` connection exists.
    *   Waits for and retrieves an `audio_data` chunk from `self.send_queue`.
    *   Checks if the selected `self.codec` has a `decode` method. If yes, calls it to convert the audio chunk (e.g., PCMU) to PCM data.
    *   Performs a sanity check to ensure the source audio sample rate matches the target Vosk rate. Logs a fatal error and skips the chunk if they mismatch (this should ideally be prevented by `choose_codec`).
    *   Ensures the final `pcm_data` to be sent is in `bytes` format (converting from numpy array if necessary).
    *   Sends the processed `pcm_data` over the WebSocket using `self.websocket.send()`.
    *   Marks the task in the `send_queue` as done.
    *   Handles `ConnectionClosed` exceptions by re-raising them to be caught by `_connect_and_manage`.
    *   When the loop exits (e.g., due to `stop_event`), attempts to send a final `{"eof": 1}` message to Vosk to signal the end of the audio stream.
*   **Type:** Private async instance method (run as a task).

### `_receive_loop(self)`
*   **Purpose:** Continuously listens for messages (transcription results) from the Vosk WebSocket server.
*   **Functionality:**
    *   Runs in a loop, iterating through messages received from `self.websocket`.
    *   Checks `stop_event` on each iteration for graceful shutdown.
    *   Parses incoming messages assuming they are JSON (`json.loads`).
    *   Distinguishes between partial and final results:
        *   If the JSON contains a `"partial"` key with non-empty text, puts `{"type": "partial", "text": ...}` into `self.transcription_queue`.
        *   If the JSON contains a `"text"` key with non-empty text (indicating a final result for a segment), puts `{"type": "final", "text": ...}` into `self.transcription_queue`.
    *   Handles potential `JSONDecodeError` if a non-JSON message is received.
    *   Handles `ConnectionClosed` exceptions by re-raising them to be caught by `_connect_and_manage`.
*   **Type:** Private async instance method (run as a task).

### `start(self)`
*   **Purpose:** Public method to start the Vosk STT engine.
*   **Functionality:**
    *   Checks if the engine is already active or if the URL is configured.
    *   Sets `self.is_active` to `True`.
    *   Clears the `self.stop_event`.
    *   Creates and starts the main `_connect_and_manage` asyncio task, storing it in `self.connection_task`.
*   **Type:** Public async instance method.

### `send(self, audio)`
*   **Purpose:** Public method for external code (like `callhandler.py`) to queue raw audio data to be sent to Vosk.
*   **Functionality:**
    *   Checks if the engine is active and not stopping. Returns immediately if not.
    *   Ensures the input `audio` is in `bytes` format. Attempts conversion if not, discarding if conversion fails.
    *   Checks if the `self.send_queue` is full. If full, logs a warning, discards the *oldest* item from the queue to make space, and then attempts to add the new item.
    *   Adds the `audio` chunk to the `self.send_queue` using `put_nowait`. Handles potential `QueueFull` exceptions (should be rare after the check).
*   **Type:** Public async instance method.

### `get_transcription(self, timeout=0.1)`
*   **Purpose:** Public method for external code to retrieve the next available transcription result (partial or final).
*   **Functionality:**
    *   Checks if the engine is inactive and the queue is empty; returns `None` if so.
    *   Uses `asyncio.wait_for` to attempt getting an item from `self.transcription_queue` with a specified `timeout`.
    *   Returns the transcription result dictionary (`{"type": ..., "text": ...}`) if available within the timeout.
    *   Returns `None` if the queue is empty or the timeout expires.
    *   Handles potential exceptions during queue retrieval.
*   **Type:** Public async instance method.

### `close(self)`
*   **Purpose:** Public method to gracefully shut down the Vosk STT engine and release resources.
*   **Functionality:**
    *   Checks if the engine is already inactive.
    *   Sets `self.is_active` to `False` to prevent new operations and stop loops.
    *   Sets the `self.stop_event` to signal all running tasks (`_connect_and_manage`, `_send_loop`, `_receive_loop`) to terminate.
    *   Identifies active asyncio tasks associated with this instance.
    *   Cancels these tasks (`task.cancel()`).
    *   Waits for the tasks to complete cancellation using `asyncio.wait` with a timeout. Logs a warning if tasks don't cancel within the timeout.
    *   Attempts to explicitly close the WebSocket connection (`self.websocket.close()`) if it's still open.
    *   Resets task and websocket instance variables to `None`.
    *   (Optionally, could clear the queues, but current code leaves them).
*   **Type:** Public async instance method.

## RTP Paket İşleme Optimizasyonları

VoskSTT sistemi, telefon sistemlerinden 20ms aralıklarla gelen küçük RTP paketlerini etkin bir şekilde işlemek için özel olarak tasarlanmıştır. Standart VoIP telefonlar genellikle ses verilerini 20ms uzunluğundaki paketler halinde gönderir. Bu kısa ses parçaları tek başlarına anlamlı konuşma içeriğine sahip olmayabilir, bu nedenle sistem şu özelliklere sahiptir:

### Ardışık Paket İzleme

- Sistem, gelen RTP paketlerini izler ve "konuşma" veya "sessizlik" olarak sınıflandırır
- Konuşma algılandığında `consecutive_speech_packets` sayacı artırılır
- Belirli sayıda ardışık konuşma paketi algılandığında (varsayılan: 3 paket), sistem "konuşma aktif" moduna geçer
- Benzer şekilde, belirli sayıda ardışık sessizlik paketi algılandığında (varsayılan: 10 paket), sistem "konuşma aktif" modundan çıkar

Bu yaklaşım, tek tek 20ms paketlerinin VAD değerlendirmesinden daha güvenilir konuşma algılama sağlar.

### VAD Buffer Yönetimi

Ses Aktivite Algılama (VAD) sistemi, küçük RTP paketlerini bir araya getirerek daha doğru konuşma tespiti yapar:

- Gelen ses, VAD (Ses Aktivite Algılama) kontrolünden geçirilir
- Konuşma içeren veya "konuşma aktif" modundayken alınan paketler bir buffer'da biriktirilir
- Konuşma aktif durumdayken, buffer daha sık boşaltılır (her 100ms'de bir)
- Konuşma aktif olmadığında, buffer sadece yeterli veri toplandığında veya uzun süre sessizlik algılandığında boşaltılır

Bu buffer stratejisi, küçük RTP paketlerini daha büyük ses parçalarına birleştirerek Vosk'un daha doğru transkripsiyon yapmasını sağlar.

### Gerçek Zamanlı İşlem

Sistem, konuşma akışının gerçek zamanlı doğasını dikkate alacak şekilde tasarlanmıştır:

- Konuşma aktif olduğunda, daha düşük gecikme için buffer daha sık boşaltılır
- Sessiz geçen paketler sırasında, sistem buffer içeriğini düzenli aralıklarla gönderir
- Maksimum buffer süresi (varsayılan: 1 saniye) ile aşırı gecikme önlenir
- Buffer en son boşaltıldıktan sonra geçen süre izlenir ve 1 saniyeden fazla süre geçtiğinde buffer boşaltılır

## Vosk Sunucusu Kurulumu

Vosk'u yerel bir sunucuda çalıştırmak için Docker kullanmanız önerilir. Örnek bir Docker komutu:

```bash
docker run -d -p 2700:2700 alphacep/kaldi-en:latest
```

Bu komut İngilizce için optimize edilmiş bir Vosk sunucusu başlatır. Farklı diller için [Vosk Docker Hub](https://hub.docker.com/r/alphacep/kaldi-en) sayfasına bakabilirsiniz.

## Yapılandırma

Vosk motoru için aşağıdaki parametreler ayarlanabilir:

| Bölüm | Parametre | Çevre Değişkeni | Zorunlu | Açıklama | Varsayılan |
|-------|-----------|-----------------|---------|----------|------------|
| `vosk` | `url` | `VOSK_URL` | hayır | Vosk WebSocket sunucusunun URL'si | `ws://localhost:2700` |
| `vosk` | `sample_rate` | `VOSK_SAMPLE_RATE` | hayır | Hedeflenen örnekleme oranı | `16000` |
| `vosk` | `vad_threshold` | `VOSK_VAD_THRESHOLD` | hayır | VAD hassasiyeti (0-1 arası) | `0.12` |
| `vosk` | `vad_min_speech_ms` | `VOSK_VAD_MIN_SPEECH_MS` | hayır | Minimum konuşma süresi (ms) | `40` |
| `vosk` | `vad_min_silence_ms` | `VOSK_VAD_MIN_SILENCE_MS` | hayır | Minimum sessizlik süresi (ms) | `200` |
| `vosk` | `bypass_vad` | `VOSK_BYPASS_VAD` | hayır | VAD'yi devre dışı bırakır | `false` |
| `vosk` | `speech_detection_threshold` | `VOSK_SPEECH_DETECTION_THRESHOLD` | hayır | Konuşma aktivasyonu için gereken ardışık konuşma paketi sayısı | `3` |
| `vosk` | `silence_detection_threshold` | `VOSK_SILENCE_DETECTION_THRESHOLD` | hayır | Konuşma deaktivasyonu için gereken ardışık sessizlik paketi sayısı | `10` |
| `vosk` | `vad_buffer_max_seconds` | `VOSK_VAD_BUFFER_MAX_SECONDS` | hayır | Maksimum buffer süresi (saniye) | `1.0` |
| `vosk` | `vad_buffer_flush_threshold` | `VOSK_VAD_BUFFER_FLUSH_THRESHOLD` | hayır | Buffer boşaltma eşik değeri (saniye) | `0.2` |
| `vosk` | `send_eof` | `VOSK_SEND_EOF` | hayır | Oturum sonunda EOF sinyali gönder | `true` |
| `vosk` | `debug` | `VOSK_DEBUG` | hayır | Ayrıntılı debug log'larını etkinleştirir | `false` |

## Test Etme

Vosk entegrasyonunu test etmek için, Vosk sunucusunun çalıştığından emin olun ve bir SIP çağrısı başlatın. Alternatif olarak, gerçek RTP davranışını simüle eden `run_local_stt_test.py` betiğini çalıştırabilirsiniz:

```bash
python src/run_local_stt_test.py
```

Bu test betiği, ses dosyasını 20ms'lik RTP paketlerine bölerek gerçek dünya VoIP çağrı senaryosunu simüle eder. 