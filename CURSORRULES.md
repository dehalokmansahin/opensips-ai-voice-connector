# CursorRules: LLM Integration WebSocket Server Repository

## 🧩 Project Overview
This repository provides a lightweight Python WebSocket server that:
- Loads a `.gguf` LLaMA‐cpp model via `llama-cpp-python`.
- Accepts `{ "system_prompt": ..., "prompt": ... }` over WebSocket.
- Streams incremental LLM responses back as JSON chunks.
- Is fully Dockerized and ready to publish to Docker Hub.

## 📁 Repository Structure

```
├── CURSORRULES.md         # This documentation file
├── server.py              # WebSocket server entrypoint
├── llm_stream.py          # LLM loading & streaming utilities
├── requirements.txt       # Python dependencies
├── Dockerfile             # Docker image build definition
└── model/                 # Place your .gguf model(s) here
```

## 🚀 WebSocket Server (`server.py`)
- Uses `websockets` to listen on port `8765` by default.
- On connection, receives a single JSON payload:
  ```json
  { "system_prompt": "...", "prompt": "..." }
  ```
- Calls `stream_chat` (or `stream_generate`) from `llm_stream.py`.
- Sends each token/chunk as:
  ```json
  { "chunk": "..." }
  ```
- Sends `{ "done": true }` when the stream ends.

## 🐳 Dockerization

### Dockerfile
```dockerfile
FROM python:3.10-slim
WORKDIR /app

# Install dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose WebSocket port
EXPOSE 8765

# Entrypoint
CMD ["python", "server.py"]
```

### Build & Push to Docker Hub
1. **Build image** (replace `<username>` and `<repo>`):
   ```bash
   docker build -t <username>/llm-ws-server:latest .
   ```
2. **Login to Docker Hub**:
   ```bash
   docker login --username <username>
   ```
3. **Push image**:
   ```bash
   docker push <username>/llm-ws-server:latest
   ```

## ⚙️ Environment & Configuration
- `MODEL_DIR` (default: `model/`): directory where your `.gguf` model file resides.
- **Ports**: WebSocket listens on `0.0.0.0:8765`.

You can override these by:
```bash
docker run -e MODEL_DIR=/data/models -p 8765:8765 <username>/llm-ws-server
```

## 📋 Usage Example

1. Place your `model.gguf` inside `model/`.
2. Run locally (without Docker):
   ```bash
   pip install -r requirements.txt
   python server.py
   ```
3. Or run via Docker:
   ```bash
   docker run -v $(pwd)/model:/app/model -p 8765:8765 <username>/llm-ws-server
   ```

## 📝 Documentation & Maintenance
- **When code changes** (e.g., API updates, new flags), update this `CURSORRULES.md` accordingly.
- Track environment variables, port mappings, and dependency updates.
- Ensure any breaking changes in `llm_stream.py` or `server.py` are reflected here. 