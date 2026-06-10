"""Shared utilities for agent implementations.
Provides consistent LLM calling, JSON parsing, and prompt building.
"""

import asyncio
import json
import logging
import os
import re
import time
from typing import Any

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# Rate-limit state and key-rotation counter: shared across all agents
_last_call_time = 0.0
_RATE_LIMIT_MIN_INTERVAL = 0.5  # seconds between calls (2 calls/sec max)
_call_counter = 0  # incremented per call for round-robin key distribution

# Retry-hook: set by the orchestrator so call_llm can emit SSE events
# when throttling retries happen. This avoids threading callbacks through
# every agent function signature.
_retry_hook = None


def set_retry_hook(callback):
    """Set a global callback invoked on each retry attempt.

    The callback receives: (attempt, status_code, wait_seconds, key_index, num_keys)
    Set to None to disable.
    """
    global _retry_hook
    _retry_hook = callback


async def call_llm(
    openai_client,
    model: str,
    system_prompt: str,
    user_message: str,
    temperature: float = 0.3,
    max_tokens: int = 8192,
    on_retry=None,
) -> str:
    """Call the LLM via NIM with rate-limit handling and infinite retry.

    Retries on 429 (rate limit), 502, 503 *indefinitely* — the system
    never stops due to throttling. Each retry is logged and, if a
    retry-hook is registered, an SSE event is emitted so the frontend
    can display retry status to the user.

    Enforces a global minimum interval between calls.

    API key rotation (round-robin):
      - If NVIDIA_NIM_API_KEY contains multiple comma-separated keys, every
        call distributes load evenly across all keys from the first attempt,
        and retries advance to the next key in the cycle.
      - If only one key exists, falls back to the passed openai_client.

    Args:
        openai_client: OpenAI AsyncClient configured for NVIDIA NIM.
            Used only when a single API key is configured.
        model: Model string.
        system_prompt: System-level instructions.
        user_message: The user turn content.
        temperature: Sampling temperature.
        max_tokens: Maximum tokens in the response.
        on_retry: Optional per-call callback (attempt, status, wait, key_idx, num_keys).
            If not provided, falls back to the global _retry_hook.

    Returns:
        The response text content.
    """
    global _last_call_time, _call_counter

    # Rate-limit: ensure interval between calls
    now = time.monotonic()
    since_last = now - _last_call_time
    if since_last < _RATE_LIMIT_MIN_INTERVAL:
        await asyncio.sleep(_RATE_LIMIT_MIN_INTERVAL - since_last)
    _last_call_time = time.monotonic()

    # Parse comma-separated API keys for round-robin distribution
    raw_keys = os.getenv("NVIDIA_NIM_API_KEY", "")
    api_keys = [k.strip() for k in raw_keys.split(",") if k.strip()]
    num_keys = len(api_keys)
    base_url = os.getenv("NIM_BASE_URL", "https://integrate.api.nvidia.com/v1")

    retry_cb = on_retry or _retry_hook

    attempt = 1
    while True:
        try:
            # Round-robin: pick a key based on (call_counter + attempt - 1)
            # This distributes the *first attempt* of each call across all keys,
            # and on retry naturally advances to the next key.
            if num_keys > 1:
                key_idx = (_call_counter + attempt - 1) % num_keys
                key = api_keys[key_idx]
                client = AsyncOpenAI(api_key=key, base_url=base_url)
            else:
                client = openai_client
                key_idx = 0

            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            _call_counter += 1  # advance for the next call
            return response.choices[0].message.content or ""

        except Exception as e:
            status = _extract_status(e)

            is_degraded = "DEGRADED" in str(e)

            if status in (429, 502, 503) or is_degraded:
                # Infinite retry on throttling or NVIDIA NIM DEGRADED — never give up
                wait = min(2 ** attempt + (attempt * 0.5), 30.0)  # exponential backoff + jitter, cap at 30s
                key_idx = (_call_counter + attempt - 1) % num_keys if num_keys > 1 else 0
                logger.warning(
                    f"LLM call attempt {attempt} got HTTP {status}, "
                    f"key #{key_idx + 1}/{num_keys}, "
                    f"retrying in {wait:.1f}s: {e}"
                )
                # Fire retry-hook so the orchestrator can emit an SSE event
                if retry_cb:
                    try:
                        await retry_cb(attempt, status, wait, key_idx, num_keys)
                    except Exception:
                        logger.exception("Retry-hook callback failed, continuing retry loop")
                await asyncio.sleep(wait)
                attempt += 1
            else:
                # Non-retryable error (400, 404, 401, etc.) — raise immediately
                _call_counter += 1
                logger.error(f"LLM call got non-retryable HTTP {status}: {e}")
                raise


def _extract_status(exc: Exception) -> int | None:
    """Try to extract HTTP status code from an exception."""
    # OpenAI APIError has status_code
    if hasattr(exc, "status_code"):
        return exc.status_code
    # httpx/requests errors
    if hasattr(exc, "response") and hasattr(exc.response, "status_code"):
        return exc.response.status_code
    # Check message for status code pattern
    m = re.search(r"(\d{3})", str(exc))
    if m:
        return int(m.group(1))
    return None


def extract_json(text: str) -> dict | None:
    """Extract a JSON object from LLM response text.

    Handles raw JSON, JSON in ```json code blocks, JSON after  tags.
    Returns parsed dict or None if no valid JSON found.
    """
    block_match = re.search(r"```(?:json)?\s*\n?([\s\S]*?)```", text)
    if block_match:
        try:
            return json.loads(block_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    brace_depth = 0
    start = -1
    candidates = []

    for i, ch in enumerate(text):
        if ch == "{":
            if brace_depth == 0:
                start = i
            brace_depth += 1
        elif ch == "}":
            brace_depth -= 1
            if brace_depth == 0 and start >= 0:
                candidates.append(text[start:i+1])
                start = -1

    candidates.sort(key=len, reverse=True)
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue

    return None


def build_agent_prompt(role: str, context: dict, instructions: str, output_format: dict) -> str:
    """Build a system prompt for a given agent role."""
    sections = [
        f"# Role: {role}",
        "",
        "## Context",
        json.dumps(context, indent=2, default=str),
        "",
        "## Instructions",
        instructions,
        "",
        "## Output Format",
        "You must end your response with a JSON block containing your structured output and status signal.",
        "The JSON block must follow this structure:",
        json.dumps(output_format, indent=2, default=str),
        "",
        "## Rules",
        "- Place the JSON block at the very end of your response.",
        "- Do not wrap the JSON in markdown code blocks.",
        "- All string values must use double quotes.",
        "- Include all keys shown, even if null.",
        "- The 'm_update_signal' key is required in every response.",
    ]
    return "\n".join(sections)