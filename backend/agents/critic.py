"""Agent C — Critic. Three escalating rounds with stateful history."""

import logging

from backend.agents._base import build_agent_prompt, call_llm, extract_json

logger = logging.getLogger(__name__)

CRITIC_OUTPUT_FORMAT = {
    "agent": "C", "status": "done", "round": 1,
    "critique": "The single most important issue",
    "killer_argument": "The core challenge",
    "prior_rounds_resolved": True, "satisfied": False,
    "m_update_signal": {"triggered": False, "reason": None},
}

ROUND_INSTRUCTIONS = {
    1: "Focus on **internal consistency**: concentration risk, correlations, budget arithmetic. ONE killer argument.",
    2: "**Before raising Round 2, confirm Round 1 resolved.** Then stress-test the single biggest macro assumption B is making.",
    3: "**Before raising Round 3, confirm Rounds 1-2 resolved.** Identify missed opportunities. After B revises, issue final sign-off.",
}


async def run_critic_agent(openai_client, model: str, round_num: int,
                            portfolio_draft: dict, macro_brief: dict,
                            prior_rounds: list, m_update_count: int) -> dict:
    if round_num not in ROUND_INSTRUCTIONS:
        raise ValueError(f"Invalid round number: {round_num}")

    memory_note = ""
    if m_update_count > 0 and prior_rounds:
        memory_note = "\nDo NOT re-raise issues already addressed. Focus on what the macro update changes."

    context_data = {
        "round": round_num, "portfolio_draft": portfolio_draft, "macro_brief": macro_brief,
        "prior_rounds": prior_rounds, "m_update_count": m_update_count,
    }
    system_prompt = build_agent_prompt(
        role=f"Devil's Advocate (Round {round_num})",
        context=context_data,
        instructions=ROUND_INSTRUCTIONS[round_num] + memory_note,
        output_format=CRITIC_OUTPUT_FORMAT,
    )
    user_msg = f"Critique Round {round_num}. {'Explicitly confirm prior rounds resolved before raising new arguments.' if round_num > 1 else ''}"
    response_text = await call_llm(openai_client, model, system_prompt, user_msg, temperature=0.4)
    result = extract_json(response_text)

    base = {"_prompt": system_prompt, "_user_message": user_msg, "_response_text": response_text,
            "_detail": {"round": round_num, "critique": result.get("critique") if result else None,
                        "killer_argument": result.get("killer_argument") if result else None}}

    if not result:
        return {"agent": "C", "status": "done", "round": round_num, "critique": "Parse failed",
                "prior_rounds_resolved": False, "satisfied": False,
                "m_update_signal": {"triggered": False, "reason": None}, **base}

    return {"agent": "C", "status": "done", "round": round_num,
            "critique": result.get("critique"), "killer_argument": result.get("killer_argument"),
            "prior_rounds_resolved": result.get("prior_rounds_resolved", False),
            "satisfied": result.get("satisfied", False),
            "m_update_signal": result.get("m_update_signal", {"triggered": False, "reason": None}),
            **base}