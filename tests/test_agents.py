"""Tests for agent output formats and error handling.

Verifies that each agent function returns the correct structure
with all required keys as specified in the architecture doc.
"""

import json
from unittest.mock import MagicMock

import pytest

# ── Required output keys for each agent ────────────────────────────
# (as specified in the architecture doc's communication protocol)

REQUIRED_BASE_KEYS = {"agent", "status", "m_update_signal"}
M_KEYS = REQUIRED_BASE_KEYS | {"macro_brief"}
B_KEYS = REQUIRED_BASE_KEYS | {"research_tasks", "fx_rate", "constraints"}
C_KEYS = REQUIRED_BASE_KEYS | {"round", "critique", "prior_rounds_resolved", "satisfied"}
D_KEYS = REQUIRED_BASE_KEYS | {"verdict", "reasoning", "required_change", "revising_party"}
X_KEYS = REQUIRED_BASE_KEYS | {"output_key", "plan_hash", "cache_hit", "candidates",
                                "quality_issues", "follow_up_requests"}
M_UPDATE_SIGNAL_KEYS = {"triggered", "reason"}

CANDIDATE_KEYS = {"ticker", "thesis", "confidence", "confidence_reason",
                  "bull_case", "base_case", "bear_case",
                  "bull_return_pct", "base_return_pct", "bear_downside_pct",
                  "known_catch", "catch_severity", "data_sources"}


def _set_mock_response(mock_client, response_data: dict):
    """Helper: set the mock client to return a specific JSON dict."""
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps(response_data)
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_response


def _check_status_block(result: dict):
    """Validate the common status block structure."""
    assert "agent" in result, f"Missing 'agent' in {result}"
    assert "status" in result, f"Missing 'status' in {result}"
    assert result["status"] == "done", f"Expected 'done', got {result['status']}"
    assert "m_update_signal" in result, "Missing 'm_update_signal'"
    m_sig = result["m_update_signal"]
    assert isinstance(m_sig, dict), "'m_update_signal' must be a dict"
    assert "triggered" in m_sig, "Missing 'triggered' in m_update_signal"
    assert "reason" in m_sig, "Missing 'reason' in m_update_signal"


# ── Tests ──────────────────────────────────────────────────────────

class TestAgentM_Macro:
    @pytest.mark.asyncio
    async def test_output_format(self, mock_openai_client):
        _set_mock_response(mock_openai_client, {
            "agent": "M", "status": "done",
            "macro_brief": {
                "fed_policy": "Test", "boj_policy": "Test",
                "usd_jpy_outlook": "Test", "us_japan_weight_rationale": "Test",
                "sector_tailwinds": ["Tech"], "sector_headwinds": ["Energy"],
            },
            "m_update_signal": {"triggered": False, "reason": None},
        })
        from backend.agents.macro import run_macro_agent
        result = await run_macro_agent(mock_openai_client, "test-model")
        _check_status_block(result)
        assert set(result.keys()) >= M_KEYS
        brief = result["macro_brief"]
        for key in ("fed_policy", "boj_policy", "usd_jpy_outlook", "us_japan_weight_rationale"):
            assert key in brief, f"Missing macro_brief.{key}"
        assert "sector_tailwinds" in brief
        assert "sector_headwinds" in brief

    @pytest.mark.asyncio
    async def test_graceful_fallback_on_parse_failure(self, mock_openai_client):
        """When LLM output can't be parsed, M should still return a valid structure."""
        mock_openai_client.chat.completions.create.return_value.choices[0].message.content = ""
        from backend.agents.macro import run_macro_agent
        result = await run_macro_agent(mock_openai_client, "test-model")
        _check_status_block(result)
        assert result["macro_brief"]["fed_policy"] is not None  # Error message returned

    @pytest.mark.asyncio
    async def test_m_update_signal_present(self, mock_openai_client):
        _set_mock_response(mock_openai_client, {
            "agent": "M", "status": "done",
            "macro_brief": {"fed_policy": "Test", "boj_policy": "Test",
                            "usd_jpy_outlook": "Test", "us_japan_weight_rationale": "Test",
                            "sector_tailwinds": [], "sector_headwinds": []},
            "m_update_signal": {"triggered": True, "reason": "Data revised"},
        })
        from backend.agents.macro import run_macro_agent
        result = await run_macro_agent(mock_openai_client, "test-model")
        assert result["m_update_signal"]["triggered"] is True
        assert result["m_update_signal"]["reason"] == "Data revised"


