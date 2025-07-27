#!/bin/bash
"""
Unified gRPC Protocol Buffer Code Generation Script
Generates Python code for all proto definitions in shared/proto/
"""

set -e

PROTO_DIR="shared/proto"
OUTPUT_DIR="shared/proto_generated"
CORE_OUTPUT_DIR="core/grpc_clients"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🔧 OpenSIPS AI Voice Connector - Proto Code Generation${NC}"
echo "=================================================="

# Check if protoc is installed
if ! command -v python -m grpc_tools.protoc &> /dev/null; then
    echo -e "${RED}❌ grpcio-tools not found. Installing...${NC}"
    pip install grpcio-tools
fi

# Create output directories
echo -e "${YELLOW}📁 Creating output directories...${NC}"
mkdir -p "$OUTPUT_DIR"
mkdir -p "$CORE_OUTPUT_DIR"

# Clean previous generated files
echo -e "${YELLOW}🧹 Cleaning previous generated files...${NC}"
rm -f "$OUTPUT_DIR"/*_pb2.py "$OUTPUT_DIR"/*_pb2_grpc.py
rm -f "$CORE_OUTPUT_DIR"/*_pb2.py "$CORE_OUTPUT_DIR"/*_pb2_grpc.py

# Generate Python code for all proto files
echo -e "${YELLOW}⚙️  Generating Python code from proto files...${NC}"

for proto_file in "$PROTO_DIR"/*.proto; do
    if [ -f "$proto_file" ]; then
        filename=$(basename "$proto_file")
        echo -e "   📄 Processing: $filename"
        
        # Generate to shared directory
        python -m grpc_tools.protoc \
            --proto_path="$PROTO_DIR" \
            --python_out="$OUTPUT_DIR" \
            --grpc_python_out="$OUTPUT_DIR" \
            "$proto_file"
        
        # Generate to core directory (for backwards compatibility)
        python -m grpc_tools.protoc \
            --proto_path="$PROTO_DIR" \
            --python_out="$CORE_OUTPUT_DIR" \
            --grpc_python_out="$CORE_OUTPUT_DIR" \
            "$proto_file"
    fi
done

# Create __init__.py files
echo -e "${YELLOW}📄 Creating __init__.py files...${NC}"
cat > "$OUTPUT_DIR/__init__.py" << 'EOF'
"""Generated gRPC Protocol Buffer code"""

# Common messages
from .common_pb2 import *
from .common_pb2_grpc import *

# Service specific messages
from .asr_service_pb2 import *
from .asr_service_pb2_grpc import *
from .llm_service_pb2 import *
from .llm_service_pb2_grpc import *
from .tts_service_pb2 import *
from .tts_service_pb2_grpc import *

# Simple LLM service (alternative)
try:
    from .llm_service_simple_pb2 import *
    from .llm_service_simple_pb2_grpc import *
except ImportError:
    pass

__all__ = [
    # Add all exported symbols here as needed
]
EOF

# Verify generated files
echo -e "${YELLOW}✅ Verifying generated files...${NC}"
generated_count=$(find "$OUTPUT_DIR" -name "*_pb2*.py" | wc -l)
echo -e "   📊 Generated $generated_count proto files"

# List generated files
echo -e "${YELLOW}📋 Generated files:${NC}"
for file in "$OUTPUT_DIR"/*.py; do
    if [ -f "$file" ]; then
        echo -e "   ✅ $(basename "$file")"
    fi
done

echo -e "${GREEN}✅ Proto code generation completed successfully!${NC}"
echo "=================================================="
echo -e "${YELLOW}📝 Next Steps:${NC}"
echo "   1. Update service imports to use shared/proto_generated"
echo "   2. Test service communication"
echo "   3. Remove old proto directories if no longer needed"
echo ""