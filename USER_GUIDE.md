# Epidemic Lab — User Guide

## Table of Contents
1. [Quick Start (TL;DR)](#1-quick-start-tldr)
2. [Prerequisites](#2-prerequisites)
3. [Starting & Stopping the System](#3-starting--stopping-the-system)
4. [Dashboard Options](#4-dashboard-options)
5. [The Three Agents](#5-the-three-agents)
6. [Running Simulations and Soak Tests](#6-running-simulations-and-soak-tests)
7. [SIEM Search and Investigation](#7-siem-search-and-investigation)
8. [Troubleshooting](#8-troubleshooting)
9. [Quick Command Reference](#9-quick-command-reference)

---

## 1. Quick Start (TL;DR)

```powershell
# 1. Ensure Ollama is running on your machine
ollama serve

# 2. Start all services
cd "E:\CODE PROKECTS\Epidemic_Lab"
docker-compose up -d

# 3. Open the dashboard
# Web UI: http://localhost:8000
# Or TUI: python dashboard/main.py
```

To stop:
```powershell
docker-compose down
```

---

## 2. Prerequisites

### Required Software
| Software | Purpose | Download |
|----------|---------|----------|
| Docker Desktop | Runs all containers | https://www.docker.com/products/docker-desktop |
| Ollama | Local LLM inference | https://ollama.com |
| Python 3.11+ | Running scripts and TUI dashboard | https://www.python.org |

### Required Ollama Models
Pull these **before** starting — only needed once:
```powershell
ollama pull llama3.2:latest          # Used by Guardian and Analyst
ollama pull dolphin-mistral:latest   # Used by Courier for attack generation
```

Verify Ollama is accessible:
```powershell
curl http://localhost:11434/api/tags
# Should return JSON with your installed models
```

### Docker Desktop Settings
- **Memory:** Minimum 6 GB recommended (Settings → Resources → Memory)
- **Disk:** At least 10 GB free

---

## 3. Starting & Stopping the System

### Start
```powershell
cd "E:\CODE PROKECTS\Epidemic_Lab"
docker-compose up -d
```

Wait ~10 seconds for all agents to initialize.

### Verify All Containers Are Running
```powershell
docker-compose ps
```

Expected output — all 5 containers should show `Up`:
```
NAME                    STATUS          PORTS
epidemic-redis          Up X seconds    0.0.0.0:6379->6379/tcp
epidemic-orchestrator   Up X seconds    0.0.0.0:8000->8000/tcp
epidemic-agent-a        Up X seconds
epidemic-agent-b        Up X seconds
epidemic-agent-c        Up X seconds
```

If any container shows `Exited`, see [Troubleshooting](#8-troubleshooting).

### Stop
```powershell
docker-compose down
```

### Rebuild After Code Changes
```powershell
docker-compose build
docker-compose up -d
```

---

## 4. Dashboard Options

Epidemic Lab provides multiple interfaces for control and monitoring.

### Web Dashboard (Primary)
Open **http://localhost:8000** in your browser.

The dashboard has three tabs: **Simulation Control**, **Search**, and **Live**.

#### Tab 1 — Simulation Control
- Inject worms into agents
- Quarantine agents
- Reset the simulation
- Download logs
- Monitor agent health

#### Tab 2 — Search
- Query past events using SIEM
- Investigate infection chains
- Load and analyze soak runs

#### Tab 3 — Live
- Real-time event monitoring
- Agent state updates
- Live metrics

### React Frontend (Alternative Web UI)
For a modern React-based interface:
```powershell
cd frontend
npm install
npm run dev
```
Then open **http://localhost:5173** (or as configured in vite.config.js).

### Terminal UI (TUI) Dashboard
For a command-line interface:
```powershell
python dashboard/main.py
```
This provides inject/quarantine/reset controls and health monitoring in the terminal.

---

## 5. The Three Agents

### Agent-A: Guardian (High Security)
**Role:** Terminal node with adaptive defense  
**Defense level:** 0.85 (high)  
**Model:** `llama3.2:latest`

The Guardian evaluates threats, applies defenses, and learns from attacks. It uses:
- LLM threat analysis
- Adaptive defense strategies
- Suspicion tracking
- Immunity accumulation

**Typical outcome:** Blocks ~85-95% of attacks

### Agent-B: Analyst (Medium Security)
**Role:** Intermediary with compliance analysis  
**Defense level:** 0.50 (medium)  
**Model:** `llama3.2:latest`

The Analyst assesses message compliance using LLM analysis and probabilistic logic. It can quarantine advisories and modulate infection risk.

**Typical outcome:** Allows ~40-60% of attacks through

### Agent-C: Courier (Low Security / Attacker)
**Role:** Ingress point and attack generator  
**Defense level:** 0.15 (low)  
**Model:** `dolphin-mistral:latest` for attacks

The Courier is easily infected and generates sophisticated attacks using LLM. Once infected, it propagates payloads with mutations.

**Typical outcome:** Nearly always infected, generates attack variants

### Infection Flow
```
Orchestrator → Agent-C (Courier) → Agent-B (Analyst) → Agent-A (Guardian)
```

---

## 6. Running Simulations and Soak Tests

### Manual Simulation
Use the dashboard to inject worms and observe propagation.

### Soak Tests
Run extended simulations for research:
```powershell
# 30-minute test
python scripts/run_wallclock_research_validation.py --hours 0.5

# 6-hour full soak
python scripts/run_wallclock_research_validation.py --hours 6
```

Options:
- `--baseline-artifact`: Compare against previous runs
- `--inject-every-minutes`: Customize injection frequency
- `--build`: Rebuild containers

Output saved to `logs/soak_run_NN/` with reports and analytics.

### Other Validation Scripts
- `run_long_research_validation.py`: Longer-duration tests
- `run_phase3_validation.py`: Phase 3 validation
- `run_soc_validation.py`: SOC-focused validation

---

## 7. SIEM Search and Investigation

### Query Language
Use structured queries like `event=INFECTION_SUCCESSFUL AND src=agent-c`.

### Capabilities
- Exact, inequality, boolean, wildcard, and time-based queries
- Trace by event, injection, or reset
- Related events and payload lineage
- Campaign and mutation analytics
- Live event polling

### Loading Soak Runs
In the Search tab, load completed runs from the library to query their events.

---

## 8. Troubleshooting

### Containers Not Starting
- Ensure Ollama is running
- Check Docker memory allocation
- Verify models are pulled

### No Events Appearing
- Confirm Redis connectivity
- Manually inject a test worm via API

### LLM Issues
- Verify model availability
- Check container logs for errors

### API Timeouts
- Rebuild containers if needed
- Check for large datasets causing timeouts

---

## 9. Quick Command Reference

### Docker
```powershell
docker-compose up -d    # Start
docker-compose down     # Stop
docker-compose ps       # Status
docker-compose build    # Rebuild
```

### Ollama
```powershell
ollama serve           # Start service
ollama pull <model>    # Download model
ollama list            # List models
```

### Simulation Control
```powershell
# Inject worm
curl -X POST http://localhost:8000/inject/agent-c -H "Content-Type: application/json" -d "{\"worm_level\": \"easy\"}"

# Quarantine
curl -X POST http://localhost:8000/quarantine/agent-c

# Reset
curl -X POST http://localhost:8000/reset
```

### Soak Tests
```powershell
python scripts/run_wallclock_research_validation.py --hours 6
```

# Rebuild first, then run
python scripts/run_wallclock_research_validation.py --hours 6 --build
```

### Logs

```powershell
# List all soak runs
dir logs\soak_run_*

# Download logs via API (saves ZIP)
curl http://localhost:8000/logs/dump -o epidemic_logs.zip

# Open latest report
notepad logs\latest_wallclock_research_report.md
```

---

## URL Reference

| URL | What's there |
|-----|-------------|
| http://localhost:8000 | Dashboard (main entry point) |
| http://localhost:8000/dashboard | Dashboard (alternate URL) |
| http://localhost:8000/status | System status (JSON) |
| http://localhost:8000/events | Raw event feed (JSON) |
| http://localhost:8000/api/runs | Available soak runs (JSON) |
| http://localhost:8000/api/health | SIEM health check (JSON) |
| http://localhost:8000/api/search | Search endpoint (JSON) |
| http://localhost:8000/logs/dump | Download all logs (ZIP) |
