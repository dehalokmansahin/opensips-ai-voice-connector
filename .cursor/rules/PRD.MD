
# 🚀 PRD – Pipecat IVR Sanal Asistan (Geliştirici Dostu)

---

## 1. Amaç

Bu doküman, bir banka çağrı merkezi için geliştirilecek olan **Pipecat tabanlı gerçek zamanlı sanal asistan** projesinin teknik gereksinimlerini ve ürün tanımını içerir.

-   **Proje Hedefi:** Banka çağrı merkezi IVR (Interactive Voice Response) sistemini, modern ve akıcı bir diyalog deneyimi sunan bir sanal asistan ile güçlendirmek.
-   **Teknoloji Odağı:** Proje, ses taşıma katmanı olarak OAVC (Open-Source Audio/Video Conferencing) platformunu kullanacak ve iş mantığı **Pipecat pipeline**'ı üzerinde inşa edilecektir.
-   **Pipeline Bileşenleri:**
    -   **VAD (Voice Activity Detection):** Kullanıcının ne zaman konuşup ne zaman sustuğunu tespit ederek konuşma segmentleri oluşturma.
    -   **Interruption (Barge-in):** Sanal asistan konuşurken kullanıcının araya girmesine (barge-in) olanak tanıma.
    -   **Çekirdek Akış:** Gerçek zamanlı STT (Speech-to-Text) → LLM (Large Language Model) → TTS (Text-to-Speech) akışını yönetme.
-   **Örnek Senaryo:** Projenin yeteneklerini sergilemek amacıyla **"Kart Kurye Durumu Sorgulama"** akışı pilot olarak geliştirilecektir.

---

## 2. Akış (High Level)

Sistemin uçtan uca veri akışı aşağıdaki gibi olacaktır:

> **OAVC (PCMU/8000 Girişi)** → **PCMU→PCM Decode** → **Pipecat Pipeline** → VAD → STT → LLM → TTS → **PCM→PCMU Encode** → **OAVC (PCMU/8000 Çıkışı)**

---

## 3. Ses Formatı

