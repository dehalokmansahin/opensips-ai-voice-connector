# Vosk Konuşma Tanıma (STT) Entegrasyonu

OpenSIPS AI Voice Connector (OAVC) projesine Vosk Konuşma Tanıma (Speech-to-Text, STT) entegrasyonu, telefon görüşmelerinde kullanıcı konuşmalarını gerçek zamanlı olarak metne dönüştürmenizi sağlar.

## Özellikler

- WebSocket üzerinden Vosk STT sunucusuna bağlantı
- Gerçek zamanlı konuşma tanıma
- Kısmi ve nihai transkripsiyon sonuçları
- WebRTC tabanlı Ses Aktivite Tespiti (VAD) desteği
- Barge-in (konuşma sırasında araya girme) desteği
- Otomatik yeniden bağlanma ve hata işleme

## Kurulum

### Docker ile Kurulum

Vosk STT sunucusunu Docker ile çalıştırmak için:

```bash
docker-compose up -d
```

Bu komut, OAVC servisini ve Vosk STT sunucusunu başlatacaktır.

### Manuel Kurulum

1. Vosk sunucusunu kurun:
   ```bash
   git clone https://github.com/alphacep/vosk-server
   cd vosk-server/websocket
   pip install -r requirements.txt
   ```

2. Bir Vosk modeli indirin (https://alphacephei.com/vosk/models):
   ```bash
   wget https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
   unzip vosk-model-small-en-us-0.15.zip
   ```

3. Sunucuyu çalıştırın:
   ```bash
   python3 asr_server.py /path/to/vosk-model-small-en-us-0.15
   ```

4. WebRTC VAD kütüphanesini yükleyin:
   ```bash
   pip install webrtcvad
   ```

## Yapılandırma

`cfg/vosk.cfg` dosyasında aşağıdaki ayarları yapılandırabilirsiniz:

- `ws_url`: Vosk WebSocket sunucu adresi
- `sample_rate`: Ses örnek hızı (genellikle telefon için 8 kHz)

### VAD Ayarları
- `use_vad`: Ses Aktivite Tespiti'ni etkinleştir/devre dışı bırak
- `vad_aggressiveness`: WebRTC VAD saldırganlık seviyesi (0-3, daha yüksek değerler daha az hassasiyet)
- `silence_frames_threshold`: Konuşmanın bittiğini belirlemek için ardışık sessiz çerçeve sayısı
- `speech_frames_threshold`: Konuşmanın başladığını belirlemek için ardışık konuşma çerçevesi sayısı

### Barge-in Ayarları
- `enable_barge_in`: Barge-in özelliğini etkinleştir/devre dışı bırak
- `barge_in_threshold`: Barge-in'i tetiklemek için gereken ardışık konuşma çerçevesi sayısı

Veya Docker Compose ile çalıştırıyorsanız, `docker-compose.yml` dosyasında çevre değişkenlerini ayarlayabilirsiniz.

## WebRTC VAD Hakkında

Bu entegrasyonda, Google'ın WebRTC projesinden alınan VAD (Ses Aktivite Tespiti) algoritması kullanılmaktadır. Bu algoritma, ses çerçevelerini analiz ederek konuşma/konuşma olmayan bölümleri ayırt eder. Enerji tabanlı basit VAD yöntemlerine göre daha doğru sonuçlar sağlar.

WebRTC VAD özellikleri:
- Farklı saldırganlık seviyeleri (0-3)
- 10ms, 20ms veya 30ms ses çerçeveleri ile çalışabilir
- Düşük CPU kullanımı
- Telefon kalitesi seslere (8kHz) optimize edilmiş

## Barge-in Özelliği

Barge-in özelliği, kullanıcının TTS (Text-to-Speech) çıkışı sırasında konuşmaya başlayabilmesini ve sistemin bunu algılayarak TTS çıkışını durdurmasını sağlar. Bu, daha doğal bir konuşma akışı sağlar.

Barge-in nasıl çalışır:
1. Sistem TTS çıkışı gönderirken, `is_tts_playing` bayrağı TRUE olarak ayarlanır
2. WebRTC VAD, kullanıcı konuşmasını tespit ettiğinde ve yeterli sayıda konuşma çerçevesi algılandığında (`barge_in_threshold`), bir barge-in olayı tetiklenir
3. TTS çıkışı durdurulur ve sistem kullanıcı konuşmasını işlemeye başlar

## Kullanım

OAVC'ye "vosk" ile başlayan bir SIP URI ile arama yaparak Vosk STT motorunu kullanabilirsiniz. Örneğin:

```
sip:vosk@your-sip-server
```

## Sorun Giderme

1. WebSocket bağlantı hataları:
   - Vosk sunucusunun çalıştığını ve erişilebilir olduğunu kontrol edin
   - Güvenlik duvarı ayarlarını kontrol edin
   
2. Kötü transkripsiyon kalitesi:
   - Daha büyük/daha doğru bir Vosk modeli kullanın
   - Ses örnek hızının model ile eşleştiğinden emin olun
   
3. VAD sorunları:
   - WebRTC VAD hassasiyet seviyesini ayarlayın (`vad_aggressiveness`)
   - Sessizlik ve konuşma eşik değerlerini ortamınıza göre ayarlayın
   
4. Barge-in çalışmıyor:
   - `enable_barge_in` ayarının TRUE olduğunu kontrol edin
   - `barge_in_threshold` değerini azaltmayı deneyin (daha hızlı tepki için)
   - TTS sırasında VAD'ın kullanıcı konuşmasını algılayıp algılamadığını kontrol edin 