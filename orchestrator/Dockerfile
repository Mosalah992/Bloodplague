FROM node:24-alpine AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
ENV PYTHONPATH=/app:/app/orchestrator:/app/shared \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# --- deps layer (cache-stable) ---
COPY orchestrator/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# --- shared code layer ---
COPY agents/shared/ /app/shared/
COPY agents/courier/system_prompt.txt /app/agent_prompts/courier_system_prompt.txt
COPY agents/analyst/system_prompt.txt /app/agent_prompts/analyst_system_prompt.txt
COPY agents/guardian/system_prompt.txt /app/agent_prompts/guardian_system_prompt.txt

# --- orchestrator code + built frontend ---
COPY orchestrator/ /app/orchestrator/
COPY sim/ /app/sim/
COPY --from=frontend-build /frontend/dist /app/orchestrator/static

# --- healthcheck: orchestrator /status must return 200 ---
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=4 \
  CMD python -c "import urllib.request,sys;r=urllib.request.urlopen('http://127.0.0.1:8000/status',timeout=3);sys.exit(0 if r.status==200 else 1)" || exit 1

CMD ["uvicorn", "orchestrator.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-config", "/app/orchestrator/logging.json"]