-   **Giriş (OAVC'den):** `PCMU/8000 ulaw` formatı (8-bit, 8kHz, mono).
-   **Paketleme:** OAVC, RTP paketleri aracılığıyla sesi yaklaşık **20ms'lik parçalar (chunk)** halinde iletir. Bu, `8000 (örnek/sn) * 0.020 (sn) * 1 (byte/örnek) = 160 byte/frame` boyutuna karşılık gelir.
-   **Pipeline İçi İşleme:** Gelen PCMU ses verisi pipeline içinde `PCM 16-bit, 16kHz, mono` formatına decode edilir.
-   **Çıkış (Pipecat'ten):** TTS servisinden üretilen ses `PCM 24kHz, mono` formatındadır. Bu ses, PSTN (Public Switched Telephone Network) hatlarına gönderilmeden önce `PCMU/8000 ulaw` formatına **encode** edilmelidir.

**Format Dönüşüm Akışı:**
> **PCMU/8000 (giriş)** → **PCM 16kHz decode** → **Pipeline İşleme** → **PCM 24kHz (TTS)** → **PCMU/8000 encode (çıkış)**

---

## 4. OAVC → Pipecat Bağlantısı

OAVC'den Pipecat'e ses akışı, Pipecat SDK'sının **`ai.send`** methodu ile gerçekleştirilir. OAVC'den alınan her bir PCM ses parçası (chunk), bu method aracılığıyla Pipecat pipeline'ına gönderilir.

Bu method, OAVC tarafından çağrıldığında, arka planda `PipelineManager` sınıfındaki `process_audio_packet` fonksiyonuna eşlenir.


---


## 5. OAVC PCMU Veri İşleme

OAVC'den gelen her 20ms'lik RTP paketi, PCMU/8000 ulaw formatında Pipecat pipeline'ına gönderilir.

-   **Örnekleme Hesabı:** `0.020 saniye * 8000 örnek/saniye = 160 örnek`
-   **Byte Boyutu:** `160 örnek * 1 byte/örnek (8-bit ulaw) = 160 byte`

Bu 160 byte'lık PCMU chunk, `process_audio_packet` fonksiyonuna argüman olarak verilir:


---
## 7. VAD Parametreleri

Türkçe konuşma için önerilen başlangıç VAD (Silero) parametreleri:

| Parametre | Değer | Açıklama |
| :--- | :---: | :--- |
| `min_speech_duration_ms` | 200 | Bir sesin konuşma olarak kabul edilmesi için gereken minimum süre. |
| `min_silence_duration_ms`| 100 | Konuşmanın bittiğini varsaymak için gereken minimum sessizlik süresi. |
| `speech_prob_threshold` | 0.5 | Sesin konuşma olma olasılığı eşiği. |

---

## 8. Interruption (Barge-in)

Kullanıcının, asistan konuşurken araya girmesini sağlamak için `MinWordsInterruptionStrategy` kullanılır. Bu strateji, kullanıcı belirli bir sayıda kelime söylediğinde TTS ses çıkışını anında keser.


## 9. LLM Kullanımı

Pipecat, LLM servisleriyle entegrasyonu basitleştirir. `OLLamaLLMService` kullanılarak yerel bir LLM'e (örneğin Llama 3.2) istek gönderilir.
---

## 10. TTS Akışı

Doğal ve akıcı Türkçe ses çıkışı için Piper TTS servisi kullanılır. Pipecat, bu servise metin gönderir ve karşılığında ses verisini stream olarak alır.


## 11. Kart Kurye Durumu Senaryosu

**Kullanıcı:** *"Merhaba, kredi kartımın durumunu öğrenebilir miyim?"* veya *"Kartım nerede?"*

**Pipeline Akışı:**

1.  **PCM Girişi:** Kullanıcının sesi OAVC üzerinden Pipecat'e 640 byte'lık paketler halinde akar.
2.  **VAD:** Konuşmanın başladığını ve bittiğini algılar, tam bir ifade segmenti oluşturur.
3.  **STT:** Ses segmentini metne çevirir: `"kartım nerede"`
4.  **LLM:** Metni işler, amacı (`intent`) anlar ve uygun cevabı oluşturur.
    -   *Intent:* `kart_kurye_sorgulama`
    -   *LLM Cevabı (Örnek):* `"Tabii, hemen kontrol ediyorum. Kartınız kuryeye verilmiş olup, tahmini teslimat süresi 3 iş günüdür."`
5.  **TTS:** LLM'in ürettiği metni sese dönüştürür.
6.  **PCM Çıkışı:** Üretilen ses PCM akışı olarak OAVC'ye geri gönderilir ve kullanıcıya dinletilir.

---

## 12. Test Senaryoları

-   [ ] OAVC'den Pipecat'e PCM aktarımı başarılı bir şekilde gerçekleşiyor mu?
-   [ ] VAD, kısa ve uzun konuşmaları doğru şekilde segmentlere ayırıyor mu?
-   [ ] Asistan konuşurken kullanıcı araya girdiğinde "barge-in" anında tetikleniyor mu?
-   [ ] Türkçe STT, farklı aksan ve hızlardaki konuşmaları doğru deşifre ediyor mu?
-   [ ] LLM, "kart kurye" ile ilgili farklı ifadelerden doğru amacı (`intent`) yakalayabiliyor mu?
-   [ ] TTS tarafından üretilen PCM ses çıkışı temiz, anlaşılır ve kesintisiz mi?
-   [ ] Pipeline, `start()` ve `stop()` çağrıları arasında istikrarlı çalışıyor ve kaynak sızıntısı olmadan kapanıyor mu?

---

## 13. Performans Gereklilikleri

Kullanıcı deneyiminin akıcı olması için hedeflenen gecikme süreleri:

| Adım | Hedef Süre (ms) | Açıklama |
| :--- | :---: | :--- |
| VAD → STT | ≤ 500 | Kullanıcı sustuktan sonra metnin üretilme süresi. |
| STT → LLM | ≤ 400 | Metnin LLM'e gidip ilk cevabın gelme süresi (TTFB).|
| LLM → TTS | ≤ 700 | LLM cevabının ilk ses paketine dönüşme süresi. |
| **Toplam Round-Trip** | **≤ 1.5 saniye** | Kullanıcı sustuktan sonra asistanın konuşmaya başlama süresi. |

