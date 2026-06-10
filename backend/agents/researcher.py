"""Agent X — Researcher (parametric). Two-phase: plan then execute."""

import json
import hashlib
import logging

from backend.agents._base import build_agent_prompt, call_llm, extract_json
from backend.tools.web_search import web_search
from backend.tools.motley_fool import query_motley_fool

logger = logging.getLogger(__name__)

CANDIDATE_SCHEMA = {
    "ticker": "NVDA", "exchange": "NASDAQ", "name": "NVIDIA",
    "industry": "Technology", "thesis": "2-3 sentence investment case",
    "fx_rate_used": "145.0",
    "bull_case": "What must go right", "bull_return_pct": 150.0,
    "base_case": "Most likely outcome", "base_return_pct": 80.0,
    "bear_case": "What kills the thesis", "bear_downside_pct": -25.0,
    "confidence": "medium", "confidence_reason": "Explicit justification",
    "known_catch": "Specific risk", "catch_severity": "How it narrows the bull case",
    "data_sources": ["web search"],
}

RESEARCHER_RESULT_FORMAT = {
    "agent": "X", "status": "done", "output_key": "us_semiconductors",
    "plan_hash": None, "cache_hit": False,
    "candidates": [CANDIDATE_SCHEMA],
    "quality_issues": [], "follow_up_requests": [],
    "m_update_signal": {"triggered": False, "reason": None},
}


async def submit_research_plan(openai_client, model: str, brief: dict) -> dict:
    system_prompt = build_agent_prompt(
        role=f"Equity Researcher — {brief.get('topic', 'unknown')}",
        context={"brief": brief},
        instructions="Produce a focused research plan with screening criteria, intended sources, and approach.",
        output_format={"plan": {"topic": brief.get("topic"), "candidate_screening_criteria": "...",
                                 "intended_sources": [...], "approach": "...", "estimated_candidates": 2}},
    )
    user_msg = f"Create a research plan for: {brief.get('focus', brief.get('topic'))}. Geography: {brief.get('geography')}."
    response_text = await call_llm(openai_client, model, system_prompt, user_msg, temperature=0.4)
    result = extract_json(response_text)
    plan = result.get("plan", {}) if result else {}
    plan_hash = hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()[:12]
    return {"plan": plan, "plan_hash": plan_hash,
            "_prompt": system_prompt, "_user_message": user_msg, "_response_text": response_text,
            "_detail": {"plan": plan}}


async def run_researcher_agent(openai_client, model: str, brief: dict, plan_hash: str = None) -> dict:
    try:
        topic = brief.get("topic", "unknown")
        geography = brief.get("geography", "")
        focus = brief.get("focus", "")

        search_queries = [
            f"best {focus} stocks {geography} publicly traded companies",
            f"top {topic} companies {geography} stock market",
            f"{focus} investment thesis 5 year outlook",
        ]
        search_results = {}
        for q in search_queries:
            try:
                search_results[q] = await web_search(q, max_results=5)
            except Exception as e:
                logger.warning(f"Research search failed: {e}")
                search_results[q] = []

        # Supplement with Motley Fool corpus (local, no rate limits)
        motley_fool_results = {}
        try:
            mf_results = await query_motley_fool(focus, top_k=5)
            if mf_results:
                motley_fool_results["broad"] = mf_results
        except Exception as e:
            logger.warning(f"Motley Fool query failed: {e}")

        context_data = {"brief": brief, "web_search_results": search_results,
                        "motley_fool_results": motley_fool_results}
        system_prompt = build_agent_prompt(
            role=f"Equity Researcher — {topic}", context=context_data,
            instructions=(
                "Search for 1-2 top candidates. For each, provide ticker, exchange, thesis, "
                "bull/base/bear scenarios with % estimates, confidence with reason, and known catch."
            ),
            output_format=RESEARCHER_RESULT_FORMAT,
        )
        user_msg = f"Research {geography} {topic} for 5-year horizon. Focus: {focus}."
        response_text = await call_llm(openai_client, model, system_prompt, user_msg, temperature=0.3)
        result = extract_json(response_text)

        candidates = result.get("candidates", []) if result else []
        base = {"_prompt": system_prompt, "_user_message": user_msg, "_response_text": response_text,
                "_detail": {"candidates": candidates}}

        return {
            "agent": "X", "status": "done", "output_key": topic,
            "plan_hash": plan_hash, "cache_hit": False,
            "candidates": candidates,
            "quality_issues": result.get("quality_issues", []) if result else [],
            "follow_up_requests": result.get("follow_up_requests", []) if result else [],
            "m_update_signal": (result.get("m_update_signal", {"triggered": False, "reason": None})
                                if result else {"triggered": False, "reason": None}),
            **base,
        }

    except Exception as e:
        logger.exception(f"Researcher failed for {brief.get('topic', 'unknown')}")
        base = {"_detail": {"candidates": [], "error": str(e)}}
        return {
            "agent": "X", "status": "done", "output_key": brief.get("topic", "unknown"),
            "plan_hash": plan_hash, "cache_hit": False,
            "candidates": [], "quality_issues": [str(e)], "follow_up_requests": [],
            "m_update_signal": {"triggered": False, "reason": None}, "_error": str(e), **base,
        }