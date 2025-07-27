FROM opensips-ai-voice-connector:base

# Copy service-specific requirements
COPY services/ai-voice-connector/requirements.txt ./service-requirements.txt
RUN pip install --user --no-cache-dir -r service-requirements.txt

# Copy shared libraries
COPY shared/ ./shared/

# Copy service source code
COPY services/ai-voice-connector/src/ ./services/ai-voice-connector/src/
COPY services/ai-voice-connector/proto/ ./services/ai-voice-connector/proto/

# Generate gRPC code
RUN python -m grpc_tools.protoc \
    --python_out=. \
    --grpc_python_out=. \
    --proto_path=services/ai-voice-connector/proto \
    services/ai-voice-connector/proto/*.proto

# Copy Pipecat source (editable install)
COPY pipecat/ ./pipecat/
RUN pip install --user -e ./pipecat/

# Expose ports
EXPOSE 8080 50051

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Start the service
CMD ["python", "-m", "services.ai_voice_connector.src.main"]