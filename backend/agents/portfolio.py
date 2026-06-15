"""Agent B — Portfolio Manager.
Dispatches internally based on the current phase from context.
"""

import json
import logging
import hashlib
from pathlib import Path

from backend.agents._base import build_agent_prompt, call_llm, extract_json

logger = logging.getLogger(__name__)

# Load curated research themes from project root
_RESEARCH_THEMES_PATH = Path(__file__).resolve().parent.parent.parent / "research-structure.md"
try:
    RESEARCH_THEMES = _RESEARCH_THEMES_PATH.read_text(encoding="utf-8")
except Exception:
    RESEARCH_THEMES = ""
    logger.warning("Could not load research-structure.md — B will generate tasks from scratch")

TASK_PLAN_FORMAT = {
    "agent": "B", "status": "done",
    "research_tasks": [{"topic": "us_semiconductors", "industry": "Technology",
                        "focus": "AI-driven growth", "budget_target_pct": 20}],
    "fx_rate": "145.0",
    "constraints": ["no single ticker > 25%", "at least 3 industries"],
    "m_update_signal": {"triggered": False, "reason": None},
}

PORTFOLIO_FORMAT = {
    "agent": "B", "status": "done",
    "portfolio_draft": {"fx_rate": "145.0", "holdings": [
        {"ticker": "NVDA", "name": "NVIDIA", "allocation_pct": 15.0, "confidence": "high",
         "base_return_pct": 120.0, "bear_downside_pct": -30.0, "score": 75.0}],
        "total_allocated_pct": 100.0},
    "m_update_signal": {"triggered": False, "reason": None},
}

REVISION_FORMAT = {
    "agent": "B", "status": "done",
    "portfolio_draft": {"fx_rate": "145.0", "holdings": [...], "total_allocated_pct": 100.0,
                        "revision_notes": "Reduced NVDA from 25% to 15% per critique"},
    "m_update_signal": {"triggered": False, "reason": None},
}

PLAN_REVIEW_FORMAT = {
    "agent": "B", "status": "done", "approved": True, "feedback": None,
    "m_update_signal": {"triggered": False, "reason": None},
}


async def run_portfolio_agent(openai_client, model: str, macro_brief: dict, context: dict) -> dict:
    phase = context.get("phase", "")
    if phase in ("planning",):
        return await _define_research_tasks(openai_client, model, macro_brief, context)
    elif phase in ("draft",):
        return await _construct_draft(openai_client, model, macro_brief, context)
    elif phase in ("critique_1", "critique_2", "critique_3", "tiebreak"):
        return await _revise_portfolio(openai_client, model, macro_brief, context)
    else:
        return await _define_research_tasks(openai_client, model, macro_brief, context)


async def review_research_plan(openai_client, model: str, plan: dict, existing_coverage: list) -> dict:
    context_data = {"plan": plan, "existing_coverage": existing_coverage}
    system_prompt = build_agent_prompt(
        role="Portfolio Manager (Plan Reviewer)", context=context_data,
        instructions="Review this research plan. Approve if scoped well, reject with feedback if overlapping or vague.",
        output_format=PLAN_REVIEW_FORMAT,
    )
    user_msg = "Please review this research plan."
    response_text = await call_llm(openai_client, model, system_prompt, user_msg, temperature=0.2)
    result = extract_json(response_text)

    default = {"agent": "B", "status": "done", "approved": True, "feedback": None,
               "m_update_signal": {"triggered": False, "reason": None},
               "_prompt": system_prompt, "_user_message": user_msg, "_response_text": response_text}
    if not result:
        return default
    return {**default, "approved": result.get("approved", True), "feedback": result.get("feedback"),
            "m_update_signal": result.get("m_update_signal", {"triggered": False, "reason": None})}


async def _define_research_tasks(openai_client, model: str, macro_brief: dict, context: dict) -> dict:
    context_data = {
        "macro_brief": macro_brief,
        "m_update_count": context.get("m_update_count", 0),
        "existing_research_cache": list(context.get("research_cache", {}).keys()),
        "available_themes": RESEARCH_THEMES,
    }
    system_prompt = build_agent_prompt(
        role="Portfolio Manager (Research Planner)", context=context_data,
        instructions=(
            "Review the available research themes in 'available_themes'. "
            "Select 8-12 themes that best fit the macro brief, adapting each theme's "
            "focus as needed (e.g. adjust screening thresholds, add/remove examples). "
            "Distribute budget percentages across selected themes — sum must equal 100. "
            "Cover a mix of US and Japan themes based on the macro brief's allocation rationale. "
            "Declare a single USD/JPY FX rate."
        ),
        output_format=TASK_PLAN_FORMAT,
    )
    user_msg = f"Given the macro briefing, define research tasks for a JPY {context.get('budget', 'unknown')} portfolio with a 5-year horizon."
    response_text = await call_llm(openai_client, model, system_prompt, user_msg, temperature=0.4)
    result = extract_json(response_text)

    base = {"_prompt": system_prompt, "_user_message": user_msg, "_response_text": response_text,
            "_detail": {"tasks": result.get("research_tasks") if result else _default_tasks(),
                        "fx_rate": result.get("fx_rate") if result else "145.0"}}

    if not result:
        return {"agent": "B", "status": "done", "research_tasks": _default_tasks(), "fx_rate": "145.0",
                "constraints": ["no single ticker > 25%", "at least 3 industries"],
                "m_update_signal": {"triggered": False, "reason": None}, **base}
    return {"agent": "B", "status": "done",
            "research_tasks": result.get("research_tasks", _default_tasks()),
            "fx_rate": result.get("fx_rate", "145.0"),
            "constraints": result.get("constraints", []),
            "m_update_signal": result.get("m_update_signal", {"triggered": False, "reason": None}),
            **base}


