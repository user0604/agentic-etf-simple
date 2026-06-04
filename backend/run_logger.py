"""Run persistence — saves every agent call to disk for audit trail and resume.

Each run creates a folder: runs/YYYY-MM-DDTHH-MM-SS_RUNID/
Inside, each agent call creates: 001_M_macro.txt, 002_B_planning.txt, etc.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class RunLogger:
    """Logs every agent interaction to a per-run folder on disk.

    Usage:
        logger = RunLogger(run_id, budget, date)
        await logger.log_call("M", "macro", system_prompt, user_msg, response_text, parsed_result)
        # Later:
        logger.save_final_portfolio(portfolio)
    """

    def __init__(self, run_id: str, budget: str, purchase_date: str):
        timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        runs_dir = Path(__file__).resolve().parent / "runs"
        self.folder = runs_dir / f"{timestamp}_{run_id}"
        self.folder.mkdir(parents=True, exist_ok=True)
        self._call_counter = 0

        # Write run metadata
        meta = {
            "run_id": run_id,
            "budget": budget,
            "purchase_date": purchase_date,
            "started_at": timestamp,
        }
        (self.folder / "_meta.json").write_text(json.dumps(meta, indent=2))
        logger.info(f"Run directory: {self.folder}")

    @property
    def path(self) -> Path:
        return self.folder

    async def log_call(
        self,
        agent: str,
        phase: str,
        system_prompt: str,
        user_message: str,
        response_text: str,
        parsed_result: dict | None,
        detail_payload: dict | None = None,
    ):
        """Save a single agent call to disk.

        Args:
            agent: Agent ID ("M", "B", "C", "D", "X1", etc.)
            phase: Phase name ("macro", "planning", "research", etc.)
            system_prompt: The system prompt sent to the LLM.
            user_message: The user message sent to the LLM.
            response_text: Raw response text from the LLM.
            parsed_result: Parsed JSON dict from the response (or None).
            detail_payload: Extra detail to emit to the UI (macro brief, debate, etc.)
        """
        self._call_counter += 1
        seq = f"{self._call_counter:03d}"
        safe_name = f"{seq}_{agent}_{phase}".replace(" ", "_")

        entry = {
            "sequence": self._call_counter,
            "agent": agent,
            "phase": phase,
            "system_prompt": system_prompt,
            "user_message": user_message,
            "response_text": response_text,
            "parsed_result": parsed_result,
            "detail": detail_payload,
        }

        filepath = self.folder / f"{safe_name}.json"
        filepath.write_text(json.dumps(entry, indent=2, default=str), encoding="utf-8")

        # Also write a human-friendly summary
        summary_path = self.folder / f"{safe_name}_summary.txt"
        summary_path.write_text(
            f"=== {agent} | {phase} | call #{self._call_counter} ===\n\n"
            f"System prompt: {system_prompt[:200]}...\n"
            f"User: {user_message[:200]}...\n"
            f"Response: {response_text[:500]}...\n"
            f"Parsed: {json.dumps(parsed_result, indent=2, default=str)[:500]}...\n",
            encoding="utf-8",
        )

    def save_final_portfolio(self, portfolio: dict):
        """Save the final portfolio output."""
        filepath = self.folder / "_final_portfolio.json"
        filepath.write_text(json.dumps(portfolio, indent=2, default=str), encoding="utf-8")

    def save_m_update_changelog(self, changelog: list):
        """Save the M-update changelog."""
        filepath = self.folder / "_m_updates.json"
        filepath.write_text(json.dumps(changelog, indent=2, default=str), encoding="utf-8")


# ── Resume helpers ─────────────────────────────────────────────────

def load_run_folder(folder_path: str) -> dict[str, Any]:
    """Load all agent call logs from a run folder.

    Returns a dict with:
        - meta: run metadata
        - calls: list of agent call entries sorted by sequence
        - final_portfolio: the final portfolio (if saved)
        - last_phase: the last completed phase
    """
    folder = Path(folder_path)
    if not folder.is_dir():
        raise ValueError(f"Run folder not found: {folder_path}")

    meta = {}
    meta_file = folder / "_meta.json"
    if meta_file.exists():
        meta = json.loads(meta_file.read_text(encoding="utf-8"))

    # Load all agent call files in sequence order
    call_files = sorted(folder.glob("[0-9][0-9][0-9]_*.json"))
    calls = []
    last_phase = None
    for cf in call_files:
        entry = json.loads(cf.read_text(encoding="utf-8"))
        calls.append(entry)
        last_phase = entry.get("phase", last_phase)

    final_portfolio = {}
    fp_file = folder / "_final_portfolio.json"
    if fp_file.exists():
        final_portfolio = json.loads(fp_file.read_text(encoding="utf-8"))

    m_updates = []
    mu_file = folder / "_m_updates.json"
    if mu_file.exists():
        m_updates = json.loads(mu_file.read_text(encoding="utf-8"))

    return {
        "meta": meta,
        "calls": calls,
        "final_portfolio": final_portfolio,
        "m_updates": m_updates,
        "last_phase": last_phase,
        "folder": folder_path,
    }