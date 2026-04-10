FROM python:3.12-slim
WORKDIR /app
ENV PYTHONPATH=/app:/app/shared \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# --- deps layer (cache-stable across agent code edits) ---
COPY agents/shared/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# --- shared library layer ---
COPY agents/shared /app/shared

# --- role-specific code (changes most often → last) ---
COPY agents/analyst /app

# --- healthcheck: redis reachability via REDIS_URL ---
HEALTHCHECK --interval=20s --timeout=15s --start-period=15s --retries=4 \
  CMD python -c "import os,redis,sys;redis.from_url(os.environ.get('REDIS_URL','redis://redis:6379/0')).ping();sys.exit(0)" || exit 1

CMD ["python", "-u", "agent.py"]
