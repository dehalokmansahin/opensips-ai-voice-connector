FROM opensips-ai-voice-connector:base

# Install VAD-specific dependencies
COPY services/vad-service/requirements.txt ./service-requirements.txt
RUN pip install --user --no-cache-dir -r service-requirements.txt

# Copy shared libraries
COPY shared/ ./shared/

# Copy service source code
COPY services/vad-service/src/ ./services/vad-service/src/
COPY services/vad-service/proto/ ./services/vad-service/proto/

# Copy Pipecat source (for VAD components)
COPY pipecat/ ./pipecat/
RUN pip install --user -e ./pipecat/

# Expose gRPC port
EXPOSE 50052

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import grpc; channel=grpc.insecure_channel('localhost:50052'); grpc.channel_ready_future(channel).result(timeout=5)" || exit 1

# Start the VAD service
CMD ["python", "-m", "services.vad_service.src.main"]