class TestAgentB_Portfolio:
    @pytest.mark.asyncio
    async def test_planning_output_format(self, mock_openai_client, sample_macro_brief, orchestrator_context):
        _set_mock_response(mock_openai_client, {
            "agent": "B", "status": "done",
            "research_tasks": [{"topic": "us_semiconductors", "industry": "Tech",
                                "focus": "AI chips", "budget_target_pct": 25}],
            "fx_rate": "145.0",
            "constraints": ["max 25% per ticker"],
            "m_update_signal": {"triggered": False, "reason": None},
        })
        from backend.agents.portfolio import run_portfolio_agent
        result = await run_portfolio_agent(
            mock_openai_client, "test-model", sample_macro_brief, orchestrator_context
        )
        _check_status_block(result)
        assert set(result.keys()) >= B_KEYS
        assert isinstance(result["research_tasks"], list)
        assert len(result["research_tasks"]) > 0
        assert result["fx_rate"] is not None

    @pytest.mark.asyncio
    async def test_default_tasks_on_parse_failure(self, mock_openai_client, sample_macro_brief, orchestrator_context):
        """When LLM fails, B should return sensible default tasks."""
        mock_openai_client.chat.completions.create.return_value.choices[0].message.content = ""
        from backend.agents.portfolio import run_portfolio_agent
        result = await run_portfolio_agent(
            mock_openai_client, "test-model", sample_macro_brief, orchestrator_context
        )
        _check_status_block(result)
        assert len(result["research_tasks"]) > 0  # default tasks populated

    @pytest.mark.asyncio
    async def test_plan_review_output(self, mock_openai_client):
        _set_mock_response(mock_openai_client, {
            "agent": "B", "status": "done",
            "approved": True,
            "feedback": None,
            "m_update_signal": {"triggered": False, "reason": None},
        })
        from backend.agents.portfolio import review_research_plan
        result = await review_research_plan(
            mock_openai_client, "test-model",
            {"plan": {"topic": "test"}}, ["existing_coverage"]
        )
        _check_status_block(result)
        assert "approved" in result
        assert result["approved"] is True


class TestAgentC_Critic:
    @pytest.mark.asyncio
    async def test_round1_output_format(self, mock_openai_client, sample_portfolio_draft, sample_macro_brief):
        _set_mock_response(mock_openai_client, {
            "agent": "C", "status": "done", "round": 1,
            "critique": "NVDA concentration is too high at 25%",
            "killer_argument": "Single stock risk exceeds portfolio guidelines",
            "prior_rounds_resolved": True,
            "satisfied": False,
            "m_update_signal": {"triggered": False, "reason": None},
        })
        from backend.agents.critic import run_critic_agent
        result = await run_critic_agent(
            mock_openai_client, "test-model",
            round_num=1, portfolio_draft=sample_portfolio_draft,
            macro_brief=sample_macro_brief, prior_rounds=[], m_update_count=0
        )
        _check_status_block(result)
        assert set(result.keys()) >= C_KEYS
        assert result["round"] == 1
        assert "prior_rounds_resolved" in result
        assert "satisfied" in result

    @pytest.mark.asyncio
    async def test_round_escalation_preserves_round_num(self, mock_openai_client, sample_portfolio_draft, sample_macro_brief):
        """Test that round numbers are correctly passed and returned."""
        from backend.agents.critic import run_critic_agent
        for rnd in (1, 2, 3):
            _set_mock_response(mock_openai_client, {
                "agent": "C", "status": "done", "round": rnd,
                "critique": f"Round {rnd} critique",
                "prior_rounds_resolved": True,
                "satisfied": False,
                "m_update_signal": {"triggered": False, "reason": None},
            })
            result = await run_critic_agent(
                mock_openai_client, "test-model",
                round_num=rnd, portfolio_draft=sample_portfolio_draft,
                macro_brief=sample_macro_brief, prior_rounds=[], m_update_count=0
            )
            assert result["round"] == rnd

    @pytest.mark.asyncio
    async def test_satisfied_signal_round3(self, mock_openai_client, sample_portfolio_draft, sample_macro_brief):
        """Round 3 with satisfied=true should trigger consensus."""
        _set_mock_response(mock_openai_client, {
            "agent": "C", "status": "done", "round": 3,
            "critique": "No more issues", "prior_rounds_resolved": True,
            "satisfied": True,
            "m_update_signal": {"triggered": False, "reason": None},
        })
        from backend.agents.critic import run_critic_agent
        result = await run_critic_agent(
            mock_openai_client, "test-model",
            round_num=3, portfolio_draft=sample_portfolio_draft,
            macro_brief=sample_macro_brief, prior_rounds=[(1, {}, {}), (2, {}, {})],
            m_update_count=0
        )
        assert result["satisfied"] is True

    @pytest.mark.asyncio
    async def test_invalid_round_number(self, mock_openai_client, sample_portfolio_draft, sample_macro_brief):
        from backend.agents.critic import run_critic_agent
        with pytest.raises(ValueError, match="Invalid round number"):
            await run_critic_agent(
                mock_openai_client, "test-model",
                round_num=4, portfolio_draft=sample_portfolio_draft,
                macro_brief=sample_macro_brief, prior_rounds=[], m_update_count=0
            )


