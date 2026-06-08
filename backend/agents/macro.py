"""Agent M — Macro Agent."""

import json
import logging

from backend.agents._base import build_agent_prompt, call_llm, extract_json
from backend.tools.fred import get_macro_snapshot
from backend.tools.web_search import web_search
from backend.tools.motley_fool import query_motley_fool

logger = logging.getLogger(__name__)

MACRO_OUTPUT_FORMAT = {
    "agent": "M",
    "status": "done",
    "macro_brief": {
        "fed_policy": "summary of current Fed stance, rate path, and balance sheet trajectory",
        "boj_policy": "summary of BOJ policy direction, yield curve control status, rate normalization path",
        "usd_jpy_outlook": "USD/JPY 12-month range forecast and directional bias",
        "us_japan_weight_rationale": "recommended US vs Japan allocation split and reasoning",
        "sector_tailwinds": ["sector_with_macro_tailwind_1"],
        "sector_headwinds": ["sector_with_macro_headwind_1"],
    },
    "m_update_signal": {"triggered": False, "reason": None},
}

MACRO_INSTRUCTUTIONS = """\
You are a macro strategist producing a 5-year investment horizon briefing.
Cover: Fed policy, BOJ policy, USD/JPY outlook, US vs Japan allocation, sector analysis.
Be specific and data-driven. End with the JSON block."""


async def run_macro_agent(openai_client, model: str) -> dict:
    try:
        fred_data = await get_macro_snapshot()
        search_queries = [
            "Federal Reserve interest rate outlook 2026 2027",
            "Bank of Japan monetary policy rate normalization 2026",
            "USD JPY forecast next 12 months analysts",
            "Japan stock market outlook 2026 foreign investment",
            "US recession risk indicators 2026",
        ]
        search_results = {}
        for query in search_queries:
            try:
                search_results[query] = await web_search(query, max_results=3)
            except Exception as e:
                logger.warning(f"Web search failed: {e}")
                search_results[query] = []

        # Supplement with Motley Fool macro commentary (local, no rate limits)
        motley_fool_results = {}
        try:
            mf_macro = await query_motley_fool("US Japan macro outlook 2026", article_type="macro", top_k=3)
            if mf_macro:
                motley_fool_results["macro"] = mf_macro
        except Exception as e:
            logger.warning(f"Motley Fool macro query failed: {e}")

        context = {
            "fred_macro_data": fred_data,
            "web_search_results": search_results,
            "motley_fool_results": motley_fool_results,
            "investment_horizon": "5 years",
        }

        system_prompt = build_agent_prompt(
            role="Macro Strategist",
            context=context,
            instructions=MACRO_INSTRUCTUTIONS,
            output_format=MACRO_OUTPUT_FORMAT,
        )

        user_message = (
            "Based on the FRED macro data and web search results provided, "
            "produce a comprehensive macro briefing for a 5-year stock portfolio investment. "
            "The investor has a JPY budget and will buy both US and Japan equities."
        )

        response_text = await call_llm(openai_client, model, system_prompt, user_message, temperature=0.3)
        result = extract_json(response_text)

        if not result:
            return {
                "agent": "M", "status": "done",
                "macro_brief": {"fed_policy": "LLM parsing failed", "boj_policy": None,
                                "usd_jpy_outlook": None, "us_japan_weight_rationale": None,
                                "sector_tailwinds": [], "sector_headwinds": []},
                "m_update_signal": {"triggered": False, "reason": None},
                "_prompt": system_prompt, "_user_message": user_message, "_response_text": response_text,
                "_detail": {"fed_policy": "LLM parsing failed"},
            }

        brief = result.get("macro_brief", {})
        for key in ["fed_policy", "boj_policy", "usd_jpy_outlook", "us_japan_weight_rationale"]:
            if key not in brief:
                brief[key] = None
        for key in ["sector_tailwinds", "sector_headwinds"]:
            if key not in brief:
                brief[key] = []

        return {
            "agent": "M", "status": "done", "macro_brief": brief,
            "m_update_signal": result.get("m_update_signal", {"triggered": False, "reason": None}),
            "_prompt": system_prompt, "_user_message": user_message, "_response_text": response_text,
            "_detail": brief,
        }

    except Exception as e:
        logger.exception("Macro agent failed")
        return {
            "agent": "M", "status": "done",
            "macro_brief": {"fed_policy": f"Error: {e}", "boj_policy": None,
                            "usd_jpy_outlook": None, "us_japan_weight_rationale": None,
                            "sector_tailwinds": [], "sector_headwinds": []},
            "m_update_signal": {"triggered": False, "reason": None},
            "_error": str(e),
        }