# Docker Instructions for OpenSIPS AI Voice Connector

This document describes how to deploy the OpenSIPS AI Voice Connector (OAVC) with Vosk Speech-to-Text (STT) and Piper Text-to-Speech (TTS) integration using Docker.

## Prerequisites

- Docker and Docker Compose installed
- At least 2GB of RAM for the basic setup
- Network ports 5060/UDP (SIP), 35000-65000/UDP (RTP), 2700/TCP (Vosk WebSocket), and 5002/TCP (Piper WebSocket) open

## Services Architecture

The Docker Compose setup includes the following services:

1. **OAVC (OpenSIPS AI Voice Connector)**: The main application that handles SIP calls and processes audio
2. **Vosk STT Server**: Provides speech-to-text capabilities via WebSocket
3. **Piper TTS Server**: Provides text-to-speech capabilities via WebSocket

## Configuration Files

Before starting the services, ensure you have the following configuration files in the `cfg/` directory:

- `config.ini`: Main configuration file for OAVC
- `vosk.cfg`: Configuration for the Vosk STT integration
- `piper.cfg`: Configuration for the Piper TTS integration

Example `config.ini`:
```ini
[opensips]
ip = 127.0.0.1
port = 8080

[engine]
event_ip = 127.0.0.1

[vosk]
url = ws://vosk:2700
sample_rate = 16000
vad_threshold = 0.12
speech_detection_threshold = 3
silence_detection_threshold = 10

[piper]
url = ws://piper:5002
voice = en_US-lessac-medium
sample_rate = 22050
```

## Environment Variables

The following environment variables can be configured in the `docker-compose.yml` file:

### OAVC Service
- `CONFIG_FILE`: Path to the configuration file inside the container

### Vosk Service
- `VOSK_MODEL_PATH`: Path to the Vosk model directory
- `VOSK_SAMPLE_RATE`: Sample rate for the Vosk model (typically 16000)

### Piper Service
- `PIPER_MODEL`: Voice model to use (e.g., "en_US-lessac-medium")
- `PIPER_SAMPLE_RATE`: Sample rate for audio output (typically 22050 Hz)
- `WS_PORT`: WebSocket port for the Piper service (default: 5002)

## Docker Compose Configuration

Here's an example `docker-compose.yml` file that includes all three services:

```yaml
version: '3'

services:
  oavc:
    image: opensips/ai-voice-connector:latest
    ports:
      - "5060:5060/udp"
      - "35000-65000:35000-65000/udp"
    volumes:
      - ./cfg:/app/cfg
    environment:
      - CONFIG_FILE=/app/cfg/config.ini
    depends_on:
      - vosk
      - piper
    restart: unless-stopped

  vosk:
    image: alphacep/kaldi-en:latest
    ports:
      - "2700:2700"
    command: /opt/vosk-server/websocket/asr_server.py /opt/vosk-model-en-us-0.22
    restart: unless-stopped

  piper:
    image: rhasspy/piper-websocket:latest
    ports:
      - "5002:5002"
    volumes:
      - ./piper-voices:/app/voices
    environment:
      - PIPER_MODEL=en_US-lessac-medium
      - WS_PORT=5002
    restart: unless-stopped
```

## Starting the Services

To start all services, run:

```bash
docker-compose up -d
```

To check the logs:

```bash
docker-compose logs -f
```

## Volumes and File Mounts

The Docker Compose file mounts the following volumes:

- `./cfg:/app/cfg`: Mounts the local configuration directory to the OAVC container
- `./piper-voices:/app/voices`: Mounts the local Piper voices directory to the Piper container

### Custom Vosk Models

If you need to use a custom Vosk model, you can add a volume to the Vosk service:

```yaml
volumes:
  - ./models/vosk-model-custom:/opt/vosk-model-custom
```

And then update the command to:

```yaml
command: /opt/vosk-server/websocket/asr_server.py /opt/vosk-model-custom
```

### Custom Piper Voices

To use custom Piper voices, download them to the `./piper-voices` directory and specify the desired voice in the environment variables:

```yaml
environment:
  - PIPER_MODEL=custom-voice-name
```

## Resource Requirements and Tuning

- **OAVC**: Minimal resources (around 100-200MB RAM)
- **Vosk STT Server**: Depends on the model size
  - Small models: 500MB-1GB RAM
  - Medium models: 1-2GB RAM
  - Large models: 2-4GB RAM
- **Piper TTS Server**: Typically requires 500MB-1GB RAM
  - CPU usage varies depending on the voice model complexity
  - For better performance, consider using smaller voice models

For better performance on systems with limited resources, consider using smaller models or setting Docker resource limits in your compose file:

```yaml
services:
  vosk:
    deploy:
      resources:
        limits:
          memory: 2G
  piper:
    deploy:
      resources:
        limits:
          memory: 1G
```

## Troubleshooting

### Common Issues

1. **Connection refused to Vosk or Piper server**:
   - Ensure the services are running: `docker-compose ps`
   - Check the service logs: `docker-compose logs vosk` or `docker-compose logs piper`

2. **Audio not being transcribed**:
   - Verify the sample rates match between the audio and STT/TTS models
   - Check that the WebSocket URLs are correct in the configuration
   - Ensure the VAD settings are appropriate for your audio input (see docs/VOSK.md for details)

3. **TTS not generating audio**:
   - Verify that the specified voice model exists and is properly loaded
   - Check the Piper logs for any error messages
   - Ensure the audio format settings are compatible with the SIP call codecs

4. **High CPU or memory usage**:
   - Try using smaller STT/TTS models
   - Enable and tune VAD to reduce audio processing
   - Adjust Docker resource limits

### Checking Logs

To view logs from specific services:

```bash
docker-compose logs oavc    # OAVC service logs
docker-compose logs vosk    # Vosk service logs
docker-compose logs piper   # Piper service logs
```

## Upgrading

To upgrade to a newer version:

1. Pull the latest images: `docker-compose pull`
2. Restart the services: `docker-compose up -d`

## Building from Source

If you need to build the OAVC image from source, make sure you have a Dockerfile in the project root and run:

```bash
docker-compose build
docker-compose up -d
``` 