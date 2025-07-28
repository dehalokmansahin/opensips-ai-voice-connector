#!/bin/bash
# Fix protobuf files before starting the application
find /app/core/grpc_clients -name "*_pb2.py" -exec sed -i 's/from google.protobuf import runtime_version.*//g' {} \;
find /app/core/grpc_clients -name "*_pb2.py" -exec sed -i '/_runtime_version.ValidateProtobufRuntimeVersion/,/)/d' {} \;

# Start the application
exec python /app/core/main.py