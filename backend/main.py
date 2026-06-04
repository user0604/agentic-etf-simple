"""FastAPI backend for the Multi-Agent Stock Portfolio System."""

import asyncio
import json
import logging
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from backend.orchestrator import Orchestrator

# ── Logging setup ──────────────────────────────────────────────────
LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "server.log"

file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter(
    fmt="%(asctime)s [%(levelname)-7s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
))

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter(
    fmt="%(asctime)s [%(levelname)-7s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
))

root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)

logger = logging.getLogger(__name__)
logger.info(f"Logging to {LOG_FILE.resolve()}")
load_dotenv()

app = FastAPI(title="Stock Portfolio Agent", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

RUNS_DIR = Path(__file__).resolve().parent / "runs"
RUNS_DIR.mkdir(exist_ok=True)

_active_runs: dict[str, Orchestrator] = {}


class RunRequest(BaseModel):
    budget: str
    date: str


class ResumeRequest(BaseModel):
    folder: str


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.post("/api/run")
async def start_run(req: RunRequest):
    """Start a new portfolio run."""
    run_id = uuid.uuid4().hex[:12]
    orch = Orchestrator(budget=req.budget, purchase_date=req.date, run_id=run_id)
    _active_runs[run_id] = orch
    return {"run_id": run_id, "log_path": str(orch._logger.path)}


@app.post("/api/run/resume")
async def resume_run(req: ResumeRequest):
    """Resume a run from a saved folder path."""
    folder = req.folder
    if not os.path.isdir(folder):
        raise HTTPException(status_code=400, detail=f"Folder not found: {folder}")
    try:
        orch = Orchestrator.from_run_folder(folder)
        _active_runs[orch.run_id] = orch
        return {"run_id": orch.run_id, "resumed_from": folder, "phase": orch.phase.value}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to resume: {e}")


@app.get("/api/run/{run_id}/events")
async def stream_events(run_id: str):
    """SSE endpoint for agent activity events."""
    orchestrator = _active_runs.get(run_id)
    if not orchestrator:
        raise HTTPException(status_code=404, detail="Run not found")

    async def event_generator():
        queue = asyncio.Queue()

        async def emit(payload):
            await queue.put(payload)

        orchestrator.on_event(emit)

        run_task = asyncio.create_task(_execute_run(orchestrator, run_id))

        while True:
            payload = await queue.get()
            yield {"event": "message", "data": json.dumps(payload, default=str)}
            if payload.get("status") in ("final", "error"):
                _active_runs.pop(run_id, None)
                break

    return EventSourceResponse(event_generator())


async def _execute_run(orchestrator: Orchestrator, run_id: str):
    try:
        result = await orchestrator.run()
        timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        filename = f"{timestamp}_JPY{orchestrator.budget}.json"
        filepath = RUNS_DIR / filename
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump({
                "run_id": run_id,
                "budget": orchestrator.budget,
                "date": orchestrator.purchase_date,
                "result": result,
                "created_at": timestamp,
            }, f, indent=2, default=str)
    except Exception as e:
        logger.exception("Run failed")
        await orchestrator._emit("A", "error", str(e))
        raise


@app.get("/api/runs")
async def list_runs():
    """List past runs from the runs directory."""
    runs = []
    if RUNS_DIR.exists():
        for f in sorted(RUNS_DIR.glob("*.json"), reverse=True):
            try:
                data = json.loads(f.read_text())
                portfolio = data.get("result", {})
                holdings = portfolio.get("holdings", [])
                runs.append({
                    "id": data["run_id"],
                    "date": data.get("date", f.stem[:19]),
                    "budget": data.get("budget", 0),
                    "holdings": len(holdings),
                })
            except (json.JSONDecodeError, KeyError):
                continue
    return runs


@app.get("/api/runs/{run_id}")
async def get_run(run_id: str):
    """Get a specific run's full output."""
    if RUNS_DIR.exists():
        for f in RUNS_DIR.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                if data.get("run_id") == run_id:
                    return data
            except json.JSONDecodeError:
                continue
    raise HTTPException(status_code=404, detail="Run not found")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)