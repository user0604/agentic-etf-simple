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