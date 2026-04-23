FROM python:3.12-slim

# System deps for Playwright + general tooling
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    wget \
    gnupg \
    ca-certificates \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install chromium --with-deps

# Copy source
COPY agent/ ./agent/
COPY eval/ ./eval/

# Seed materials are mounted at runtime, never baked into the image
# Mount: -v $(pwd)/seed:/app/seed:ro

# Kill-switch: OUTBOUND_LIVE is deliberately NOT set here.
# Set it explicitly in your run command only when you intend live outbound.
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "agent.main:app", "--host", "0.0.0.0", "--port", "8000"]
