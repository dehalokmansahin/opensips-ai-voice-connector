# Port Mapping Guide

This document provides a comprehensive overview of all ports used in the OpenSIPS AI Voice Connector system.

## Port Overview Table

| Service | Port | Protocol | Purpose | Environment Variable | Default | Notes |
|---------|------|----------|---------|---------------------|---------|-------|
| **OpenSIPS** |
| OpenSIPS | 5060 | UDP | SIP Signaling | `OS_SIP_PORT` | 5060 | Main SIP port for call setup |
| OpenSIPS MI | 8088 | UDP | Management Interface | `MI_PORT` | 8088 | Used by OAVC to send MI commands |
| OpenSIPS Events | 8089 | UDP | Event Notifications | `EVENT_PORT` | 8089 | E_UA_SESSION events to OAVC |
| **OAVC (AI Voice Connector)** |
| RTP Media | 35000-35100 | UDP | Media Streams | `RTP_MIN_PORT`, `RTP_MAX_PORT` | 35000-35100 | Dynamic allocation per call |
| **AI Services** |
| AI Service | 2700 | TCP/WS | WebSocket API | `AI_SERVICE_PORT` | 2700 | Main AI processing |
| TTS Service | 8000 | TCP/HTTP | Text-to-Speech | `TTS_SERVICE_PORT` | 8000 | Speech synthesis |
| STT Service | 2701 | TCP/WS | Speech-to-Text | `STT_SERVICE_PORT` | 2701 | Speech recognition |

## Port Flow Diagram

```
┌─────────────┐    5060/UDP     ┌─────────────┐
│   SIP UA    │ ──────────────► │  OpenSIPS   │
│  (Phone)    │                 │             │
└─────────────┘                 └─────────────┘
                                       │
                                       │ 8088/UDP (MI)
                                       │ 8089/UDP (Events)
                                       ▼
┌─────────────┐  35000-35100/UDP ┌─────────────┐
│   SIP UA    │ ◄────────────────┤    OAVC     │
│  (Phone)    │    RTP Media     │             │
└─────────────┘                 └─────────────┘
                                       │
                                       │ 2700/WS (AI)
                                       │ 8000/HTTP (TTS)
                                       │ 2701/WS (STT)
                                       ▼
                                ┌─────────────┐
                                │ AI Services │
                                │             │
                                └─────────────┘
```

## Port Configuration

### Environment Variables

All ports can be configured using environment variables:

```bash
# OpenSIPS Ports
export OS_SIP_PORT=5060
export MI_PORT=8088
export EVENT_PORT=8089

# RTP Media Ports
export RTP_MIN_PORT=35000
export RTP_MAX_PORT=35100

# AI Service Ports
export AI_SERVICE_PORT=2700
export TTS_SERVICE_PORT=8000
export STT_SERVICE_PORT=2701
```

### Docker Compose Configuration

In `docker-compose.override.yml`:

```yaml
services:
  opensips:
    ports:
      - "${OS_SIP_PORT:-5060}:5060/udp"
      - "${MI_PORT:-8088}:8088/udp"
      - "${EVENT_PORT:-8089}:8089/udp"
      
  opensips-ai-voice-connector:
    ports:
      - "${RTP_MIN_PORT:-35000}-${RTP_MAX_PORT:-35100}:35000-35100/udp"
```

## Firewall Configuration

### iptables Rules

```bash
# Allow SIP signaling
iptables -A INPUT -p udp --dport 5060 -j ACCEPT

# Allow OpenSIPS MI and Events (internal only)
iptables -A INPUT -p udp --dport 8088 -s 172.20.0.0/16 -j ACCEPT
iptables -A INPUT -p udp --dport 8089 -s 172.20.0.0/16 -j ACCEPT

# Allow RTP media range
iptables -A INPUT -p udp --dport 35000:35100 -j ACCEPT

# Allow AI services (internal only)
iptables -A INPUT -p tcp --dport 2700 -s 172.20.0.0/16 -j ACCEPT
iptables -A INPUT -p tcp --dport 8000 -s 172.20.0.0/16 -j ACCEPT
iptables -A INPUT -p tcp --dport 2701 -s 172.20.0.0/16 -j ACCEPT
```

### UFW Rules

```bash
# Allow SIP signaling
ufw allow 5060/udp

# Allow RTP media range
ufw allow 35000:35100/udp

# Internal services (Docker network)
ufw allow from 172.20.0.0/16 to any port 8088 proto udp
ufw allow from 172.20.0.0/16 to any port 8089 proto udp
ufw allow from 172.20.0.0/16 to any port 2700 proto tcp
ufw allow from 172.20.0.0/16 to any port 8000 proto tcp
ufw allow from 172.20.0.0/16 to any port 2701 proto tcp
```

## Port Security Considerations

### Public vs Internal Ports

| Port | Exposure | Security Level | Notes |
|------|----------|----------------|-------|
| 5060 | Public | Medium | SIP signaling - use fail2ban |
| 35000-35100 | Public | Low | RTP media - encrypted if needed |
| 8088, 8089 | Internal | High | Management interfaces |
| 2700, 8000, 2701 | Internal | High | AI services |

### Security Recommendations

1. **SIP Port (5060)**:
   - Use fail2ban to prevent brute force attacks
   - Consider changing to non-standard port
   - Implement SIP authentication

2. **RTP Ports (35000-35100)**:
   - Consider SRTP for encrypted media
   - Monitor for unusual traffic patterns
   - Limit concurrent calls to prevent port exhaustion

3. **Internal Ports (8088, 8089, 2700, 8000, 2701)**:
   - Never expose to public internet
   - Use Docker network isolation
   - Implement service-to-service authentication

## Troubleshooting Port Issues

### Common Problems

1. **Port Already in Use**:
   ```bash
   # Check what's using a port
   netstat -tulpn | grep :5060
   lsof -i :5060
   ```

2. **Docker Port Conflicts**:
   ```bash
   # Check Docker port mappings
   docker ps --format "table {{.Names}}\t{{.Ports}}"
   ```

3. **RTP Port Exhaustion**:
   ```bash
   # Monitor RTP port usage
   netstat -un | grep :350 | wc -l
   ```

### Diagnostic Commands

```bash
# Test SIP port connectivity
nc -u -v opensips-server 5060

# Test MI interface
echo "ps" | nc -u opensips-server 8088

# Test RTP port range
nmap -sU -p 35000-35010 oavc-server

# Check Docker network connectivity
docker exec opensips ping opensips-ai-voice-connector
```

## Performance Considerations

### Port Allocation Strategy

1. **RTP Port Pool**:
   - Reserve 100 ports for concurrent calls
   - Monitor usage with metrics
   - Implement port recycling

2. **Connection Limits**:
   - Set appropriate ulimits
   - Monitor file descriptor usage
   - Implement connection pooling

### Monitoring

```bash
# Monitor port usage
watch 'netstat -tulpn | grep -E "(5060|8088|8089|350)"'

# Check connection counts
ss -s | grep -E "(UDP|TCP)"

# Monitor Docker network traffic
docker exec opensips iftop -i eth0
``` 