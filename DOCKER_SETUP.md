# 🚀 OpenSIPS AI Voice Connector - Dynamic Docker Setup

## 📋 Özet

Bu yeni kurulum **tamamen dinamik ve konfigüratif**! Artık IP değişikliklerinde zaman kaybetmiyorsunuz:

- ✅ **Docker Service Discovery**: Container'lar hostname ile birbirini buluyor
- ✅ **Environment Variables**: Tüm konfigürasyon environment variable'lar ile  
- ✅ **Template System**: OpenSIPS config dosyası otomatik oluşturuluyor
- ✅ **Multi-Profile Support**: Development, Production, Debug profilleri
- ✅ **Health Checks**: Servislerin durumu otomatik kontrol ediliyor

## 🔧 Hızlı Başlangıç

### 1. Environment Dosyasını Oluşturun
```bash
# Template'i kopyalayın
cp docker.env.example .env

# Değerleri ihtiyacınıza göre düzenleyin
nano .env
```

### 2. Servisleri Başlatın
```bash
# Temel servisler (Development)
docker-compose up -d

# Production profili ile
docker-compose --profile production up -d

# Debug profili ile (Event monitoring dahil)
docker-compose --profile debug up -d
```

### 3. Durumu Kontrol Edin
```bash
# Container durumları
docker-compose ps

# Logları izleyin
docker-compose logs -f opensips-ai-voice-connector
docker-compose logs -f opensips

# Health check durumları
docker-compose exec opensips-ai-voice-connector curl -f http://localhost:8089 || echo "OAVC not ready"
```

## 🌍 Environment Variables

### Temel Konfigürasyon
```bash
# Network Configuration
DOCKER_SUBNET=172.20.0.0/16

# Port Configuration  
OPENSIPS_SIP_PORT=5060
OPENSIPS_MI_PORT=8087
OPENSIPS_EVENT_PORT=8090
OAVC_SIP_PORT=8089

# AI Services
VOSK_PORT=2700
PIPER_PORT=8000 
LLM_PORT=8765
```

### AI Model Configuration
```bash
# LLM Settings
LLM_MODEL=llama3.2:3b-instruct-turkish
LLM_MAX_TOKENS=80
LLM_TEMPERATURE=0.2

# TTS Settings
PIPER_VOICE_MODEL=tr_TR-dfki-medium
PIPER_SAMPLE_RATE=22050

# STT Settings
VOSK_SAMPLE_RATE=16000
```

### Runtime Configuration
```bash
# Development Mode
TEST_MODE=false
DEBUG_MODE=false
LOG_LEVEL=INFO

# Production Mode  
TEST_MODE=false
DEBUG_MODE=false
LOG_LEVEL=WARN
```

## 🔌 Port Mapping

| **Service** | **Internal Port** | **External Port** | **Protocol** | **Açıklama** |
|-------------|-------------------|-------------------|--------------|--------------|
| **OpenSIPS SIP** | 5060 | 5060 | UDP/TCP | Ana SIP interface |
| **OpenSIPS Secondary** | 8080 | 8080 | UDP | İkincil SIP interface |
| **OpenSIPS MI** | 8087 | 8087 | UDP | Management Interface |
| **OpenSIPS Events** | 8090 | 8090 | UDP | Event notifications |
| **OAVC SIP** | 8089 | 8089 | UDP/TCP | OAVC call interface |
| **Vosk STT** | 2700 | 2700 | TCP | Speech-to-text |
| **Piper TTS** | 8000 | 8000 | TCP | Text-to-speech |
| **LLM** | 8765 | 8765 | TCP | Language model |
| **RTP Media** | 35000-35003 | 35000-35003 | UDP | Media streams |

## 🎯 Docker Profiles

### Development (Varsayılan)
```bash
docker-compose up -d
```
**İçerik:** OAVC + OpenSIPS + AI Services

### Production
```bash
docker-compose --profile production up -d
```
**İçerik:** Development + PostgreSQL + Redis

### Debug/Monitoring
```bash
docker-compose --profile debug up -d
```
**İçerik:** Development + Event Monitor

### Full Stack
```bash
docker-compose --profile production --profile debug up -d
```
**İçerik:** Tüm servisler

