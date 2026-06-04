"""Shared fixtures and mock data for all tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_openai_client():
    """Return an AsyncMock OpenAI client that returns a valid chat completion.

    The returned message.content is set in each test via
    mock_openai_client.chat.completions.create.return_value.choices[0].message.content = "..."
    """
    client = AsyncMock()
    # Default: return a simple JSON response
    mock_choice = MagicMock()
    mock_choice.message.content = '{"status": "done", "agent": "test"}'
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    client.chat.completions.create = AsyncMock(return_value=mock_response)
    return client


@pytest.fixture
def sample_macro_brief():
    return {
        "fed_policy": "Fed holding rates at 5.25-5.50%, expecting 2 cuts in H2 2026",
        "boj_policy": "BOJ normalizing, policy rate at 0.50%, further hikes expected",
        "usd_jpy_outlook": "Range 140-150 over 12 months, gradual JPY strengthening",
        "us_japan_weight_rationale": "60% US / 40% Japan — US growth edge offsets FX risk",
        "sector_tailwinds": ["US Technology", "Japan Financials"],
        "sector_headwinds": ["US Real Estate", "Japan Utilities"],
    }


@pytest.fixture
def sample_portfolio_draft():
    return {
        "fx_rate": "145.0",
        "holdings": [
            {
                "ticker": "NVDA",
                "name": "NVIDIA Corporation",
                "industry": "Technology",
                "thesis": "AI leader benefiting from multi-year capex cycle",
                "allocation_pct": 20.0,
                "allocation_jpy": 200000,
                "confidence": "high",
                "base_return_pct": 100.0,
                "bear_downside_pct": -20.0,
                "score": 64.0,
            }
        ],
        "total_allocated_pct": 100.0,
    }


@pytest.fixture
def sample_research_brief():
    return {
        "topic": "us_semiconductors",
        "industry": "Technology",
        "sub_industry": "Semiconductors",
        "geography": "US",
        "focus": "AI-driven growth in GPU and custom silicon",
        "budget_target_pct": 20,
    }


@pytest.fixture
def sample_critique_history():
    return [
        (
            1,
            {"critique": "Too concentrated in NVDA at 25%", "killer_argument": "NVDA concentration risk"},
            {"portfolio_draft": {"holdings": [{"ticker": "NVDA", "allocation_pct": 15}]}},
        )
    ]


@pytest.fixture
def orchestrator_context():
    """Minimal context dict as built by Orchestrator._get_context()."""
    return {
        "phase": "planning",
        "budget": "1000000",
        "purchase_date": "2026-06-09",
        "m_update_count": 0,
        "m_update_changelog": [],
        "research_cache": {},
        "critique_history": [],
        "outputs": {
            "macro_brief": None,
            "research_tasks": None,
            "portfolio_draft": None,
            "critique_1": None,
            "critique_2": None,
            "critique_3": None,
            "tiebreak_verdict": None,
            "portfolio_final": None,
        },
    }