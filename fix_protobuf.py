#!/usr/bin/env python3
"""Fix protobuf files by removing runtime_version import"""

import os
import re

def fix_protobuf_file(filepath):
    """Remove runtime_version import from protobuf file"""
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Remove runtime_version import
    content = re.sub(r'from google\.protobuf import runtime_version.*\n', '', content)
    content = re.sub(r'import runtime_version.*\n', '', content)
    
    # Remove ValidateProtobufRuntimeVersion call
    content = re.sub(r'_runtime_version\.ValidateProtobufRuntimeVersion\([^)]*\)\n', '', content, flags=re.DOTALL)
    
    with open(filepath, 'w') as f:
        f.write(content)
    print(f"Fixed: {filepath}")

# Fix all protobuf files
for root, dirs, files in os.walk("core/grpc_clients"):
    for file in files:
        if file.endswith("_pb2.py"):
            fix_protobuf_file(os.path.join(root, file))

for root, dirs, files in os.walk("shared/proto_generated"):
    for file in files:
        if file.endswith("_pb2.py"):
            fix_protobuf_file(os.path.join(root, file))

print("All protobuf files fixed!")