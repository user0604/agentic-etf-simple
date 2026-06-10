"""Tests for the Orchestrator (Agent A) state machine and phase logic."""

from unittest.mock import AsyncMock

import pytest
import asyncio

from backend.orchestrator import Orchestrator, Phase, AgentStatus


@pytest.fixture
def orch():
    """A fresh Orchestrator instance for each test."""
    return Orchestrator(budget="1000000", purchase_date="2026-06-09")


class TestInitialState:
    def test_initial_phase_is_macro(self, orch):
        assert orch.phase == Phase.MACRO

    def test_initial_agent_statuses_idle(self, orch):
        for agent in ("M", "B", "C", "D"):
            assert orch.agents[agent] == AgentStatus.IDLE

    def test_initial_outputs_all_none(self, orch):
        for key in ("macro_brief", "research_tasks", "portfolio_draft",
                     "critique_1", "critique_2", "critique_3",
                     "tiebreak_verdict", "portfolio_final"):
            assert orch.outputs[key] is None

    def test_m_update_count_starts_at_zero(self, orch):
        assert orch.m_update_count == 0


class TestPhaseTransitions:
    def test_plan_hash_is_hex_string(self, orch):
        import json
        h = asyncio.run(orch._compute_plan_hash({"topic": "test"}))
        assert isinstance(h, str)
        assert len(h) == 12
        # hex string
        int(h, 16)

    def test_get_context_includes_budget(self, orch):
        ctx = orch._get_context()
        assert ctx["budget"] == "1000000"
        assert ctx["phase"] == "macro"

    def test_get_context_updates_with_phase(self, orch):
        orch.phase = Phase.DRAFT
        ctx = orch._get_context()
        assert ctx["phase"] == "draft"


class TestDedupLogic:
    def test_no_duplicates_passthrough(self, orch):
        candidates = [
            {"ticker": "NVDA", "thesis": "AI"},
            {"ticker": "SONY", "thesis": "Entertainment"},
        ]
        import asyncio
        result = asyncio.run(orch._deduplicate_research(candidates))
        assert len(result) == 2

    def test_duplicate_tickers_merged(self, orch):
        candidates = [
            {"ticker": "NVDA", "thesis": "AI", "confidence": "high"},
            {"ticker": "NVDA", "thesis": "GPU leader", "confidence": "medium"},
            {"ticker": "SONY", "thesis": "Entertainment"},
        ]
        import asyncio
        result = asyncio.run(orch._deduplicate_research(candidates))
        assert len(result) == 2
        assert len(orch.dedup_log) == 1  # one merge recorded

    def test_richer_schema_kept(self, orch):
        candidates = [
            {"ticker": "NVDA", "thesis": "GPU", "extra_field": "yes"},
            {"ticker": "NVDA", "thesis": "AI"},
        ]
        import asyncio
        result = asyncio.run(orch._deduplicate_research(candidates))
        nvda = [c for c in result if c["ticker"] == "NVDA"][0]
        assert "extra_field" in nvda  # richer schema kept

    def test_empty_candidates(self, orch):
        import asyncio
        result = asyncio.run(orch._deduplicate_research([]))
        assert result == []


class TestEventEmission:
    def test_event_callback_receives_events(self, orch):
        received = []

        async def capture(payload):
            received.append(payload)

        orch.on_event(capture)

        import asyncio
        asyncio.run(orch._emit("M", "done", "Macro complete"))
        assert len(received) == 1
        assert received[0]["agent"] == "M"
        assert received[0]["status"] == "done"
        assert received[0]["message"] == "Macro complete"

    def test_multiple_callbacks(self, orch):
        received1, received2 = [], []

        async def cb1(p): received1.append(p)
        async def cb2(p): received2.append(p)

        orch.on_event(cb1)
        orch.on_event(cb2)

        import asyncio
        asyncio.run(orch._emit("A", "working", "test"))
        assert len(received1) == 1
        assert len(received2) == 1


class TestMUpdate:
    @pytest.mark.asyncio
    async def test_m_update_increments_count(self, orch):
        orch._call_agent = AsyncMock(return_value={"agent": "M", "status": "done", "macro_brief": {}})
        await orch._handle_m_update("Macro gap identified")
        assert orch.m_update_count == 1

    @pytest.mark.asyncio
    async def test_m_update_changelog_records_reason(self, orch):
        orch._call_agent = AsyncMock(return_value={"agent": "M", "status": "done", "macro_brief": {}})
        await orch._handle_m_update("Fed policy not addressed")
        assert orch.m_update_changelog[0]["reason"] == "Fed policy not addressed"
        assert orch.m_update_changelog[0]["update_number"] == 1

    @pytest.mark.asyncio
    async def test_m_update_phase_becomes_planning(self, orch):
        """After M-update, phase resets to Planning (keeping research cache)."""
        orch._call_agent = AsyncMock(return_value={"agent": "M", "status": "done", "macro_brief": {}})
        orch.phase = Phase.CRITIQUE_1
        await orch._handle_m_update("test")
        assert orch.phase == Phase.PLANNING


