# Smart Speech Akış Diyagramı

Bu doküman, **OpenSIPS AI Voice Connector (OAVC)** projesinde Smart Speech bileşeninin nasıl çalıştığını adım adım geliştirici perspektifinden açıklar. Aşağıdaki adımlar, çağrı açılmasından TTS/STT entegrasyonuna, VAD ile barge-in'e ve kapanışa kadar kod akışını senaryolar üzerinden inceler.

---

## 1. Çağrı Başlatma (Entry Point)
- Giriş noktası: `src/main.py` içindeki `main()` fonksiyonu.
- Yapılandırma (`config.py`) ve log ayarları yüklenir.
- `Call` sınıfı örneklenir ve çağrı dinleme süreci başlatılır.

## 2. Konfigürasyon ve Sabitler
- `src/config.py`: SIP portları, RTP port aralığı, VAD hassasiyeti, AI hizmet URL'leri vb.
- `src/constants.py`: Kodek, protokol ve diğer sabit değerler.

## 3. Çağrı Yönetimi ve Durum Makinesi
- `src/call.py`:
  - `Call` sınıfı çağrı oturumunu ve durum geçişlerini (`IDLE`, `LISTENING`, `SPEAKING`, `BARGING_IN`) yönetir.
  - `Call.__init__()`: SDP işlemlerini yapar, RTP soketlerini bind eder, `RTPReceiver`/`RTPSender` ve AI engine (SpeechSessionManager) başlatır.
  - `Call.resume()`: Çağrıyı yeniden etkinleştirir (`sendrecv` yönü).
  - `Call.pause()`: Çağrıyı duraklatır (`recvonly` yönü).
  - `Call.close()`: Asenkron olarak çağrıyı kapatır ve tüm görevleri sonlandırır.
  - `Call.terminate()`: SIP seviyesinde çağrıyı sonlandırır.

## 4. RTP Akışları ve Kodek İşleme
- `src/rtp.py`: Async I/O ile RTP paketlerini alır ve gönderir.
- `src/codec.py` (ve `pcmu_decoder.py`, `opus.py`): G.711 ↔ PCM dönüşümlerini gerçekleştirir.

## 5. Voice Activity Detection (VAD) ve Barge-in
- `src/speech_processing/vad.py` modülu:
  - Gelen ses paketlerini WebRTC VAD'a gönderir.
  - Debounce mekanizması ile kısa çırpışmaları (false positive) filtreler.
  - Kullanıcı konuştuğunda `SPEAKING` durumu tetiklenir.
- **Barge-in Akışı:**
  1. VAD `SPEAKING` algıladığında, TTS akışı kesilir.
  2. TTS tamponu temizlenir ve TTS görevi iptal edilir.
  3. STT alımına geçiş yapılır, yapay zekadan gelen kendi sesi üzerindeki hatalı transkriptler atılır.

## 6. Vosk STT Entegrasyonu
- `src/speech_processing/vosk_stt_engine.py`:
  - WebSocket üzerinden Vosk sunucusuna ses akışı gönderir.
  - Ses formatı uyumsuzluğunda (`16 kHz` vs `8 kHz`) gerekiyorsa `src/utils.py` içinde yeniden örnekler.
  - `partial` (kısmi) ve final `text` transkriptleri alır.
  - VAD ile konuşma sonu tespiti birleştirilir.

## 7. Piper TTS Entegrasyonu
- `src/speech_processing/piper_tts_engine.py`:
  - Metni Piper sarmalayıcı servisine iletir.
  - Gelen ses paketlerini parça parça (streaming) alır ve anında RTP üzerinden gönderir.
  - Barge-in sinyali geldiğinde TTS akışını durdurur.

## 8. Engine Döngüsü ve Eşzamanlılık
- `src/engine.py`:
  - `asyncio` tabanlı ana döngüyü yönetir.
  - Görevler `asyncio.create_task()` veya `asyncio.gather()` ile paralel çalışır.
  - Bloklamayan I/O ve `await asyncio.sleep(0)` ile event loop tıkanmasını önler.
  - Çağrı sonlandığında görev iptalleri ve temizlik işlemlerini gerçekleştirir.

## 9. Test ve Geliştirme Araçları
- `src/run_local_stt_test.py`: Lokal STT akış testi ve `test_sine.wav`, `test.wav` gibi örnek ses dosyaları.
- `src/utils.py`: Resampling, paket işleme, yardımcı fonksiyonlar.

### Oturum Yönetimi ve Sınıflar
- `src/speech_processing/speech_session_manager.py`:
  - `SessionConfigurator`: Oturum konfigürasyon ayarlarını yükler ve codec seçimini yapar. (Lines 1–25)
  - `AudioOrchestrator`: PCM verisini işler, VAD ve barge-in mantığını yönetir. (Lines 80–128)
  - `TranscriptCoordinator`: STT WebSocket bağlantısını yönetir, kısmi ve final transkriptleri işler. (Lines 320–380)
  - `TTSCoordinator`: TTS isteklerini kuyruğa alır, mevcut sentezi iptal eder ve RTP üzerinden ses gönderimini koordine eder. (Lines 450–495)
  - `SpeechSessionManager`: Yukarıdaki bileşenleri bir araya getirerek tam bir çağrı oturumu akışını yönetir. (Lines 570–620)
- `src/speech_processing/transcript_handler.py`:
  - `TranscriptHandler`: STT hizmetinden gelen JSON mesajlarını analiz eder, kısmi ve final transkriptleri yakalar ve callback'leri tetikler. (Lines 1–50)
- `src/speech_processing/audio_processor.py`:
  - `AudioProcessor`: PCMU (G.711 μ-law) ham verisini çözerek temizler, normalize eder, yeniden örnekler ve tensor ile PCM byte formatına dönüştürür. (Lines 1–40)

## 10. OpenShift Dağıtımı
- `openshift/01-configmaps.yaml`: Ortam değişkenleri ve konfigürasyon yönetimi.
- `openshift/02-oavc-deployment.yaml`: OAVC ana servisi ve container ayarları.
- `openshift/04-vosk-deployment.yaml`: Vosk STT servisi.
- `openshift/05-services.yaml`: Hizmet tanımları ve ağ yönlendirmeleri.

## 11. Notlar ve İyileştirmeler
- Kod veya parametre değişikliklerinde mutlaka ilgili Türkçe dokümantasyonu (`docs/config.md`, `docs/VOSK.md`, `docs/Docker Instructions.md`) güncelleyin.
- Event loop performansını korumak için bloklamayan asenkron I/O kullanın.
- VAD debounce ve barge-in hassasiyet parametrelerini test senaryolarına göre ayarlayın.

---

*Bu doküman, Smart Speech entegrasyonunun tüm kritik adımlarını özetlemektedir. Geliştirici yorumları ve örnek akış diyagramları için kod içindeki ilgili fonksiyon bloklarına başvurabilirsiniz.* 