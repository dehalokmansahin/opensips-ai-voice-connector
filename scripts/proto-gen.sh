#!/bin/bash

# gRPC Protocol Buffer Code Generation Script
set -e

echo "🔧 Generating gRPC code from protocol buffer definitions..."

# Ensure grpc_tools is available
python3 -c "import grpc_tools" || {
    echo "❌ grpc_tools not found. Installing..."
    pip install grpcio-tools
}

# Function to generate code for a service
generate_service_proto() {
    local service_name=$1
    local proto_dir="services/${service_name}/proto"
    local output_dir="services/${service_name}/src"
    
    if [ -d "$proto_dir" ] && [ -n "$(ls -A $proto_dir/*.proto 2>/dev/null)" ]; then
        echo "📋 Generating code for $service_name..."
        
        mkdir -p "$output_dir"
        
        python3 -m grpc_tools.protoc \
            --python_out="$output_dir" \
            --grpc_python_out="$output_dir" \
            --proto_path="$proto_dir" \
            --proto_path="shared/proto" \
            "$proto_dir"/*.proto
            
        echo "✅ Generated gRPC code for $service_name"
    else
        echo "⚠️ No .proto files found in $proto_dir, skipping $service_name"
    fi
}

# Generate shared protocol definitions first
if [ -d "shared/proto" ] && [ -n "$(ls -A shared/proto/*.proto 2>/dev/null)" ]; then
    echo "📋 Generating shared protocol definitions..."
    
    mkdir -p "shared/proto_generated"
    
    python3 -m grpc_tools.protoc \
        --python_out="shared/proto_generated" \
        --grpc_python_out="shared/proto_generated" \
        --proto_path="shared/proto" \
        shared/proto/*.proto
        
    echo "✅ Generated shared protocol definitions"
fi

# Generate code for each service
services=(
    "ai-voice-connector"
    "vad-service" 
    "asr-service"
    "llm-service"
    "tts-service"
    "session-manager"
    "context-store"
    "banking-service"
)

for service in "${services[@]}"; do
    generate_service_proto "$service"
done

# Fix Python import paths in generated files
echo "🔧 Fixing Python import paths..."

# Fix imports in shared generated files
if [ -d "shared/proto_generated" ]; then
    find shared/proto_generated -name "*_pb2*.py" -exec sed -i 's/^import \([^.]*\)_pb2/from . import \1_pb2/g' {} \; 2>/dev/null || true
    
    # Create __init__.py files
    touch shared/__init__.py
    touch shared/proto_generated/__init__.py
fi

# Fix imports in service generated files  
find services -name "*_pb2*.py" -exec sed -i 's/^import common_pb2/from shared.proto_generated import common_pb2/g' {} \; 2>/dev/null || true
find services -name "*_pb2*.py" -exec sed -i 's/^import \([^.]*\)_pb2/from . import \1_pb2/g' {} \; 2>/dev/null || true

# Create __init__.py files for services
for service in "${services[@]}"; do
    if [ -d "services/${service}/src" ]; then
        touch "services/${service}/__init__.py"
        touch "services/${service}/src/__init__.py"
    fi
done

echo "🎉 gRPC code generation complete!"
echo ""
echo "Generated files:"
echo "- Shared protobuf definitions: shared/proto_generated/"
for service in "${services[@]}"; do
    if [ -d "services/${service}/src" ]; then
        echo "- ${service}: services/${service}/src/"
    fi
done