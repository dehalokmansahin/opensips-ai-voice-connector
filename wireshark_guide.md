# 🔍 Wireshark Debug Guide - SIP Call to 192.168.1.120:5060

## 📋 Call Scenario
- **SIP URI**: `sip:pipecat@192.168.1.120:5060;transport=udp`
- **Client IP**: `192.168.88.1` (your softphone)
- **Server IP**: `192.168.1.120` (host Wi-Fi IP)
- **SIP Port**: `5060` (OpenSIPS)
- **Expected RTP**: `192.168.1.120:35008` ↔ `192.168.88.1:4056`

## 🚀 Step 1: Start Wireshark

1. Run Wireshark as **Administrator**
2. Select capture interface: **"Wi-Fi"** (recommended for this scenario)

## 🔍 Step 2: Set Capture Filter

Use this exact filter in the "Capture Filter" field:
```
host 192.168.88.1 or host 192.168.1.120
```

Alternative filters:
```bash
# More specific (SIP + RTP ports)
(host 192.168.88.1 or host 192.168.1.120) and (port 5060 or port 8089 or portrange 35000-35020)

# Just RTP traffic
udp and portrange 35000-35020 and (host 192.168.88.1 or host 192.168.1.120)
```

## 📞 Step 3: Start Capture and Make Call

1. Click **"Start Capturing"** in Wireshark
2. Make SIP call to: `sip:pipecat@192.168.1.120:5060;transport=udp`
3. Let call run for 10-15 seconds
4. Stop capture

## 🔎 Step 4: Analysis with Display Filters

After capture, use these display filters:

### SIP Traffic Analysis
```bash
sip
```
Expected packets:
- `INVITE` from `192.168.88.1` to `192.168.1.120`
- `180 Ringing` from `192.168.1.120` to `192.168.88.1`
- `200 OK` from `192.168.1.120` to `192.168.88.1`
- `ACK` from `192.168.88.1` to `192.168.1.120`

### RTP Traffic Analysis
```bash
rtp
```
Expected packets:
- RTP from `192.168.88.1:4056` to `192.168.1.120:35008`
- RTP from `192.168.1.120:35008` to `192.168.88.1:4056`

### Combined Analysis
```bash
sip or rtp
```

## 📊 Step 5: Detailed Analysis

### 1. Check SIP Flow
- Right-click on any SIP packet → **"Follow" → "UDP Stream"**
- Look for SDP content in 200 OK response:
  ```
  m=audio 35008 RTP/AVP 0
  c=IN IP4 192.168.1.120
  ```

### 2. Check RTP Streams
- **Menu**: `Telephony` → `RTP` → `RTP Streams`
- Should see bidirectional RTP stream between:
  - `192.168.88.1:4056` → `192.168.1.120:35008`
  - `192.168.1.120:35008` → `192.168.88.1:4056`

### 3. VoIP Call Analysis
- **Menu**: `Telephony` → `VoIP Calls`
- Should show complete call with RTP streams

## ❌ Troubleshooting

### If NO RTP packets are visible:

1. **Check SDP in 200 OK response**:
   - Look for `c=IN IP4 192.168.1.120`
   - Look for `m=audio 35008 RTP/AVP 0`

2. **Check if packets reach host**:
   ```bash
   # Display filter:
   udp.port == 35008
   ```

3. **Check source routing**:
   ```bash
   # Display filter:
   ip.src == 192.168.88.1 and udp.dstport >= 35000 and udp.dstport <= 35020
   ```

### If SIP works but RTP doesn't:

- **Issue**: Client can't reach `192.168.1.120:35008`
- **Cause**: Network routing, firewall, or Docker port mapping
- **Solution**: Check Docker port exposure and Windows Firewall

## 🎯 Expected Results

### ✅ Success Indicators:
- SIP INVITE/200 OK/ACK sequence complete
- SDP shows correct IP (`192.168.1.120`) and port (`35008`)
- Bidirectional RTP packets visible
- RTP payload type 0 (PCMU)
- RTP packets at ~20ms intervals

### ❌ Failure Indicators:
- SIP works but no RTP packets
- RTP packets only in one direction
- "Destination unreachable" ICMP messages
- TCP RST packets on UDP ports (weird but possible)

## 🔧 Quick Commands for Terminal

```bash
# Check port mappings
docker port opensips-ai-voice-connector

# Check if ports are listening
netstat -an | findstr :35008

# Test RTP connectivity
python test_rtp_client.py --local-ip 192.168.88.1 --local-port 4056 --remote-ip 192.168.1.120 --remote-port 35008 --duration 30
``` 