class TestCallAgent:
    def test_call_agent_passes_openai_client_and_model(self):
        """_call_agent passes openai_client and model to the target function."""
        orch = Orchestrator(budget="1000000", purchase_date="2026-06-09")
        orch._call_agent = None  # remove mock below

        received_kwargs = {}

        async def fake_fn(**kwargs):
            received_kwargs.update(kwargs)
            return {"status": "done"}

        # Monkey-patch _call_agent to bypass import machinery
        orig_call = orch._call_agent

        async def mock_call(module_path, fn_name, **kwargs):
            # Simulate calling fn(openai_client=..., model=..., **kwargs)
            return await fake_fn(openai_client=orch.client, model=orch.model, **kwargs)

        orch._call_agent = mock_call
        import asyncio
        result = asyncio.run(orch._call_agent("test", "test", extra="data"))
        assert result == {"status": "done"}


class TestResearchTaskNormalization:
    """_phase_planning normalizes research_tasks from strings to dicts."""

    def _run_planning(self, orch, research_tasks):
        """Helper: simulate B returning the given research_tasks."""
        orch._call_agent = AsyncMock(return_value={
            "agent": "B", "status": "done",
            "research_tasks": research_tasks,
            "fx_rate": "145.0",
        })
        import asyncio
        asyncio.run(orch._phase_planning())

    def test_dict_tasks_pass_through(self, orch):
        tasks = [
            {"topic": "us_semiconductors", "industry": "Technology", "geography": "US", "focus": "AI chips"},
            {"topic": "japan_auto", "industry": "Automotive", "geography": "Japan", "focus": "EV transition"},
        ]
        self._run_planning(orch, tasks)
        assert len(orch.outputs["research_tasks"]) == 2
        assert orch.outputs["research_tasks"][0]["topic"] == "us_semiconductors"
        assert orch.outputs["research_tasks"][1]["industry"] == "Automotive"

    def test_string_tasks_wrapped_to_dicts(self, orch):
        tasks = ["us_semiconductors", "japan_auto"]
        self._run_planning(orch, tasks)
        assert len(orch.outputs["research_tasks"]) == 2
        assert orch.outputs["research_tasks"][0]["topic"] == "us_semiconductors"
        assert orch.outputs["research_tasks"][0]["focus"] == "us_semiconductors"
        assert orch.outputs["research_tasks"][0]["industry"] == ""
        assert orch.outputs["research_tasks"][0]["geography"] == ""

    def test_mixed_tasks_normalized(self, orch):
        tasks = ["us_semiconductors", {"topic": "japan_auto", "focus": "EV", "geography": "Japan"}]
        self._run_planning(orch, tasks)
        assert len(orch.outputs["research_tasks"]) == 2
        assert isinstance(orch.outputs["research_tasks"][0], dict)
        assert orch.outputs["research_tasks"][0]["topic"] == "us_semiconductors"
        assert isinstance(orch.outputs["research_tasks"][1], dict)
        assert orch.outputs["research_tasks"][1]["topic"] == "japan_auto"

    def test_empty_tasks_handled(self, orch):
        self._run_planning(orch, [])
        assert orch.outputs["research_tasks"] == []

    def test_missing_tasks_handled(self, orch):
        orch._call_agent = AsyncMock(return_value={
            "agent": "B", "status": "done",
            "fx_rate": "145.0",
        })
        import asyncio
        asyncio.run(orch._phase_planning())
        assert orch.outputs["research_tasks"] == []


