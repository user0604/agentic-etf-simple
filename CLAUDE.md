# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project: Multi-Agent Stock Portfolio System

A PoC AI-driven stock purchase planner. Takes a budget (JPY) and purchase date, runs a multi-agent pipeline to produce a ranked/allocated portfolio of US/Japan stocks optimized for 5-year return.

**Backend:** Python 3.13+, FastAPI + Uvicorn  
**Frontend:** React 19 + Vite 6 + @tanstack/react-query  
**LLM:** NVIDIA NIM API (default: `deepseek-ai/deepseek-v4-pro`) via `openai` Python SDK  
**Tests:** pytest + pytest-asyncio  
**Vector Store:** ChromaDB + sentence-transformers (local Motley Fool corpus)

---

## Architecture (6-Agent Pipeline)

```
A (Orchestrator) → M (Macro) → B (Portfolio Manager) → X1..Xn (Researchers) → C (Critic) → D (Tiebreaker)
```

| Agent | File | Role |
|-------|------|------|
| **A** | `backend/orchestrator.py` | Event-driven state machine; 9 phases (macro → planning → research → draft → critique_1/2/3 → tiebreak → final) |
| **M** | `backend/agents/macro.py` | Macro strategist: Fed/BOJ policy, USD/JPY, sector tailwinds/headwinds |
| **B** | `backend/agents/portfolio.py` | Portfolio manager: selects 8-12 research themes, sets FX rate, constructs/scored portfolio, reviews researcher plans, revises after critique |
| **X1..Xn** | `backend/agents/researcher.py` | Domain specialists: submit plan → B approves → execute research (web search + Motley Fool corpus) → return ticker candidates |
| **C** | `backend/agents/critic.py` | 3-round escalating critique (internal consistency → thesis stress test → missed opportunities), signals `satisfied` |
| **D** | `backend/agents/tiebreaker.py` | Resolves B/C stalemate after round 3, can also trigger M-update |

### Research Themes (from `research-structure.md`)

B selects 8-12 themes per run from this curated universe:

**US Themes:** US-01 AI & Data Center Infrastructure, US-02 Enterprise Software, US-03 Healthcare & Life Sciences, US-04 Financials, US-05 Defense & Aerospace, US-06 Energy & Industrial Transition, US-07 Consumer & Retail

**Japan Themes:** JP-01 Financials (Rate Normalisation), JP-02 Industrials & Factory Automation, JP-03 Semiconductor Equipment, JP-04 Trading Companies (Sogo Shosha), JP-05 Tech & Entertainment, JP-06 Consumer & Defensive, JP-07 Auto & Mobility, JP-08 Real Estate & REITs

**Global Themes:** AI Infrastructure, Climate/Energy Transition

Each theme defines rationale, screening criteria, and example tickers. Theme topic names serve as `topic` keys in research task dicts.

### Key Design Decisions

- **Event-driven**: Orchestrator runs a loop dispatching phase handlers; each agent call is sequential within a phase
- **B reviews X plans before execution**: Prevents wasted research on misaligned briefs
- **A deduplicates research**: Merges tickers from multiple X agents before B sees them
- **M-update**: B, C, or D can trigger a macro re-evaluation mid-run, which restarts from planning while preserving research cache
- **3 critique rounds**: Single escalating argument per round; consensus detected via `C.satisfied == true`
- **Full persistence**: Every LLM call saved to `backend/runs/{timestamp}_{runid}/` for audit trail and resume

### State Machine

9 phases defined in `backend/orchestrator.py` lines 22-31. The `run()` method loops through `phase_handlers` dict until FINAL. Resume via `Orchestrator.from_run_folder()` classmethod.

### Agent Communication Protocol

Every agent ends its output with a structured status block. The `m_update_signal` field is in every agent's status. C carries `prior_rounds_resolved` and `satisfied` booleans. A uses `satisfied == true` after Round 3 for deterministic consensus detection.

