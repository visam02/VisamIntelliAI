FROM python:3.11-slim

WORKDIR /app

# Install system deps for eventlet
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements-web.txt .
RUN pip install --no-cache-dir -r requirements-web.txt

# Copy application
COPY web_server.py .
COPY ui/ ui/

# Render.com sets PORT env var dynamically
ENV PORT=5000
ENV LLM_API_KEY=""
ENV LLM_BASE_URL="https://api.groq.com/openai/v1"
ENV LLM_MODEL="llama-3.3-70b-versatile"

EXPOSE ${PORT}

# Use gunicorn with eventlet for production WebSocket support
CMD gunicorn --worker-class eventlet -w 1 --bind 0.0.0.0:${PORT} --timeout 120 web_server:app