class TestAgentD_Tiebreaker:
    @pytest.mark.asyncio
    async def test_output_format(self, mock_openai_client, sample_macro_brief):
        _set_mock_response(mock_openai_client, {
            "agent": "D", "status": "done",
            "verdict": "B revises",
            "reasoning": "C's concentration argument is stronger",
            "required_change": "Reduce NVDA to 15%",
            "revising_party": "B",
            "m_update_signal": {"triggered": False, "reason": None},
        })
        from backend.agents.tiebreaker import run_tiebreaker_agent
        result = await run_tiebreaker_agent(
            mock_openai_client, "test-model",
            b_strongest_argument="Diversification is fine",
            c_strongest_argument="Too concentrated",
            macro_brief=sample_macro_brief,
        )
        _check_status_block(result)
        assert set(result.keys()) >= D_KEYS
        assert result["verdict"] in ("B revises", "C revises", "both partially revise")

    @pytest.mark.asyncio
    async def test_fallback_on_parse_failure(self, mock_openai_client, sample_macro_brief):
        """When LLM fails, D should default to B revises."""
        mock_openai_client.chat.completions.create.return_value.choices[0].message.content = ""
        from backend.agents.tiebreaker import run_tiebreaker_agent
        result = await run_tiebreaker_agent(
            mock_openai_client, "test-model",
            b_strongest_argument="", c_strongest_argument="",
            macro_brief=sample_macro_brief,
        )
        _check_status_block(result)
        assert result["verdict"] == "B revises"  # safe default

    @pytest.mark.asyncio
    async def test_m_update_signal_from_tiebreaker(self, mock_openai_client, sample_macro_brief):
        _set_mock_response(mock_openai_client, {
            "agent": "D", "status": "done",
            "verdict": "B revises", "reasoning": "test",
            "required_change": "test", "revising_party": "B",
            "m_update_signal": {"triggered": True, "reason": "Macro data disputed"},
        })
        from backend.agents.tiebreaker import run_tiebreaker_agent
        result = await run_tiebreaker_agent(
            mock_openai_client, "test-model",
            b_strongest_argument="A", c_strongest_argument="B",
            macro_brief=sample_macro_brief,
        )
        assert result["m_update_signal"]["triggered"] is True