## 🔍 Debugging ve Monitoring

### Container Logları
```bash
# Tüm servisler
docker-compose logs -f

# Specific service
docker-compose logs -f opensips-ai-voice-connector
docker-compose logs -f opensips
docker-compose logs -f vosk-server
```

### Health Checks
```bash
# OAVC Health
curl -f http://localhost:8089 || echo "OAVC down"

# OpenSIPS MI Test
echo "uptime" | nc -u localhost 8087

# AI Services
curl -f http://localhost:2700/health || echo "Vosk down"
curl -f http://localhost:8000/health || echo "Piper down"
curl -f http://localhost:8765/health || echo "LLM down"
```

### Event Monitoring
```bash
# OpenSIPS events dinle
docker-compose exec opensips-event-monitor tail -f /var/log/event-monitor/events.log

# Manual event listening
nc -u -l 8090
```

## 📊 Service Discovery

Container'lar artık hostname ile birbirini buluyor:

```bash
# OAVC içinden OpenSIPS'e erişim
OPENSIPS_HOST=opensips
OPENSIPS_MI_PORT=8087

# OpenSIPS içinden OAVC'ye erişim
OAVC_HOST=opensips-ai-voice-connector
OAVC_SIP_PORT=8089

# AI Service URL'leri
VOSK_SERVER_URL=ws://vosk-server:2700
PIPER_TTS_URL=ws://piper-tts-server:8000/tts
LLAMA_SERVER_URL=ws://llm-turkish-server:8765
```

## 🔧 Troubleshooting

### Container Başlamıyor
```bash
# Build rebuild
docker-compose build --no-cache

# Volume temizle
docker-compose down -v
docker system prune -f
```

### Connectivity Sorunları
```bash
# Network kontrol
docker network inspect opensips_network

# DNS resolution test
docker-compose exec opensips-ai-voice-connector nslookup opensips
docker-compose exec opensips nslookup opensips-ai-voice-connector
```

### Port Conflicts
```bash
# Port değiştir (.env dosyasında)
OPENSIPS_SIP_PORT=5061
OAVC_SIP_PORT=8090

# Restart
docker-compose down
docker-compose up -d
```

### Configuration Issues
```bash
# Template debug
docker-compose exec opensips cat /etc/opensips/opensips.cfg

# Environment variables check
docker-compose exec opensips-ai-voice-connector env | grep -E "(OPENSIPS|OAVC|VOSK|PIPER|LLM)"
```

## 🎉 Production Deployment

### Güvenlik
```bash
# Güvenli şifreler ayarlayın (.env)
POSTGRES_PASSWORD=super_secure_password_2024
REDIS_PASSWORD=another_secure_password_2024

# Container permissions
docker-compose exec opensips-ai-voice-connector chown -R app:app /app/logs
```

### Scaling
```bash
# Sadece AI worker'ları scale et
docker-compose up -d --scale opensips-ai-voice-connector=3

# Load balancer ekle (nginx)
# (Ayrı bir docker-compose.nginx.yml dosyası oluşturulabilir)
```

### Monitoring
```bash
# Production monitoring
docker-compose --profile production --profile monitoring up -d

# Log aggregation
# (ELK Stack veya Grafana + Prometheus eklentisi yapılabilir)
```

## 🆘 Support

### Log Dosyaları
- **OAVC**: `/app/logs/` (container içi) - `./logs/` (host)
- **OpenSIPS**: `/var/log/opensips/` (container içi) - `./logs/opensips/` (host)
- **Event Monitor**: `/var/log/event-monitor/` (container içi) - `./logs/event-monitor/` (host)

### Configuration Validation
```bash
# OpenSIPS config syntax check
docker-compose exec opensips opensips -c -f /etc/opensips/opensips.cfg

# OAVC config test
docker-compose exec opensips-ai-voice-connector python -c "from src.config import Config; c=Config(); print('Config OK')"
```

---

## 🚀 **Artık IP değişikliği endişeniz yok!** 

Tüm sistem Docker Service Discovery ile dinamik olarak çalışıyor. Sadece `.env` dosyasında portları değiştirmeniz yeterli! 🎯 