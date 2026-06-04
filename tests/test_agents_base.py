"""Tests for the shared agent utilities in _base.py."""

import json

import pytest

from backend.agents._base import extract_json, build_agent_prompt


class TestExtractJson:
    """extract_json handles various LLM response formats."""

    def test_raw_json(self):
        text = '{"agent": "M", "status": "done"}'
        result = extract_json(text)
        assert result == {"agent": "M", "status": "done"}

    def test_json_in_code_block(self):
        text = 'Some text\n```json\n{"agent": "M", "status": "done"}\n```\nMore text'
        result = extract_json(text)
        assert result == {"agent": "M", "status": "done"}

    def test_json_in_code_block_no_lang(self):
        text = 'Text\n```\n{"agent": "M", "status": "done"}\n```'
        result = extract_json(text)
        assert result == {"agent": "M", "status": "done"}

    def test_json_after_think_tags(self):
        text = 'Okay, let me analyze this.\n\n{"agent": "M", "status": "done"}'
        result = extract_json(text)
        assert result == {"agent": "M", "status": "done"}

    def test_multiple_json_objects_picks_most_complete(self):
        text = (
            '{"agent": "M", "status": "partial"}\n'
            'More analysis...\n'
            '{"agent": "M", "status": "done", "macro_brief": {"fed_policy": "test"}}'
        )
        result = extract_json(text)
        assert result is not None
        assert result.get("status") == "done"

    def test_nested_json_object(self):
        text = 'Some text {"agent": "C", "status": "done", "critique": {"round": 2, "issue": "test"}} more text'
        result = extract_json(text)
        assert result == {"agent": "C", "status": "done", "critique": {"round": 2, "issue": "test"}}

    def test_no_json_returns_none(self):
        text = "This response has no JSON at all."
        result = extract_json(text)
        assert result is None

    def test_malformed_json_returns_none(self):
        text = '{"agent": "M", "status: done}'
        result = extract_json(text)
        assert result is None

    def test_empty_string_returns_none(self):
        assert extract_json("") is None

    def test_large_deeply_nested_json(self):
        data = {
            "agent": "B",
            "status": "done",
            "portfolio_draft": {
                "holdings": [
                    {"ticker": f"TICK{i}", "allocation_pct": round(100 / 5, 1)}
                    for i in range(5)
                ]
            },
        }
        text = f"Some text\n{json.dumps(data)}\nend"
        result = extract_json(text)
        assert result is not None
        assert len(result["portfolio_draft"]["holdings"]) == 5

    def test_multiple_json_objects_same_depth(self):
        text = (
            '{"a": 1}\n'
            '{"b": 2}\n'
            '{"c": 3}'
        )
        result = extract_json(text)
        # When objects have equal depth, returns the first valid one found
        assert result == {"a": 1}

    def test_deepseek_r1_style_output(self):
        text = (
            ' \n'
            'I need to analyze the macro environment...\n'
            'The Fed is likely to cut rates.\n'
            '\n'
            'Based on the data, here is my analysis:\n'
            '- Fed holding steady\n'
            '- BOJ normalizing\n'
            '\n'
            '{"agent": "M", "status": "done", "macro_brief": {"fed_policy": "Holding"}}'
        )
        result = extract_json(text)
        assert result is not None
        assert result["agent"] == "M"
        assert result["macro_brief"]["fed_policy"] == "Holding"


class TestBuildAgentPrompt:
    """build_agent_prompt produces well-structured prompts."""

    def test_contains_role(self):
        prompt = build_agent_prompt("Macro Strategist", {}, "Do stuff", {"key": "val"})
        assert "# Role: Macro Strategist" in prompt

    def test_contains_context(self):
        ctx = {"rate": 5.25, "trend": "rising"}
        prompt = build_agent_prompt("Analyst", ctx, "Do stuff", {"key": "val"})
        assert '"rate": 5.25' in prompt
        assert '"trend": "rising"' in prompt

    def test_contains_instructions(self):
        prompt = build_agent_prompt("Analyst", {}, "Analyze the market carefully", {"key": "val"})
        assert "Analyze the market carefully" in prompt

    def test_contains_output_format(self):
        fmt = {"agent": "M", "status": "done"}
        prompt = build_agent_prompt("Analyst", {}, "Do stuff", fmt)
        assert '"agent": "M"' in prompt
        assert '"status": "done"' in prompt

    def test_contains_rules(self):
        prompt = build_agent_prompt("Analyst", {}, "Do stuff", {"key": "val"})
        assert "m_update_signal" in prompt
        assert "Do not wrap" in prompt

    def test_requires_m_update_signal(self):
        """Every prompt must instruct agents to include m_update_signal."""
        prompt = build_agent_prompt("Analyst", {}, "Do stuff", {"key": "val"})
        assert "m_update_signal" in prompt


@pytest.mark.asyncio
async def test_call_llm_basic(monkeypatch, mock_openai_client):
    """call_llm returns the text from the mocked response."""
    from backend.agents._base import call_llm

    # Force single-key mode so the mock client is used (not a real AsyncOpenAI)
    monkeypatch.setenv("NVIDIA_NIM_API_KEY", "test-single-key")

    mock_openai_client.chat.completions.create.return_value.choices[0].message.content = "Hello world"
    result = await call_llm(mock_openai_client, "test-model", "system", "user")
    assert result == "Hello world"


@pytest.mark.asyncio
async def test_call_llm_passes_correct_args(monkeypatch, mock_openai_client):
    """call_llm passes model, messages, temperature, max_tokens correctly."""
    from backend.agents._base import call_llm

    # Force single-key mode so the mock client is used
    monkeypatch.setenv("NVIDIA_NIM_API_KEY", "test-single-key")

    await call_llm(mock_openai_client, "deepseek-ai/deepseek-r1", "sys prompt", "user msg", temperature=0.7, max_tokens=2048)

    mock_openai_client.chat.completions.create.assert_called_once()
    kwargs = mock_openai_client.chat.completions.create.call_args[1]
    assert kwargs["model"] == "deepseek-ai/deepseek-r1"
    assert len(kwargs["messages"]) == 2
    assert kwargs["messages"][0]["role"] == "system"
    assert kwargs["messages"][0]["content"] == "sys prompt"
    assert kwargs["messages"][1]["role"] == "user"
    assert kwargs["messages"][1]["content"] == "user msg"
    assert kwargs["temperature"] == 0.7
    assert kwargs["max_tokens"] == 2048