class TestAgentX_Researcher:
    @pytest.mark.asyncio
    async def test_research_plan_format(self, mock_openai_client, sample_research_brief):
        _set_mock_response(mock_openai_client, {
            "plan": {"topic": "us_semiconductors", "candidate_screening_criteria": "P/E < 30",
                     "intended_sources": ["web"], "approach": "Screen top 5", "estimated_candidates": 2},
        })
        from backend.agents.researcher import submit_research_plan
        result = await submit_research_plan(mock_openai_client, "test-model", sample_research_brief)
        assert "plan" in result
        assert "plan_hash" in result
        assert len(result["plan_hash"]) == 12

    @pytest.mark.asyncio
    async def test_researcher_output_format(self, mock_openai_client, sample_research_brief):
        _set_mock_response(mock_openai_client, {
            "agent": "X", "status": "done",
            "output_key": "us_semiconductors",
            "plan_hash": None, "cache_hit": False,
            "candidates": [{
                "ticker": "NVDA", "exchange": "NASDAQ",
                "name": "NVIDIA", "industry": "Tech",
                "thesis": "AI leader", "fx_rate_used": "145.0",
                "bull_case": "Growth", "bull_return_pct": 150.0,
                "base_case": "Steady", "base_return_pct": 80.0,
                "bear_case": "Recession", "bear_downside_pct": -25.0,
                "confidence": "high", "confidence_reason": "Strong moat",
                "known_catch": "Valuation", "catch_severity": "Moderate",
                "data_sources": ["web search"],
            }],
            "quality_issues": [], "follow_up_requests": [],
            "m_update_signal": {"triggered": False, "reason": None},
        })
        from backend.agents.researcher import run_researcher_agent
        result = await run_researcher_agent(mock_openai_client, "test-model", sample_research_brief)
        _check_status_block(result)
        assert set(result.keys()) >= X_KEYS
        assert len(result["candidates"]) > 0
        cand = result["candidates"][0]
        for key in ("ticker", "thesis", "confidence", "confidence_reason"):
            assert key in cand, f"Missing candidate key: {key}"

    @pytest.mark.asyncio
    async def test_graceful_empty_on_error(self, mock_openai_client, sample_research_brief):
        """Researcher should return empty candidates, not crash, when LLM fails."""
        mock_openai_client.chat.completions.create.side_effect = Exception("API down")
        from backend.agents.researcher import run_researcher_agent
        result = await run_researcher_agent(mock_openai_client, "test-model", sample_research_brief)
        _check_status_block(result)
        assert result["candidates"] == []
        assert len(result["quality_issues"]) > 0


class TestAgentSignatures:
    """Verify all agent functions accept the expected (openai_client, model, ...) signature."""

    def test_macro_signature(self):
        import inspect
        from backend.agents.macro import run_macro_agent
        sig = inspect.signature(run_macro_agent)
        params = list(sig.parameters.keys())
        assert params[0] == "openai_client"
        assert params[1] == "model"

    def test_portfolio_signature(self):
        import inspect
        from backend.agents.portfolio import run_portfolio_agent
        sig = inspect.signature(run_portfolio_agent)
        assert list(sig.parameters.keys())[:2] == ["openai_client", "model"]

    def test_critic_signature(self):
        import inspect
        from backend.agents.critic import run_critic_agent
        assert list(inspect.signature(run_critic_agent).parameters.keys())[:2] == ["openai_client", "model"]

    def test_tiebreaker_signature(self):
        import inspect
        from backend.agents.tiebreaker import run_tiebreaker_agent
        assert list(inspect.signature(run_tiebreaker_agent).parameters.keys())[:2] == ["openai_client", "model"]

    def test_researcher_signature(self):
        import inspect
        from backend.agents.researcher import run_researcher_agent
        assert list(inspect.signature(run_researcher_agent).parameters.keys())[:2] == ["openai_client", "model"]


class TestToolSignatures:
    def test_yfinance_client_has_expected_functions(self):
        from backend.tools.yfinance_client import get_price_history, get_fundamentals, search_tickers
        assert callable(get_price_history)
        assert callable(get_fundamentals)
        assert callable(search_tickers)

    def test_fred_has_expected_functions(self):
        from backend.tools.fred import get_series, get_macro_snapshot
        assert callable(get_series)
        assert callable(get_macro_snapshot)

    def test_web_search_signature(self):
        from backend.tools.web_search import web_search
        import inspect
        sig = inspect.signature(web_search)
        assert "query" in sig.parameters
        assert "max_results" in sig.parameters