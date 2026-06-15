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
    """Tests for research task string-to-dict normalization."""

    def test_research_tasks_already_dict(self):
        """Dict-formatted tasks pass through unchanged."""
        orch = Orchestrator(budget="1000000", purchase_date="2026-06-09")
        tasks = [
            {"topic": "US-01", "industry": "Tech", "focus": "AI", "budget_target_pct": 30},
            {"topic": "JP-01", "industry": "Finance", "focus": "Banks", "budget_target_pct": 20},
        ]
        result = orch._normalize_research_tasks(tasks)
        assert result == tasks
        assert all(isinstance(t, dict) for t in result)

    def test_research_tasks_string_values(self):
        """String-formatted tasks normalize to dict."""
        orch = Orchestrator(budget="1000000", purchase_date="2026-06-09")
        tasks = [
            "topic: US-01, industry: Tech, focus: AI, budget: 30",
            "topic: JP-01, industry: Finance, focus: Banks, budget: 20",
        ]
        result = orch._normalize_research_tasks(tasks)
        assert all(isinstance(t, dict) for t in result)
        assert result[0]["topic"] == "US-01"
        assert result[1]["budget_target_pct"] == 20

    def test_research_tasks_mixed(self):
        """Mixed list of dicts and strings normalizes correctly."""
        orch = Orchestrator(budget="1000000", purchase_date="2026-06-09")
        tasks = [
            {"topic": "US-01", "industry": "Tech", "budget_target_pct": 30},
            "topic: JP-01, industry: Finance, budget: 20",
        ]
        result = orch._normalize_research_tasks(tasks)
        assert all(isinstance(t, dict) for t in result)
        assert result[0]["topic"] == "US-01"
        assert result[1]["topic"] == "JP-01"

    def test_research_tasks_none_values(self):
        """None topic handled gracefully."""
        orch = Orchestrator(budget="1000000", purchase_date="2026-06-09")
        tasks = [None, "", {"topic": "US-01", "industry": "Tech", "budget_target_pct": 30}]
        result = orch._normalize_research_tasks(tasks)
        assert len(result) == 3

    def test_research_tasks_empty_list(self):
        """Empty list returns empty."""
        orch = Orchestrator(budget="1000000", purchase_date="2026-06-09")
        result = orch._normalize_research_tasks([])
        assert result == []

    def test_research_tasks_preserves_all_fields(self):
        """All fields preserved after normalization."""
        orch = Orchestrator(budget="1000000", purchase_date="2026-06-09")
        tasks = [{
            "topic": "US-01",
            "industry": "Technology",
            "sub_industry": "Semiconductors",
            "focus": "AI/data center GPU demand",
            "geography": "United States",
            "budget_target_pct": 25,
            "screening_criteria": ">25% YoY revenue growth",
            "examples": ["NVDA", "AMD"],
        }]
        result = orch._normalize_research_tasks(tasks)
        assert result[0]["topic"] == "US-01"
        assert result[0]["budget_target_pct"] == 25
        assert result[0]["examples"] == ["NVDA", "AMD"]