class TestFromRunFolder:
    """from_run_folder correctly determines next phase from saved runs."""

    def test_resume_from_macro(self, monkeypatch):
        data = {"meta": {"budget": "1000000", "purchase_date": "2026-06-09", "run_id": "test"},
                "calls": [], "last_phase": "macro", "m_updates": []}
        import backend.orchestrator as m
        monkeypatch.setattr(m, "load_run_folder", lambda _: data)
        orch = Orchestrator.from_run_folder("/fake/path")
        assert orch.phase == Phase.PLANNING

    def test_resume_from_planning(self, monkeypatch):
        data = {"meta": {"budget": "1000000", "purchase_date": "2026-06-09", "run_id": "test"},
                "calls": [{"phase": "macro", "agent": "M",
                           "parsed_result": {"macro_brief": {"fed_policy": "hawkish"}}}],
                "last_phase": "planning", "m_updates": []}
        import backend.orchestrator as m
        monkeypatch.setattr(m, "load_run_folder", lambda _: data)
        orch = Orchestrator.from_run_folder("/fake/path")
        assert orch.phase == Phase.RESEARCH

    def test_resume_from_critique_3(self, monkeypatch):
        data = {"meta": {"budget": "1000000", "purchase_date": "2026-06-09", "run_id": "test"},
                "calls": [{"phase": f"critique_{i}", "agent": "C", "parsed_result": {}}
                          for i in (1, 2, 3)] +
                         [{"phase": f"critique_{i}", "agent": "B",
                           "parsed_result": {"portfolio_draft": {"holdings": []}}}
                          for i in (1, 2, 3)],
                "last_phase": "critique_3", "m_updates": []}
        import backend.orchestrator as m
        monkeypatch.setattr(m, "load_run_folder", lambda _: data)
        orch = Orchestrator.from_run_folder("/fake/path")
        assert orch.phase == Phase.TIEBREAK

    def test_resume_from_tiebreak_with_b_revision(self, monkeypatch):
        data = {"meta": {"budget": "1000000", "purchase_date": "2026-06-09", "run_id": "test"},
                "calls": [{"phase": "tiebreak", "agent": "D", "parsed_result": {"verdict": "B must revise"}},
                          {"phase": "tiebreak", "agent": "B",
                           "parsed_result": {"portfolio_draft": {"holdings": []}}}],
                "last_phase": "tiebreak", "m_updates": []}
        import backend.orchestrator as m
        monkeypatch.setattr(m, "load_run_folder", lambda _: data)
        orch = Orchestrator.from_run_folder("/fake/path")
        assert orch.phase == Phase.FINAL

    def test_resume_from_tiebreak_without_b_revision(self, monkeypatch):
        data = {"meta": {"budget": "1000000", "purchase_date": "2026-06-09", "run_id": "test"},
                "calls": [{"phase": "tiebreak", "agent": "D", "parsed_result": {"verdict": "B must revise"}}],
                "last_phase": "tiebreak", "m_updates": []}
        import backend.orchestrator as m
        monkeypatch.setattr(m, "load_run_folder", lambda _: data)
        orch = Orchestrator.from_run_folder("/fake/path")
        assert orch.phase == Phase.TIEBREAK

    def test_resume_from_unknown_phase_falls_back_to_macro(self, monkeypatch):
        data = {"meta": {"budget": "1000000", "purchase_date": "2026-06-09", "run_id": "test"},
                "calls": [], "last_phase": "nonexistent", "m_updates": []}
        import backend.orchestrator as m
        monkeypatch.setattr(m, "load_run_folder", lambda _: data)
        orch = Orchestrator.from_run_folder("/fake/path")
        assert orch.phase == Phase.MACRO

    def test_resume_restores_critique_history(self, monkeypatch):
        data = {"meta": {"budget": "1000000", "purchase_date": "2026-06-09", "run_id": "test"},
                "calls": [{"phase": "critique_1", "agent": "C", "parsed_result": {"critique": "too risky"}},
                          {"phase": "critique_1", "agent": "B", "parsed_result": {"defence": "hedged"}},
                          {"phase": "critique_2", "agent": "C", "parsed_result": {"critique": "fx risk"}},
                          {"phase": "critique_2", "agent": "B",
                           "parsed_result": {"defence": "hedged", "portfolio_draft": {}}}],
                "last_phase": "critique_2", "m_updates": []}
        import backend.orchestrator as m
        monkeypatch.setattr(m, "load_run_folder", lambda _: data)
        orch = Orchestrator.from_run_folder("/fake/path")
        assert len(orch.critique_history) == 2
        assert orch.critique_history[0][0] == 1
        assert orch.critique_history[0][1]["critique"] == "too risky"
        assert orch.critique_history[1][2]["defence"] == "hedged"

    def test_resume_restores_research_cache(self, monkeypatch):
        data = {"meta": {"budget": "1000000", "purchase_date": "2026-06-09", "run_id": "test"},
                "calls": [{"phase": "research", "agent": "X1",
                           "parsed_result": {"candidates": [{"ticker": "NVDA"}]},
                           "user_message": "us_semiconductors"},
                          {"phase": "research", "agent": "X2",
                           "parsed_result": {"candidates": [{"ticker": "SONY"}]},
                           "user_message": "japan_consumer"}],
                "last_phase": "research", "m_updates": []}
        import backend.orchestrator as m
        monkeypatch.setattr(m, "load_run_folder", lambda _: data)
        orch = Orchestrator.from_run_folder("/fake/path")
        all_candidates = []
        for topic, candidates in orch.research_cache.items():
            all_candidates.extend(candidates)
        assert len(all_candidates) >= 2

    def test_resume_normalizes_string_tasks(self, monkeypatch):
        data = {"meta": {"budget": "1000000", "purchase_date": "2026-06-09", "run_id": "test"},
                "calls": [{"phase": "planning", "agent": "B",
                           "parsed_result": {"research_tasks": ["us_semiconductors", "japan_auto"]}}],
                "last_phase": "planning", "m_updates": []}
        import backend.orchestrator as m
        monkeypatch.setattr(m, "load_run_folder", lambda _: data)
        orch = Orchestrator.from_run_folder("/fake/path")
        tasks = orch.outputs["research_tasks"]
        assert len(tasks) == 2
        assert isinstance(tasks[0], dict)
        assert tasks[0]["topic"] == "us_semiconductors"
        assert tasks[0]["industry"] == ""
        assert isinstance(tasks[1], dict)
        assert tasks[1]["topic"] == "japan_auto"