FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for caching
COPY requirements.txt .

# Remove emergentintegrations from requirements (installed separately below)
RUN grep -v emergentintegrations requirements.txt > /tmp/req_no_ei.txt \
    && pip install --no-cache-dir -r /tmp/req_no_ei.txt

# Install emergentintegrations from GitHub (has llm module; payments/stubbed locally)
RUN pip install --no-cache-dir git+https://github.com/greenhorrorshorts-sys/emergentintegrations.git@main || true

# Copy full application code
COPY . .

# Expose port
EXPOSE 8000

# Healthcheck — verifies API responds on /health (no auth required)
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application
ENV PYTHONUNBUFFERED=1
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
