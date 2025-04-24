# Docker Instructions for OpenSIPS AI Voice Connector with Vosk STT

This document describes how to deploy the OpenSIPS AI Voice Connector (OAVC) with Vosk Speech-to-Text integration using Docker.

## Prerequisites

- Docker and Docker Compose installed
- At least 2GB of RAM for the basic setup
- Network ports 5060/UDP (SIP), 35000-35100/UDP (RTP), and 2700/TCP (WebSocket) open

## Services Architecture

The Docker Compose setup includes the following services:

1. **OAVC (OpenSIPS AI Voice Connector)**: The main application that handles SIP calls and processes audio
2. **Vosk STT Server**: Provides speech-to-text capabilities via WebSocket

## Configuration Files

Before starting the services, ensure you have the following configuration files in the `cfg/` directory:

- `vosk.cfg`: Configuration for the Vosk STT integration
- `opensips.cfg`: OpenSIPS configuration (if needed)

## Environment Variables

The following environment variables can be configured in the `docker-compose.yml` file:

### OAVC Service
- `CONFIG_FILE`: Path to the configuration file inside the container
- `VOSK_WS_URL`: WebSocket URL of the Vosk server
- `VOSK_SAMPLE_RATE`: Sample rate for the audio sent to Vosk (typically 8000 for telephony)

### Vosk Service
- `VOSK_MODEL_PATH`: Path to the Vosk model directory
- `VOSK_SAMPLE_RATE`: Sample rate for the Vosk model

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

- `./cfg:/app/cfg`: Mounts the local configuration directory to the container

If you need to use a custom Vosk model, you can add a volume to the Vosk service:

```yaml
volumes:
  - ./models/vosk-model-custom:/opt/vosk-model-custom
```

And then update the command to:

```yaml
command: /opt/vosk-server/websocket/asr_server.py /opt/vosk-model-custom
```

## Resource Requirements and Tuning

- **OAVC**: Minimal resources (around 100-200MB RAM)
- **Vosk STT Server**: Depends on the model size
  - Small models: 500MB-1GB RAM
  - Medium models: 1-2GB RAM
  - Large models: 2-4GB RAM

For better performance on systems with limited resources, consider using smaller Vosk models or setting Docker resource limits.

## Troubleshooting

### Common Issues

1. **Connection refused to Vosk server**:
   - Ensure the Vosk service is running: `docker-compose ps`
   - Check Vosk logs: `docker-compose logs vosk`

2. **Audio not being transcribed**:
   - Verify the sample rate matches between the audio and Vosk model
   - Check that the WebSocket URL is correct in the configuration

3. **High CPU or memory usage**:
   - Try using a smaller Vosk model
   - Enable VAD to reduce audio processing
   - Adjust Docker resource limits

### Checking Logs

To view logs from specific services:

```bash
docker-compose logs oavc    # OAVC service logs
docker-compose logs vosk    # Vosk service logs
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