class TestFromRunFolder:
    """Tests for Orchestrator.from_run_folder resume logic."""

    def test_from_run_folder_phase_macro(self, tmp_path):
        """Resume from MACRO phase — only meta.json exists."""
        import json
        meta = {"budget": "1000000", "purchase_date": "2026-06-09", "run_id": "test123"}
        (tmp_path / "_meta.json").write_text(json.dumps(meta))
        orch = Orchestrator.from_run_folder(str(tmp_path))
        assert orch.phase == Phase.MACRO
        assert orch.budget == "1000000"
        assert orch.purchase_date == "2026-06-09"

    def test_from_run_folder_phase_planning(self, tmp_path):
        """Resume from PLANNING phase — macro JSON exists."""
        import json
        meta = {"budget": "1000000", "purchase_date": "2026-06-09", "run_id": "test123"}
        (tmp_path / "_meta.json").write_text(json.dumps(meta))
        (tmp_path / "001_A_macro.json").write_text(json.dumps({
            "agent": "M", "status": "done", "macro_brief": {"fed_policy": "test"}
        }))
        orch = Orchestrator.from_run_folder(str(tmp_path))
        assert orch.phase == Phase.PLANNING

    def test_from_run_folder_phase_research(self, tmp_path):
        """Resume from RESEARCH phase — planning JSON exists."""
        import json
        meta = {"budget": "1000000", "purchase_date": "2026-06-09", "run_id": "test123"}
        (tmp_path / "_meta.json").write_text(json.dumps(meta))
        (tmp_path / "001_A_macro.json").write_text(json.dumps({"agent": "M", "status": "done"}))
        (tmp_path / "002_A_planning.json").write_text(json.dumps({"agent": "B", "status": "done", "research_tasks": []}))
        orch = Orchestrator.from_run_folder(str(tmp_path))
        assert orch.phase == Phase.RESEARCH

    def test_from_run_folder_phase_draft(self, tmp_path):
        """Resume from DRAFT phase."""
        import json
        meta = {"budget": "1000000", "purchase_date": "2026-06-09", "run_id": "test123"}
        (tmp_path / "_meta.json").write_text(json.dumps(meta))
        (tmp_path / "001_A_macro.json").write_text(json.dumps({"agent": "M", "status": "done"}))
        (tmp_path / "002_A_planning.json").write_text(json.dumps({"agent": "B", "status": "done"}))
        (tmp_path / "003_A_research.json").write_text(json.dumps({"agent": "B", "status": "done"}))
        orch = Orchestrator.from_run_folder(str(tmp_path))
        assert orch.phase == Phase.DRAFT

    def test_from_run_folder_phase_critique(self, tmp_path):
        """Resume from CRITIQUE phase."""
        import json
        meta = {"budget": "1000000", "purchase_date": "2026-06-09", "run_id": "test123"}
        (tmp_path / "_meta.json").write_text(json.dumps(meta))
        (tmp_path / "001_A_macro.json").write_text(json.dumps({"agent": "M", "status": "done"}))
        (tmp_path / "002_A_planning.json").write_text(json.dumps({"agent": "B", "status": "done"}))
        (tmp_path / "003_A_research.json").write_text(json.dumps({"agent": "B", "status": "done"}))
        (tmp_path / "004_A_draft.json").write_text(json.dumps({"agent": "B", "status": "done"}))
        orch = Orchestrator.from_run_folder(str(tmp_path))
        assert orch.phase == Phase.CRITIQUE_1

    def test_from_run_folder_phase_tiebreak(self, tmp_path):
        """Resume from TIEBREAK phase — critique_3 done but no B revision."""
        import json
        meta = {"budget": "1000000", "purchase_date": "2026-06-09", "run_id": "test123"}
        (tmp_path / "_meta.json").write_text(json.dumps(meta))
        (tmp_path / "001_A_macro.json").write_text(json.dumps({"agent": "M", "status": "done"}))
        (tmp_path / "002_A_planning.json").write_text(json.dumps({"agent": "B", "status": "done"}))
        (tmp_path / "003_A_research.json").write_text(json.dumps({"agent": "B", "status": "done"}))
        (tmp_path / "004_A_draft.json").write_text(json.dumps({"agent": "B", "status": "done"}))
        (tmp_path / "005_A_critique_1.json").write_text(json.dumps({"agent": "C", "status": "done"}))
        (tmp_path / "006_A_critique_2.json").write_text(json.dumps({"agent": "C", "status": "done"}))
        (tmp_path / "007_A_critique_3.json").write_text(json.dumps({"agent": "C", "status": "done"}))
        orch = Orchestrator.from_run_folder(str(tmp_path))
        assert orch.phase == Phase.TIEBREAK

    def test_from_run_folder_phase_tiebreak_b_revision_done(self, tmp_path):
        """Resume from TIEBREAK with B revision done — maps to FINAL."""
        import json
        meta = {"budget": "1000000", "purchase_date": "2026-06-09", "run_id": "test123"}
        (tmp_path / "_meta.json").write_text(json.dumps(meta))
        (tmp_path / "001_A_macro.json").write_text(json.dumps({"agent": "M", "status": "done"}))
        (tmp_path / "002_A_planning.json").write_text(json.dumps({"agent": "B", "status": "done"}))
        (tmp_path / "003_A_research.json").write_text(json.dumps({"agent": "B", "status": "done"}))
        (tmp_path / "004_A_draft.json").write_text(json.dumps({"agent": "B", "status": "done"}))
        (tmp_path / "005_A_critique_1.json").write_text(json.dumps({"agent": "C", "status": "done"}))
        (tmp_path / "006_A_critique_2.json").write_text(json.dumps({"agent": "C", "status": "done"}))
        (tmp_path / "007_A_critique_3.json").write_text(json.dumps({"agent": "C", "status": "done"}))
        (tmp_path / "008_A_tiebreak.json").write_text(json.dumps({"agent": "D", "status": "done", "verdict": "revise"}))
        # B revision file exists → tiebreak sub-step complete
        (tmp_path / "009_A_tiebreak_b_revision.json").write_text(json.dumps({"agent": "B", "status": "done"}))
        orch = Orchestrator.from_run_folder(str(tmp_path))
        assert orch.phase == Phase.FINAL

    def test_from_run_folder_phase_final(self, tmp_path):
        """Resume from FINAL phase."""
        import json
        meta = {"budget": "1000000", "purchase_date": "2026-06-09", "run_id": "test123"}
        (tmp_path / "_meta.json").write_text(json.dumps(meta))
        (tmp_path / "001_A_macro.json").write_text(json.dumps({"agent": "M", "status": "done"}))
        (tmp_path / "002_A_planning.json").write_text(json.dumps({"agent": "B", "status": "done"}))
        (tmp_path / "003_A_research.json").write_text(json.dumps({"agent": "B", "status": "done"}))
        (tmp_path / "004_A_draft.json").write_text(json.dumps({"agent": "B", "status": "done"}))
        (tmp_path / "005_A_critique_1.json").write_text(json.dumps({"agent": "C", "status": "done"}))
        (tmp_path / "006_A_critique_2.json").write_text(json.dumps({"agent": "C", "status": "done"}))
        (tmp_path / "007_A_critique_3.json").write_text(json.dumps({"agent": "C", "status": "done"}))
        (tmp_path / "008_A_tiebreak.json").write_text(json.dumps({"agent": "D", "status": "done"}))
        (tmp_path / "009_A_final.json").write_text(json.dumps({"agent": "A", "status": "done"}))
        orch = Orchestrator.from_run_folder(str(tmp_path))
        assert orch.phase == Phase.FINAL

    def test_from_run_folder_nonexistent_folder(self):
        """Nonexistent folder raises FileNotFoundError."""
        import pytest
        with pytest.raises(FileNotFoundError):
            Orchestrator.from_run_folder("/nonexistent/path")