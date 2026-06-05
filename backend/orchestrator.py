"""Agent A — Orchestrator.
Event-driven supervisor, quality gate, and phase controller.
"""

import asyncio
import hashlib
import json
import logging
import os
import uuid
from enum import Enum
from typing import Any

from dotenv import load_dotenv
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

load_dotenv()


class Phase(str, Enum):
    MACRO = "macro"
    PLANNING = "planning"
    RESEARCH = "research"
    DRAFT = "draft"
    CRITIQUE_1 = "critique_1"
    CRITIQUE_2 = "critique_2"
    CRITIQUE_3 = "critique_3"
    TIEBREAK = "tiebreak"
    FINAL = "final"


class AgentStatus(str, Enum):
    IDLE = "idle"
    WORKING = "working"
    PLAN_SUBMITTED = "plan_submitted"
    PLAN_APPROVED = "plan_approved"
    DONE = "done"


class Orchestrator:
    """Event-driven orchestrator for the multi-agent stock portfolio system."""

    def __init__(self, budget: str, purchase_date: str, run_id: str = None):
        self.budget = budget
        self.purchase_date = purchase_date
        self.run_id = run_id or uuid.uuid4().hex[:12]
        self.model = os.getenv("NIM_MODEL", "deepseek-ai/deepseek-v4-pro")
        nim_base_url = os.getenv("NIM_BASE_URL", "https://integrate.api.nvidia.com/v1")
        nim_api_key = os.getenv("NVIDIA_NIM_API_KEY", "")
        # Parse comma-separated keys — use only the first for the default client;
        # call_llm in _base.py rotates through all keys on retry.
        api_keys = [k.strip() for k in nim_api_key.split(",") if k.strip()]
        first_key = api_keys[0] if api_keys else ""
        self.client = AsyncOpenAI(api_key=first_key, base_url=nim_base_url)

        self.phase = Phase.MACRO
        self.m_update_count = 0
        self.m_update_changelog = []

        self.agents = {
            "M": AgentStatus.IDLE,
            "B": AgentStatus.IDLE,
            "C": AgentStatus.IDLE,
            "D": AgentStatus.IDLE,
        }
        self.x_agents = {}

        self.research_cache = {}
        self.dedup_log = []
        self.task_queue = []
        self.critique_history = []

        self.outputs = {
            "macro_brief": None,
            "research_tasks": None,
            "portfolio_draft": None,
            "critique_1": None,
            "critique_2": None,
            "critique_3": None,
            "tiebreak_verdict": None,
            "portfolio_final": None,
        }

        self._event_callbacks = []

        from backend.run_logger import RunLogger
        self._logger = RunLogger(self.run_id, budget, purchase_date)

    def on_event(self, callback):
        self._event_callbacks.append(callback)

    async def _emit_retry_event(self, attempt: int, status_code: int, wait: float, key_idx: int, num_keys: int):
        """Called by call_llm's retry-hook on each throttling retry."""
        await self._emit(
            "system", "retry",
            f"Rate limited (HTTP {status_code}) — "
            f"retry #{attempt}, key #{key_idx+1}/{num_keys}, "
            f"waiting {wait:.0f}s...",
            retry_info={"attempt": attempt, "status_code": status_code,
                         "wait_seconds": round(wait, 1),
                         "key_index": key_idx + 1, "total_keys": num_keys},
        )

    async def _emit(self, agent: str, status: str, message: str, **extra):
        payload = {"agent": agent, "status": status, "message": message, **extra}
        for cb in self._event_callbacks:
            try:
                await cb(payload)
            except Exception:
                logger.exception("Event callback failed")

    async def _call_agent(self, module_path: str, fn_name: str, **kwargs) -> dict:
        """Call an agent function with retry+abort and persist to disk."""
        import importlib

        module = importlib.import_module(module_path)
        fn = getattr(module, fn_name)

        last_exc = None
        for attempt in range(3):
            try:
                result = await fn(openai_client=self.client, model=self.model, **kwargs)
                break
            except Exception as e:
                logger.warning(f"Agent call {module_path}.{fn_name} attempt {attempt+1} failed: {e}")
                last_exc = e
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise
        else:
            raise last_exc

        # Persist to disk
        if isinstance(result, dict):
            agent_label = result.get("agent", fn_name)
            await self._logger.log_call(
                agent=agent_label,
                phase=self.phase.value,
                system_prompt=result.pop("_prompt", "") or "",
                user_message=result.pop("_user_message", "") or "",
                response_text=result.pop("_response_text", "") or "",
                parsed_result={k: v for k, v in result.items() if not k.startswith("_")},
                detail_payload=result.get("_detail"),
            )
            detail = result.get("_detail")
            if detail:
                await self._emit(agent_label, "detail", "", detail=detail)

        return result

    async def _compute_plan_hash(self, plan: dict) -> str:
        return hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()[:12]

    async def _deduplicate_research(self, candidates_list: list) -> list:
        merged = {}
        for entry in candidates_list:
            ticker = entry.get("ticker")
            if not ticker:
                continue
            if ticker in merged:
                self.dedup_log.append(
                    f"{ticker} appeared in multiple researchers — merged, keeping richer schema"
                )
                if len(entry) > len(merged[ticker]):
                    merged[ticker] = entry
            else:
                merged[ticker] = entry
        return list(merged.values())

    # ── Phase handlers ──────────────────────────────────────────

    async def _phase_macro(self):
        await self._emit("A", "working", "Triggering macro agent M")
        self.agents["M"] = AgentStatus.WORKING
        result = await self._call_agent("backend.agents.macro", "run_macro_agent")
        self.outputs["macro_brief"] = result.get("macro_brief")
        self.agents["M"] = AgentStatus.DONE
        await self._emit("M", "done", "Macro brief complete",
                         detail=result.get("macro_brief"))
        self.phase = Phase.PLANNING

    async def _phase_planning(self):
        await self._emit("A", "working", "Activating portfolio manager B")
        self.agents["B"] = AgentStatus.WORKING
        result = await self._call_agent(
            "backend.agents.portfolio", "run_portfolio_agent",
            macro_brief=self.outputs["macro_brief"], context=self._get_context()
        )
        self.outputs["research_tasks"] = result.get("research_tasks", [])
        self.agents["B"] = AgentStatus.DONE
        await self._emit("B", "done", f"Research plan: {len(self.outputs['research_tasks'])} tasks issued",
                         detail={"tasks": self.outputs["research_tasks"],
                                 "fx_rate": result.get("fx_rate")})

        for i, task in enumerate(self.outputs.get("research_tasks", [])):
            agent_id = f"X{i+1}"
            self.x_agents[agent_id] = AgentStatus.IDLE
            self.task_queue.append({"task": task, "assigned_to": agent_id, "status": "pending"})

        self.phase = Phase.RESEARCH

    async def _phase_research(self):
        await self._emit("A", "working", "Dispatching researcher agents")

        plans = {}
        for entry in self.task_queue:
            agent_id = entry["assigned_to"]
            task = entry["task"]
            self.x_agents[agent_id] = AgentStatus.WORKING
            await self._emit(agent_id, "working", f"Submitting plan for {task.get('topic', 'unknown')}")
            plan = await self._call_agent(
                "backend.agents.researcher", "submit_research_plan", brief=task
            )
            plans[agent_id] = plan
            self.x_agents[agent_id] = AgentStatus.PLAN_SUBMITTED

        for agent_id, plan in plans.items():
            plan_hash = plan.get("plan_hash") or await self._compute_plan_hash(plan)
            task = next((t["task"] for t in self.task_queue if t["assigned_to"] == agent_id), {})
            existing_coverage = list(self.research_cache.keys())

            if plan_hash in self.research_cache:
                self.x_agents[agent_id] = AgentStatus.DONE
                await self._emit(agent_id, "done", f"Cache hit — reusing prior result")
                continue

            review = await self._call_agent(
                "backend.agents.portfolio", "review_research_plan",
                plan=plan, existing_coverage=existing_coverage
            )
            max_attempts = 3
            attempt = 1
            while not review.get("approved", True) and attempt < max_attempts:
                feedback = review.get("feedback", "Revise")
                await self._emit(agent_id, "plan_submitted", f"Plan rejected — {feedback}")
                plan = await self._call_agent(
                    "backend.agents.researcher", "submit_research_plan", brief=task
                )
                plan_hash = plan.get("plan_hash") or await self._compute_plan_hash(plan)
                review = await self._call_agent(
                    "backend.agents.portfolio", "review_research_plan",
                    plan=plan, existing_coverage=existing_coverage
                )
                attempt += 1

            self.x_agents[agent_id] = AgentStatus.PLAN_APPROVED
            await self._emit(agent_id, "plan_approved", f"Plan approved" +
                             (f" (attempt {attempt})" if attempt > 1 else ""),
                             detail={"plan": plan.get("plan")})

            self.x_agents[agent_id] = AgentStatus.WORKING
            result = await self._call_agent(
                "backend.agents.researcher", "run_researcher_agent",
                brief=task, plan_hash=plan_hash
            )
            topic_key = task.get("topic", agent_id)
            self.research_cache[topic_key] = result.get("candidates", [])
            self.x_agents[agent_id] = AgentStatus.DONE
            n = len(result.get("candidates", []))
            await self._emit(agent_id, "done", f"Returned {n} candidate(s)",
                             detail={"candidates": result.get("candidates")})

            for req in result.get("follow_up_requests", []):
                self.task_queue.append({"task": req, "assigned_to": None, "status": "pending"})

        all_candidates = []
        for candidates in self.research_cache.values():
            all_candidates.extend(candidates)
        deduped = await self._deduplicate_research(all_candidates)
        self.outputs["research_deduped"] = deduped
        await self._emit("A", "done", f"Research complete — {len(deduped)} unique candidates after dedup",
                         detail={"deduped_count": len(deduped), "dedup_log": self.dedup_log})
        self.phase = Phase.DRAFT

    async def _phase_draft(self):
        await self._emit("A", "working", "B constructing draft portfolio")
        self.agents["B"] = AgentStatus.WORKING
        result = await self._call_agent(
            "backend.agents.portfolio", "run_portfolio_agent",
            macro_brief=self.outputs["macro_brief"], context=self._get_context()
        )
        self.outputs["portfolio_draft"] = result.get("portfolio_draft")
        self.agents["B"] = AgentStatus.DONE
        await self._emit("B", "done", "Portfolio draft constructed",
                         detail=result.get("portfolio_draft"))
        self.phase = Phase.CRITIQUE_1

    async def _phase_critique(self, round_num: int):
        output_key = f"critique_{round_num}"
        await self._emit("A", "working", f"Critique Round {round_num}")
        self.agents["C"] = AgentStatus.WORKING
        result = await self._call_agent(
            "backend.agents.critic", "run_critic_agent",
            round_num=round_num,
            portfolio_draft=self.outputs["portfolio_draft"],
            macro_brief=self.outputs["macro_brief"],
            prior_rounds=self.critique_history,
            m_update_count=self.m_update_count,
        )
        self.outputs[output_key] = result
        self.agents["C"] = AgentStatus.DONE
        await self._emit("C", "done", f"Round {round_num} critique complete",
                         detail={"round": round_num, "critique": result.get("critique"),
                                 "killer_argument": result.get("killer_argument")})

        if result.get("m_update_signal", {}).get("triggered"):
            await self._handle_m_update(result["m_update_signal"]["reason"])
            return

        self.agents["B"] = AgentStatus.WORKING
        revision = await self._call_agent(
            "backend.agents.portfolio", "run_portfolio_agent",
            macro_brief=self.outputs["macro_brief"], context=self._get_context()
        )
        self.outputs["portfolio_draft"] = revision.get("portfolio_draft")
        self.agents["B"] = AgentStatus.DONE
        await self._emit("B", "done", f"Revision after Round {round_num} complete",
                         detail=revision.get("portfolio_draft"))

        if revision.get("m_update_signal", {}).get("triggered"):
            await self._handle_m_update(revision["m_update_signal"]["reason"])
            return

        self.critique_history.append((round_num, result, revision))

        is_satisfied = result.get("satisfied", False)
        if round_num >= 3:
            if is_satisfied:
                await self._emit("C", "done", "Consensus reached — all issues resolved",
                                 detail={"satisfied": True, "round": round_num})
                self.phase = Phase.FINAL
            else:
                self.phase = Phase.TIEBREAK
        else:
            self.phase = {1: Phase.CRITIQUE_2, 2: Phase.CRITIQUE_3}.get(round_num, Phase.FINAL)

    async def _phase_tiebreak(self):
        await self._emit("A", "working", "Triggering tiebreaker D")
        last_critique = self.critique_history[-1][1] if self.critique_history else {}
        last_revision = self.critique_history[-1][2] if self.critique_history else {}

        self.agents["D"] = AgentStatus.WORKING
        result = await self._call_agent(
            "backend.agents.tiebreaker", "run_tiebreaker_agent",
            b_strongest_argument=json.dumps(last_revision.get("defence", {})),
            c_strongest_argument=json.dumps(last_critique.get("critique", {})),
            macro_brief=self.outputs["macro_brief"],
        )
        self.outputs["tiebreak_verdict"] = result
        self.agents["D"] = AgentStatus.DONE

        if result.get("m_update_signal", {}).get("triggered"):
            await self._handle_m_update(result["m_update_signal"]["reason"])
            return

        verdict = result.get("verdict", "unknown")
        await self._emit("D", "done", f"Verdict: {verdict}",
                         detail={"verdict": verdict, "reasoning": result.get("reasoning"),
                                 "required_change": result.get("required_change")})

        self.agents["B"] = AgentStatus.WORKING
        revision = await self._call_agent(
            "backend.agents.portfolio", "run_portfolio_agent",
            macro_brief=self.outputs["macro_brief"], context=self._get_context()
        )
        self.outputs["portfolio_draft"] = revision.get("portfolio_draft")
        self.agents["B"] = AgentStatus.DONE
        self.phase = Phase.FINAL

    async def _phase_final(self):
        await self._emit("A", "working", "Generating final portfolio output")

        draft = self.outputs.get("portfolio_draft") or {}
        raw_holdings = draft.get("holdings") or []

        # Build lookup from research cache to enrich holdings with thesis/price/sector
        research_lookup = {}
        for topic, candidates in self.research_cache.items():
            for c in candidates:
                tk = (c.get("ticker") or "").upper().strip()
                if tk:
                    existing = research_lookup.get(tk, {})
                    # Prefer richer entry (more keys)
                    if len(c) > len(existing):
                        research_lookup[tk] = c

        # Normalize holdings field names for the frontend
        budget_float = float(self.budget) if self.budget else 0
        normalized = []
        for h in raw_holdings:
            h_ticker = (h.get("ticker") or "?").upper().strip()
            pct = h.get("allocation_pct") or h.get("pct") or 0
            amount = h.get("allocation_jpy")
            if amount is None:
                amount = h.get("amount")
            if amount is None:
                amount = budget_float * pct / 100.0

            rc = research_lookup.get(h_ticker, {})
            thesis = h.get("thesis") or rc.get("thesis") or rc.get("investment_thesis") or ""
            price = rc.get("price") or rc.get("current_price")
            sector = rc.get("sector") or rc.get("industry") or ""
            volume = None
            if price and amount:
                try:
                    volume = round(amount / float(price))
                except (ValueError, TypeError):
                    pass

            normalized.append({
                "ticker": h_ticker,
                "name": h.get("name") or rc.get("name", h_ticker),
                "amount": amount,
                "pct": pct,
                "confidence": h.get("confidence", "medium"),
                "thesis": thesis,
                "sector": sector,
                "price": float(price) if price else None,
                "volume": volume,
            })

        self.outputs["portfolio_final"] = {
            "budget": self.budget,
            "total_budget": self.budget,
            "purchase_date": self.purchase_date,
            "fx_rate": draft.get("fx_rate", None),
            "holdings": normalized,
            "audit_trail": {
                "m_update_count": self.m_update_count,
                "m_update_changelog": self.m_update_changelog,
                "critique_rounds": len(self.critique_history),
                "tiebreak_used": self.outputs.get("tiebreak_verdict") is not None,
                "dedup_log": self.dedup_log,
                "research_cache_size": len(self.research_cache),
            },
        }
        self._logger.save_final_portfolio(self.outputs["portfolio_final"])
        self._logger.save_m_update_changelog(self.m_update_changelog)
        await self._emit("A", "final", "Run complete", portfolio=self.outputs["portfolio_final"])

    async def _handle_m_update(self, reason: str = None):
        self.m_update_count += 1
        self.m_update_changelog.append({
            "update_number": self.m_update_count,
            "reason": reason,
            "triggered_by": self.phase.value,
        })
        await self._emit("A", "working", f"M-update #{self.m_update_count}: {reason}")

        self.agents["M"] = AgentStatus.WORKING
        result = await self._call_agent("backend.agents.macro", "run_macro_agent")
        self.outputs["macro_brief"] = result.get("macro_brief")
        self.agents["M"] = AgentStatus.DONE
        await self._emit("M", "done", f"Updated macro brief (update #{self.m_update_count})")
        self.phase = Phase.PLANNING

    def _get_context(self) -> dict:
        return {
            "phase": self.phase.value,
            "budget": self.budget,
            "purchase_date": self.purchase_date,
            "m_update_count": self.m_update_count,
            "m_update_changelog": self.m_update_changelog,
            "research_cache": self.research_cache,
            "critique_history": self.critique_history,
            "outputs": self.outputs,
        }

    # ── Resume support ────────────────────────────────────────────

    @classmethod
    def from_run_folder(cls, folder_path: str) -> "Orchestrator":
        """Rebuild an orchestrator from a saved run folder and return it ready
        to resume from the last completed phase."""
        from backend.run_logger import load_run_folder
        data = load_run_folder(folder_path)

        meta = data["meta"]
        orch = cls(
            budget=meta.get("budget", "1000000"),
            purchase_date=meta.get("purchase_date", ""),
            run_id=meta.get("run_id", "resume"),
        )

        # Restore state from saved calls, rebuilding outputs, research_cache,
        # portfolio_draft (including B's revision during tiebreak), and critique_history.
        critique_history = []  # list of (round_num, critique_dict, revision_dict)

        for call in data.get("calls", []):
            parsed = call.get("parsed_result", {})
            phase = call.get("phase", "")
            agent = call.get("agent", "")

            if phase == "macro" and agent == "M":
                orch.outputs["macro_brief"] = parsed.get("macro_brief")
            elif phase == "planning" and agent == "B":
                orch.outputs["research_tasks"] = parsed.get("research_tasks", [])
            elif phase == "research" and "X" in agent:
                topic = parsed.get("output_key", call.get("user_message", "")[:20])
                orch.research_cache[topic] = parsed.get("candidates", [])
            elif phase == "draft" and agent == "B":
                orch.outputs["portfolio_draft"] = parsed.get("portfolio_draft")
            elif phase in ("critique_1", "critique_2", "critique_3"):
                round_num = int(phase.split("_")[1])
                if agent == "C":
                    orch.outputs[phase] = parsed
                    critique_history.append([round_num, parsed, {}])
                elif agent == "B":
                    # This is B's revision after C's critique — attach to last entry
                    if critique_history and critique_history[-1][0] == round_num:
                        critique_history[-1][2] = parsed
                    else:
                        critique_history.append([round_num, {}, parsed])
                    # Update portfolio_draft from the latest B revision
                    orch.outputs["portfolio_draft"] = parsed.get("portfolio_draft")
            elif phase == "tiebreak" and agent == "D":
                orch.outputs["tiebreak_verdict"] = parsed
            elif phase == "tiebreak" and agent == "B":
                # B's revision after D verdict — update portfolio_draft
                orch.outputs["portfolio_draft"] = parsed.get("portfolio_draft")

        orch.m_update_count = len(data.get("m_updates", []))
        orch.m_update_changelog = data.get("m_updates", [])

        # Restore critique_history as list of (round_num, critique, revision) tuples
        orch.critique_history = [(r, c, rev) for r, c, rev in critique_history]

        # Determine next phase
        last_phase = data.get("last_phase", "macro")
        phase_map = {
            "macro": Phase.MACRO,
            "planning": Phase.PLANNING,
            "research": Phase.RESEARCH,
            "draft": Phase.DRAFT,
            "critique_1": Phase.CRITIQUE_1,
            "critique_2": Phase.CRITIQUE_2,
            "critique_3": Phase.CRITIQUE_3,
            "tiebreak": Phase.TIEBREAK,
            "final": Phase.MACRO,
        }
        next_phase_map = {
            "macro": Phase.PLANNING,
            "planning": Phase.RESEARCH,
            "research": Phase.DRAFT,
            "draft": Phase.CRITIQUE_1,
            "critique_1": Phase.CRITIQUE_2,
            "critique_2": Phase.CRITIQUE_3,
            "critique_3": Phase.TIEBREAK,
            "tiebreak": Phase.FINAL,
        }

        if last_phase and last_phase in next_phase_map:
            orch.phase = next_phase_map[last_phase]
        else:
            orch.phase = Phase.MACRO

        logger.info(f"Resumed run from {folder_path} — next phase: {orch.phase.value}")
        return orch

    # ── Main run loop ───────────────────────────────────────────────

    async def run(self):
        """Execute the full agent pipeline."""
        # Install the retry-hook so call_llm can emit SSE events on throttling retries
        from backend.agents._base import set_retry_hook
        set_retry_hook(self._emit_retry_event)

        phase_handlers = {
            Phase.MACRO: self._phase_macro,
            Phase.PLANNING: self._phase_planning,
            Phase.RESEARCH: self._phase_research,
            Phase.DRAFT: self._phase_draft,
            Phase.CRITIQUE_1: lambda: self._phase_critique(1),
            Phase.CRITIQUE_2: lambda: self._phase_critique(2),
            Phase.CRITIQUE_3: lambda: self._phase_critique(3),
            Phase.TIEBREAK: self._phase_tiebreak,
            Phase.FINAL: self._phase_final,
        }

        await self._emit("A", "working", f"Starting run: budget=¥{self.budget}, date={self.purchase_date}")

        while True:
            handler = phase_handlers.get(self.phase)
            if handler is None:
                raise RuntimeError(f"No handler for phase {self.phase}")
            try:
                await handler()
            except Exception as e:
                logger.exception(f"Phase {self.phase} failed")
                await self._emit("A", "error", f"Phase {self.phase} failed: {e}")
                raise
            if self.phase == Phase.FINAL:
                break

        return self.outputs["portfolio_final"]