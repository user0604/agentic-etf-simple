"""Agent D — Tie-breaker. Binding verdict when B and C cannot reach consensus."""

import logging

from backend.agents._base import build_agent_prompt, call_llm, extract_json

logger = logging.getLogger(__name__)

TIEBREAKER_OUTPUT_FORMAT = {
    "agent": "D", "status": "done",
    "verdict": "B revises | C revises | both partially revise",
    "reasoning": "Which argument was stronger and why",
    "required_change": "Concrete instruction for the revising party",
    "revising_party": "B | C | both",
    "m_update_signal": {"triggered": False, "reason": None},
}


async def run_tiebreaker_agent(openai_client, model: str,
                                b_strongest_argument: str, c_strongest_argument: str,
                                macro_brief: dict) -> dict:
    context_data = {
        "b_strongest_argument": b_strongest_argument,
        "c_strongest_argument": c_strongest_argument,
        "macro_brief": macro_brief,
    }
    system_prompt = build_agent_prompt(
        role="Impartial Arbitrator", context=context_data,
        instructions=(
            "Evaluate which argument is stronger. Be specific. "
            "Your decision is BINDING. If the dispute reveals a macro gap, set m_update_signal."
        ),
        output_format=TIEBREAKER_OUTPUT_FORMAT,
    )
    user_msg = "Review the strongest arguments and issue your binding verdict."
    response_text = await call_llm(openai_client, model, system_prompt, user_msg, temperature=0.2)
    result = extract_json(response_text)

    base = {"_prompt": system_prompt, "_user_message": user_msg, "_response_text": response_text,
            "_detail": {"verdict": result.get("verdict") if result else None,
                        "reasoning": result.get("reasoning") if result else None}}

    if not result:
        return {"agent": "D", "status": "done", "verdict": "B revises",
                "reasoning": "LLM parse failed — defaulting to B revise",
                "required_change": "Review C's critique and address concerns",
                "revising_party": "B",
                "m_update_signal": {"triggered": False, "reason": None}, **base}

    return {"agent": "D", "status": "done",
            "verdict": result.get("verdict"), "reasoning": result.get("reasoning"),
            "required_change": result.get("required_change"),
            "revising_party": result.get("revising_party"),
            "m_update_signal": result.get("m_update_signal", {"triggered": False, "reason": None}),
            **base}