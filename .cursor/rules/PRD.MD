
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
-   **Çıkış (Pipecat'ten):** TTS servisinden üretilen ses `PCM 22050kHz, mono` formatındadır. Bu ses, PSTN (Public Switched Telephone Network) hatlarına gönderilmeden önce `PCMU/8000 ulaw` formatına **encode** edilmelidir.

**Format Dönüşüm Akışı:**
> **PCMU/8000 (giriş)** → **PCM 16kHz decode** → **Pipeline İşleme** → **PCM 22050kHz (TTS)** → **PCMU/8000 encode (çıkış)**

---



## 5. OAVC PCMU Veri İşleme

OAVC'den gelen her 20ms'lik RTP paketi, PCMU/8000 ulaw formatında Pipecat pipeline'ına gönderilir.

-   **Örnekleme Hesabı:** `0.020 saniye * 8000 örnek/saniye = 160 örnek`
-   **Byte Boyutu:** `160 örnek * 1 byte/örnek (8-bit ulaw) = 160 byte`



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