### Scoring Formula

`Score = (base_case_return × confidence_weight) − (bear_downside × (1 − confidence_weight))`
- High: 0.7, Medium: 0.5, Low: 0.3

---

## Motley Fool Offline Corpus

A key differentiator — ~2,843 local Motley Fool articles indexed in ChromaDB for offline semantic search:

| Article Type | Count | Folder | Used by |
|-------------|-------|--------|---------|
| Macro commentary | 1,825 | `data/articles/macro/` | M agent (`article_type="macro"`) |
| Epic Exclusive (bull/bear) | 919 | `data/articles/epic_exclusive/` | X agents (broad search) |
| Ticker analysis | 99 | `data/articles/ticker_analysis/` | X agents (broad + ticker-filtered) |

**How it works:**
- `backend/tools/motley_fool.py` — ChromaDB query client, async, returns `list[dict]` with `{title, date, article_type, passage, ticker, source_file, score}`
- Three query modes: `query` only (broad), `query + ticker` (ticker-filtered), `query + article_type` (type-filtered)
- Lazy-init module-level singleton (`chromadb.PersistentClient`)
- Supplements web search results — passed to agents as `motley_fool_results` in their context, appended to agent prompts
- M agent calls it with `article_type="macro"` for qualitative macro context
- X agents call it for candidate discovery and deep dives, added alongside `web_search_results`

**Index setup** (one-time, before first run):
```powershell
venv\Scripts\python scripts/index_motley_fool.py
```
Scans subfolders under `data/articles/`, reads each folder's `index.md` manifest, chunks articles into ~500-token passages, embeds with sentence-transformers, stores in `data/motley_fool_index/`. Re-run when articles change.

---

## Data Sources

| Source | Tools file | Used by | Access |
|--------|-----------|---------|--------|
| FRED | `backend/tools/fred.py` | M | REST API (free) |
| SEC EDGAR | `backend/tools/edgar.py` + sec-edgar-mcp MCP server | X | REST API (free) |
| EDINET (Japan) | `backend/tools/edinet.py` + edinet-mcp MCP server | X | REST API (free key) |
| Alpha Vantage | `backend/tools/alpha_vantage.py` | X | REST API (free tier) |
| Polygon.io | `backend/tools/polygon.py` | X | REST API (free tier) |
| Yahoo Finance | `backend/tools/yfinance_client.py` | X | Python library |
| Tavily / DuckDuckGo | `backend/tools/web_search.py` | M, X | API / scraping |
| Motley Fool (offline) | `backend/tools/motley_fool.py` | M, X | Local ChromaDB |

Web search uses Tavily as primary with DuckDuckGo fallback. All blocking I/O runs in a thread pool. Motley Fool corpus is entirely local (no rate limits, no internet required after indexing).

---

## Commands

### Development Setup

```powershell
python -m venv venv
venv\Scripts\pip install -r requirements.txt
cd frontend && npm install
```

### Environment

Copy `.env.example` to `.env` and fill in API keys. Required:
- `NVIDIA_NIM_API_KEY` — LLM provider (comma-separated for key rotation in `_base.py:call_llm`)
- `TAVILY_API_KEY` — web search (falls back to DuckDuckGo if missing)
- `FRED_API_KEY` — US macro data
- `EDINET_API_KEY` — Japan filings
- `ALPHA_VANTAGE_API_KEY`, `POLYGON_API_KEY` — US equities data

### Index Motley Fool Articles (One-Time)

```powershell
venv\Scripts\python scripts/index_motley_fool.py
```
Scans `data/articles/`, builds ChromaDB index at `data/motley_fool_index/`. The system works without this (MF queries gracefully return empty, agents fall back to web search only).

### Run Everything

```powershell
.\start.ps1
# Or individually:
venv\Scripts\python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
cd frontend && npm run dev
```

