# v0.3 — Deep Integration Release

> **Merge of `feature+mf-deep-integration` branch**
> Pipeline hang fix, resiliency improvements, enhanced multi-agent orchestration, and feature-rich GUI.

---

## Table of Contents

1. [Critical Bug Fixes](#1-critical-bug-fixes)
2. [Pipeline & Orchestration](#2-pipeline--orchestration)
3. [Resiliency & Retry Logic](#3-resiliency--retry-logic)
4. [GUI Features](#4-gui-features)
5. [Testing](#5-testing)
6. [Configuration & Infrastructure](#6-configuration--infrastructure)
7. [Full File Change List](#7-full-file-change-list)

---

## 1. Critical Bug Fixes

### 1.1 Pipeline Hang After D's Verdict (ROOT CAUSE)

**Problem:** The pipeline always stopped producing output after Agent D (Tiebreaker) delivered its verdict. The frontend received D's result, then silence forever — even after 7+ hours of running.

**Root cause:** The main run loop had `Phase.FINAL` registered as a handler, but the loop immediately `break`-ed whenever any handler (tiebreak/critique) set `phase = Phase.FINAL`, **before** `_phase_final` was called. `_phase_final` was effectively dead code on fresh runs.

**Fix** (`backend/orchestrator.py` lines 622–629):
```python
if self.phase == Phase.FINAL:
    if handler != self._phase_final:
        await self._phase_final()
    break
```

This ensures `_phase_final` runs to completion every time, emitting "Generating final portfolio output" and "Portfolio final" SSE events and building the `portfolio_final` output dict.

### 1.2 Missing SSE Events During B's Revision

**Problem:** In `_phase_tiebreak`, when Agent D's verdict was "revise" and Agent B was asked to revise the portfolio, the orchestrator emitted no SSE events for B's work.

**Fix:** Added `_emit()` calls before and after B's revision dispatch.

### 1.3 Research Task String-to-Dict Normalization

**Problem:** When Agent B returned research tasks as plain strings instead of dicts with proper structure, downstream researcher agents failed to parse them.

**Fix:** Added normalization in `_phase_planning` and the `from_run_folder` resume path that converts string-typed tasks into proper dict structure.

### 1.4 Resume Path Sub-Step Detection

**Problem:** When resuming from a saved run folder, the orchestrator couldn't distinguish between "tiebreak phase is done" and "tiebreak phase partially complete."

**Fix:** Added detection logic that checks if B's revision was persisted before mapping tiebreak → FINAL vs staying on TIEBREAK.

---

## 2. Pipeline & Orchestration

### 2.1 Agent Architecture

The pipeline follows a strict phase progression:

```
MACRO → PLANNING → RESEARCH → DRAFT → CRITIQUE_1/2/3 → TIEBREAK → FINAL
```

**Phase flow:**
1. **MACRO** — Agent M produces a macro-economic brief (Fed/BOJ policy, USD/JPY outlook, sector analysis)
2. **PLANNING** — Agent B selects 8–12 research themes from a curated universe, distributes budget percentages, declares FX rate
3. **RESEARCH** — Researcher agents X1–Xn execute plans (pseudo-parallel), return candidates with bull/base/bear cases
4. **DRAFT** — Agent B builds initial portfolio from researcher candidates
5. **CRITIQUE 1–3** — Agent C reviews in 3 escalating rounds. After each round, B revises. Up to 3 iterations.
6. **TIEBREAK** — Agent D arbitrates final approval or orders further revision (one additional B revision allowed)
7. **FINAL** — Portfolio output generated and emitted to frontend

**Key orchestrator improvements:**
- Phase progression is event-driven via SSE to the frontend
- Retry-hook installed at run start so `call_llm` can emit SSE events on API throttling retries
- `m_update_signal` mechanism allows B to trigger M re-run during planning if macro conditions warrant

### 2.2 AsyncOpenAI Client Configuration

```python
self.client = AsyncOpenAI(api_key=first_key, base_url=nim_base_url,
                           timeout=120.0, max_retries=0)
```

- **timeout=120.0**: Increased from default to handle NVIDIA NIM's occasionally slow responses (DeepSeek V4-Pro can take 60–120s for complex reasoning)
- **max_retries=0**: Retry logic is handled at the application layer with smarter key rotation and backoff

---

## 3. Resiliency & Retry Logic

### 3.1 NVIDIA NIM "DEGRADED" Error Handling

**Problem:** NVIDIA's NIM API occasionally returns HTTP 400 with `DEGRADED function cannot be invoked` — a server-side capacity issue misclassified as a client error. The previous code treated ALL 400s as non-retryable.

**Fix** (`backend/agents/_base.py`):
```python
is_degraded = "DEGRADED" in str(e)
if status in (429, 502, 503) or is_degraded:
```

Now detects `"DEGRADED"` in the error message and treats it as retryable with exponential backoff.

### 3.2 Retry Architecture

| Layer | Location | Strategy |
|-------|----------|----------|
| OpenAI client | `AsyncOpenAI(max_retries=0)` | **Disabled** — handled below |
| `call_llm` | `backend/agents/_base.py` | Infinite retry on 429/502/503/DEGRADED, exponential backoff (capped 30s), round-robin key rotation |
| `_call_agent` | `backend/orchestrator.py` | 3 attempts with 0s/1s/2s backoff |

**Key rotation:** Comma-separated `NVIDIA_NIM_API_KEY` values are distributed round-robin across all keys.

**Rate limiting:** Minimum 200ms interval enforced between all LLM calls.

### 3.3 Retry Hook (SSE Integration)

Connects `call_llm` retry events to SSE emission. Frontend displays:
```
Agent X — retry #1, key #2/3, waiting 3.2s...
```

---

## 4. GUI Features

### 4.1 Server Log Panel (New Component)

A resizable panel for real-time server log display:
- Auto-scroll to newest entries
- SSE log streaming from `/api/run/{runId}/log`
- Drag-to-resize width
- Close/dismiss button
- Full log history load on connect

### 4.2 Activity Feed Enhancements

Complete rewrite with sophisticated detail formatting:
- **JST Timestamps** on every feed item (`YYYY/MM/DD HH:mm:ss`)
- **Research Plan View**: topic, screening criteria, approach, source badges
- **Enhanced Candidate Cards**:
  - Thesis with blue accent bar
  - Bull/Base/Bear scenario grid (green/gray/red) with return percentages
  - Confidence badge + reason text
  - "Known Catch" warning with severity labeling
  - Data sources list
- **Detail grouping**: pending detail payloads captured from `status: "detail"` events
- **Show/hide toggle** for structured details
- **Generic JSON fallback** with no truncation, `null, 1` indentation

### 4.3 Pipeline Status Display

- Pipeline status groups for agents M, B, C, D with live indicators (working/done/error)
- Log visibility toggle
- ServerLogPanel integrated into main app layout

---

## 5. Testing

### 5.1 New Test Suite — `tests/test_orchestrator.py`

**TestResearchTaskNormalization** (6 tests):
- Dict, string, mixed, null, empty, and field-preservation cases

**TestFromRunFolder** (9 tests):
- Resume from every phase, tiebreak sub-step detection, nonexistent folder error

---

## 6. Configuration & Infrastructure

### 6.1 Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `NIM_MODEL` | `deepseek-ai/deepseek-v4-pro` | NVIDIA NIM model identifier |
| `NIM_BASE_URL` | `https://integrate.api.nvidia.com/v1` | API base URL |
| `NVIDIA_NIM_API_KEY` | — | Comma-separated keys for round-robin |
| `NIM_RETRY_WAIT` | `3` | Base wait between retries |

### 6.2 .gitignore
- Uncommented `.claude/` exclusion

### 6.3 Architecture Docs
- `stock-agent-architecture.md` updated with resume path documentation

---

## 7. Full File Change List

| File | Change | Type |
|------|--------|------|
| `backend/orchestrator.py` | Pipeline hang fix, tiebreak SSE events, task normalization, resume detection, AsyncOpenAI timeout | Bug fix |
| `backend/agents/_base.py` | DEGRADED retry handling, retry hook mechanism | Resiliency |
| `frontend/src/ActivityFeed.jsx` | Complete rewrite: timestamps, research plans, enhanced candidates | Enhancement |
| `frontend/src/App.jsx` | ServerLogPanel import, log toggle, pipeline status | Enhancement |
| `frontend/src/ServerLogPanel.jsx` | **New** — real-time server log viewer | New feature |
| `tests/test_orchestrator.py` | 15 new tests for normalization and resume | Testing |
| `stock-agent-architecture.md` | Resume path documentation | Docs |
| `.gitignore` | `.claude/` exclusion uncommented | Config |

---

## Upgrade Notes

**Breaking changes:** None.

**Migration:**
1. Set `NVIDIA_NIM_API_KEY` (comma-separated for multiple keys)
2. No database migrations required