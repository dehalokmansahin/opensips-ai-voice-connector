# 📞 OpenSIPS AI Voice Connector - SIP Çağrısı Rehberi

## 🎯 SIP Çağrısı Akışı

### 1. **Gelen Çağrı (INVITE)**
```
SIP Client → OpenSIPS:5060 → OAVC:8088 → Pipecat Pipeline
```

### 2. **Ses İşleme Pipeline**
```
Audio Input → VAD → STT (Vosk) → LLM (Llama3.2) → TTS (Piper) → Audio Output
```

### 3. **RTP Ses Akışı**
```
Client ↔ OpenSIPS ↔ OAVC ↔ AI Services
```

## 🔧 Konfigürasyon

### OpenSIPS Konfigürasyonu (`cfg/opensips.cfg`)
- ✅ OPTIONS method desteği eklendi
- ✅ INVITE handling için OAVC forwarding 
- ✅ Dialog management
- ✅ Record routing

### OAVC Konfigürasyonu (`cfg/opensips-ai-voice-connector.ini`)
- ✅ STT: Vosk (ws://vosk-server:2700)
- ✅ LLM: Llama3.2 Turkish (ws://llm-turkish-server:8765)  
- ✅ TTS: Piper Turkish (ws://piper-tts-server:8000/tts)
- ✅ Pipeline: VAD → STT → LLM → TTS

## 📱 Test Yöntemleri

### 1. **SIP Client ile Test**
```ini
# MicroSIP / X-Lite Ayarları
Server: YOUR_SERVER_IP:5060
Username: test
Domain: YOUR_SERVER_IP  
Protocol: UDP
```

### 2. **Test Çağrısı**
```
Çağrı: sip:12345@YOUR_SERVER_IP:5060
```

### 3. **Asterisk/FreeSWITCH'ten Test**
```
Dial(SIP/12345@YOUR_SERVER_IP:5060)
```

## 🎵 Ses Formatları

### Giriş (PSTN → OpenSIPS)
- **Format**: PCMU/8000 (G.711 μ-law)
- **Sample Rate**: 8 kHz
- **Bit Depth**: 8-bit
- **Channels**: Mono

### İşleme (OpenSIPS → OAVC → Pipeline)  
- **Format**: PCM 16-bit
- **Sample Rate**: 16 kHz (STT) / 22 kHz (TTS)
- **Channels**: Mono
- **Frame Size**: 160 bytes (20ms)

### Çıkış (Pipeline → PSTN)
- **Format**: PCMU/8000 (G.711 μ-law) 
- **Sample Rate**: 8 kHz
- **Bit Depth**: 8-bit
- **Channels**: Mono

## ⚡ Performans Hedefleri

- **VAD → STT**: ≤ 500ms
- **STT → LLM**: ≤ 400ms
- **LLM → TTS**: ≤ 700ms
- **Total Round-Trip**: ≤ 1.5 saniye

## 🔍 Debug

### OpenSIPS Logları
```bash
docker logs opensips -f
```

### OAVC Logları
```bash
docker logs opensips-ai-voice-connector -f
```

### SIP Message Trace
```bash
# tcpdump ile SIP mesajlarını yakalama
tcpdump -i any -n port 5060
```

## 🚀 Production Deployment

### 1. **Linux Sunucuda Deploy**
```bash
git clone https://github.com/your-repo/opensips-ai-voice-connector
cd opensips-ai-voice-connector
docker-compose up -d
```

### 2. **Firewall Ayarları**
```bash
# SIP signaling
ufw allow 5060/udp
ufw allow 5060/tcp

# RTP media (OAVC)
ufw allow 35000:35100/udp

# Management interfaces
ufw allow 8088:8089/tcp
```

### 3. **Health Check**
```bash
# Container durumları
docker-compose ps

# SIP connectivity test
sip-test-tool --target YOUR_SERVER_IP:5060
```

## 🎤 AI Asistan Test Senaryoları

### 1. **Basit Karşılama**
```
Kullanıcı: "Merhaba"
AI: "Merhaba! Size nasıl yardımcı olabilirim?"
```

### 2. **Bilgi Sorgusu**
```
Kullanıcı: "Bugün hava nasıl?"
AI: "Üzgünüm, hava durumu bilgisine erişimim yok. Başka konularda yardımcı olabilirim."
```

### 3. **Barge-in Test**
```
AI konuşurken kullanıcı araya girse → Pipeline kesinti (interruption) yapmalı
```

## 📊 Monitoring

### Key Metrics
- Call success rate
- Audio quality (MOS score)
- Response latency
- Pipeline processing time
- Error rates per component

### Alerting
- High latency (>2 seconds)
- Failed calls (>5% error rate)  
- Container health issues
- Resource exhaustion

---

## 🎯 **Özet: SIP çağrısı akışı hazır, Windows Docker UDP sorunu production'da olmayacak!** 