- Backend: http://localhost:8000 | Frontend: http://localhost:5173 | API docs: http://localhost:8000/docs

### Run Tests

```powershell
# All tests:
venv\Scripts\python -m pytest

# Single file:
venv\Scripts\python -m pytest tests/test_orchestrator.py -v

# Single test:
venv\Scripts\python -m pytest tests/test_agents.py::TestAgentM_Macro::test_output_format -v

# With live output:
venv\Scripts\python -m pytest -s

# Headless (no cache dependency):
venv\Scripts\python -m pytest -p no:cacheprovider
```

### Quick API Test

```powershell
curl -X POST http://localhost:8000/api/run -H "Content-Type: application/json" -d '{"budget":"1000000","date":"2026-06-20"}'
```

---

## Test Structure

| File | What it tests |
|------|--------------|
| `tests/test_orchestrator.py` | State machine: phase transitions, dedup, event emission, M-update logic, resume (from_run_folder), research task normalization |
| `tests/test_agents.py` | Agent output format validation (required keys per agent), graceful fallbacks on parse failure, round escalation, tool signatures |
| `tests/test_agents_base.py` | `extract_json` (code blocks, think tags, nested JSON, DeepSeek-R1 style), `build_agent_prompt`, `call_llm` |
| `tests/test_tools.py` | Ticker normalization (TSE .T suffix), graceful error handling, structure validation |

Tests mock the OpenAI client via `conftest.py` — no real API calls during testing.

---

## Key File Paths

- `backend/orchestrator.py` — Agent A (central state machine, all phase handlers, resume)
- `backend/main.py` — FastAPI app (SSE streaming, run/resume endpoints, log polling)
- `backend/run_logger.py` — Persistence layer + resume loader
- `backend/agents/_base.py` — Shared: `extract_json`, `build_agent_prompt`, `call_llm` (multi-key retry for NVIDIA NIM throttling, DEGRADED error handling, 200ms rate-limit interval)
- `backend/agents/macro.py` — Agent M: FRED data + web search + Motley Fool macro articles
- `backend/agents/researcher.py` — Agent X: web search + Motley Fool corpus, ticker candidate schema validation
- `backend/agents/portfolio.py` — Agent B: theme selection, plan review, portfolio construction/scoring, revision
- `backend/agents/critic.py` — Agent C: 3-round escalating critique, consensus detection
- `backend/agents/tiebreaker.py` — Agent D: verdict between B and C, can trigger M-update
- `backend/tools/motley_fool.py` — ChromaDB query client for offline article search
- `backend/tools/web_search.py` — Tavily primary / DuckDuckGo fallback
- `scripts/index_motley_fool.py` — One-time indexing script for the article corpus
- `data/articles/` — 2,843 Motley Fool articles (macro, epic_exclusive, ticker_analysis)
- `frontend/src/App.jsx` — Main UI (SSE connection, pipeline status bar, export/load from JSON)
- `frontend/src/ActivityFeed.jsx` — Agent event stream with collapsible detail views (macro brief, research plans, candidates, critique, tiebreaker verdict, portfolio drafts)
- `frontend/src/PortfolioTable.jsx` — Final portfolio table with expandable thesis, audit trail
- `frontend/src/ServerLogPanel.jsx` — Draggable side panel, polls backend logs every 2s
- `frontend/src/RunForm.jsx` — Budget/date input + resume folder path

### Architecture Docs

- `stock-agent-architecture.md` — Full architecture specification (state machine, agent roles, scoring, communication protocol, persistence, resume)
- `research-structure.md` — Curated universe of 17 research themes (US + Japan + Global) with screening criteria
- `tech-stack.md` — Technology choices and system design
- `data-sources.md` — All data sources with access methods and rationale
- `planned-update-for-v0.3.md` — Motley Fool offline corpus integration plan
- `docs/CHANGELOG-v0.3.md` — v0.3 deep integration release notes (pipeline fix, resiliency, GUI features)