async def _construct_draft(openai_client, model: str, macro_brief: dict, context: dict) -> dict:
    all_candidates = context.get("outputs", {}).get("research_deduped", [])
    context_data = {"macro_brief": macro_brief, "candidates": all_candidates}
    system_prompt = build_agent_prompt(
        role="Portfolio Manager (Constructor)", context=context_data,
        instructions=(
            "Score each candidate using: Score = (base_return x confidence_weight) - (bear_downside x (1 - confidence_weight)). "
            "High=0.7, Med=0.5, Low=0.3. Allocate proportionally."
        ),
        output_format=PORTFOLIO_FORMAT,
    )
    user_msg = "Construct the portfolio from the research candidates."
    response_text = await call_llm(openai_client, model, system_prompt, user_msg, temperature=0.3)
    result = extract_json(response_text)

    base = {"_prompt": system_prompt, "_user_message": user_msg, "_response_text": response_text}

    fallback = {"fx_rate": "145.0", "holdings": [], "total_allocated_pct": 0}
    if not result or "portfolio_draft" not in result or not isinstance(result["portfolio_draft"], dict):
        return {"agent": "B", "status": "done", "portfolio_draft": fallback,
                "m_update_signal": {"triggered": False, "reason": None},
                **base, "_detail": fallback}

    draft = result["portfolio_draft"]
    return {"agent": "B", "status": "done", "portfolio_draft": draft,
            "m_update_signal": result.get("m_update_signal", {"triggered": False, "reason": None}),
            **base, "_detail": draft}


async def _revise_portfolio(openai_client, model: str, macro_brief: dict, context: dict) -> dict:
    current_draft = context.get("outputs", {}).get("portfolio_draft", {})
    context_data = {
        "macro_brief": macro_brief,
        "current_portfolio": current_draft,
        "critique_history": context.get("critique_history", []),
        "round_number": len(context.get("critique_history", [])) + 1,
    }
    system_prompt = build_agent_prompt(
        role="Portfolio Manager (Revision)", context=context_data,
        instructions="Address each critique with explicit reasoning. Show what changed and why.",
        output_format=REVISION_FORMAT,
    )
    round_num = len(context.get("critique_history", [])) + 1
    user_msg = f"Revise the portfolio in response to Critique Round {round_num}."
    response_text = await call_llm(openai_client, model, system_prompt, user_msg, temperature=0.3)
    result = extract_json(response_text)

    base = {"_prompt": system_prompt, "_user_message": user_msg, "_response_text": response_text}

    if not result or "portfolio_draft" not in result or not isinstance(result["portfolio_draft"], dict):
        return {"agent": "B", "status": "done", "portfolio_draft": current_draft,
                "m_update_signal": {"triggered": False, "reason": None}, **base}

    draft = result["portfolio_draft"]
    if "revision_notes" not in draft:
        draft["revision_notes"] = f"Revised after critique round {round_num}"
    return {"agent": "B", "status": "done", "portfolio_draft": draft,
            "m_update_signal": result.get("m_update_signal", {"triggered": False, "reason": None}),
            **base, "_detail": draft}


def _default_tasks() -> list:
    return [
        {"topic": "us_semiconductors", "industry": "Technology", "sub_industry": "Semiconductors",
         "geography": "US", "focus": "AI-driven semiconductor leaders", "budget_target_pct": 20},
        {"topic": "us_large_cap_growth", "industry": "Technology", "sub_industry": "Large Cap Growth",
         "geography": "US", "focus": "Mega-cap tech with durable advantages", "budget_target_pct": 15},
        {"topic": "us_healthcare", "industry": "Healthcare", "sub_industry": "Pharma",
         "geography": "US", "focus": "Large-cap pharma with strong pipelines", "budget_target_pct": 10},
        {"topic": "japan_industrials", "industry": "Industrials", "sub_industry": "Manufacturing",
         "geography": "Japan", "focus": "TSE-listed global automation leaders", "budget_target_pct": 20},
        {"topic": "japan_financials", "industry": "Financials", "sub_industry": "Banking",
         "geography": "Japan", "focus": "Japanese banks benefiting from BOJ normalization", "budget_target_pct": 15},
        {"topic": "japan_consumer", "industry": "Consumer Defensive", "sub_industry": "Household",
         "geography": "Japan", "focus": "Defensive consumer staples with pricing power", "budget_target_pct": 20},
    ]