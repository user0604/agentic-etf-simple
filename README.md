# 🧠 Multi-Agent Stock Portfolio System

[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com)
[![React 19](https://img.shields.io/badge/React-19-61DAFB.svg)](https://react.dev)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> **An AI-driven stock purchase planner.** Feed it a budget (JPY) and a purchase date, and a 6-agent LLM pipeline produces a ranked, allocated portfolio of US and Japan stocks optimized for a 5-year return horizon.

---

## 📋 Table of Contents

- [Overview](#-overview)
- [Architecture](#-architecture)
- [The 6 Agents](#-the-6-agents)
- [Pipeline Phases](#-pipeline-phases)
- [Features](#-features)
- [Tech Stack](#-tech-stack)
- [Getting Started](#-getting-started)
- [Configuration](#-configuration)
- [Project Structure](#-project-structure)
- [Research Themes](#-research-themes)
- [Scoring Formula](#-scoring-formula)
- [Data Sources](#-data-sources)
- [Motley Fool Offline Corpus](#-motley-fool-offline-corpus)
- [Resilience & Retry Logic](#-resilience--retry-logic)
- [Testing](#-testing)
- [Documentation](#-documentation)

---

## 🚀 Overview

This project is a **proof-of-concept** that replaces a human investment committee with an AI multi-agent system. Given two inputs — **budget** (in JPY) and **purchase date** — it orchestrates six specialized AI agents that collaborate like an institutional investment team:

| Role | Code | Analogy |
|------|------|---------|
| **Orchestrator** | A | Project manager / committee chair |
| **Macro Strategist** | M | Chief economist |
| **Portfolio Manager** | B | Senior portfolio manager |
| **Researchers** | X1–Xn | Sector analysts |
| **Critic** | C | Devil's advocate / risk officer |
| **Tiebreaker** | D | Independent arbiter |

Each agent is powered by **DeepSeek V4-Pro** via **NVIDIA NIM**, uses real financial data (FRED, SEC EDGAR, EDINET, Yahoo Finance, Alpha Vantage, Polygon.io), and supplements its analysis with a local **Motley Fool** article corpus indexed in ChromaDB for offline semantic search.

---

## 🏗 Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         A — Orchestrator                                  │
│         (event-driven supervisor, quality gate, phase manager)             │
└───────┬──────────────────────────────────────────────┬───────────────────┘
        │ dispatches                                   │ monitors all signals
        ▼                                             ▼
┌──────────────────┐                      ┌────────────────────────────┐
│  M — Macro       │◄── update signal ────│  B — Portfolio Manager     │◄──────────┐
│    Agent         │◄── update signal ────│   (proposer/optimizer)     │           │
└────────┬─────────┘◄── update signal ────│                            │           │
         │ macro brief                     └────────────┬───────────────┘           │
         │ (reruns when updated)                        │ issues + approves         │
         ▼                                              │ research plans            │
                             ┌──────────────────────────────────────────┐           │
                             │       X1 … Xn — Researchers              │           │
                             │  plan → B approval → execute             │           │
                             │     (pseudo-parallel batch)               │           │
                             └──────────────────────────────────────────┘           │
                                                                                    │
                             ┌──────────────────────────────────────────┐           │
                             │        C — Critic Agent                   │───────────┘
                             │  (3 rounds, escalating, stateful)         │
                             └──────────────────────────────────────────┘
                                            │ stalemate
                                            ▼
                             ┌──────────────────────────────────────────┐
                             │        D — Tie-breaker                    │
                             │  (triggered automatically by A)          │
                             └──────────────────────────────────────────┘
```

### Workflow

```
MACRO → PLANNING → RESEARCH → DRAFT → CRITIQUE_1/2/3 → TIEBREAK → FINAL
```

The system also supports **M-update** — at any point during Phases 2–5, agents B, C, or D can signal the orchestrator to re-run the macro strategist, then restart from the planning phase while preserving all research results.

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Event-driven, not timer-based** | Self-pacing — fast agents immediately pick up queued work |
| **A deduplicates research** | Keeps B's allocation logic uncontaminated |
| **A triggers D automatically** | No incentive problem — B/C don't self-report failure |
| **B reviews X plans before execution** | Catches misalignment before research effort is wasted |
| **B declares FX rate uniformly** | Makes all return estimates commensurable |
| **One critique argument per round** | Forces genuine strategic revision (mirrors real investment committees) |
| **D receives only strongest arguments** | Judges logical merit, not debate volume |
| **No hard cap on M-updates** | Frequent M corrections are themselves a signal worth surfacing |

---

## 🤖 The 6 Agents

### A — Orchestrator (`backend/orchestrator.py`)

The central state machine. Maintains the phase, task queue, agent states, research cache, and deduplication log. Dispatches agents, enforces phase ordering, validates outputs, detects consensus, and triggers tiebreaker or M-update when needed.

**9 phases:** `MACRO → PLANNING → RESEARCH → DRAFT → CRITIQUE_1 → CRITIQUE_2 → CRITIQUE_3 → TIEBREAK → FINAL`

### M — Macro Strategist (`backend/agents/macro.py`)

Assesses the global macro environment: Fed and BOJ policy, USD/JPY trends, inflation, recession risk, and geopolitical factors. Produces a macro brief consumed by all downstream agents. Uses FRED data, web search, and the local Motley Fool macro article corpus.

### B — Portfolio Manager (`backend/agents/portfolio.py`)

The strategic brain. Selects 8–12 research themes from a curated universe, distributes budget, declares the FX rate, reviews and approves researcher plans, constructs the portfolio using confidence-weighted scoring, and revises through critique rounds.

### X1–Xn — Researchers (`backend/agents/researcher.py`)

Domain specialists. Each scoped to one industry/theme. Two-phase execution:

1. **Plan submission** — submit research plan to B for approval
2. **Execution** — after approval, run web search + financial APIs + Motley Fool corpus

Return candidates with bull/base/bear scenarios, confidence level, and known catch.

### C — Critic (`backend/agents/critic.py`)

Three escalating rounds of critique (stateful across rounds):

| Round | Focus | What C Attacks |
|-------|-------|----------------|
| **1** — Internal Consistency | Concentration risk, holding correlations, currency imbalance, budget arithmetic |
| **2** — Thesis Stress Test | The single biggest macro assumption B is making |
| **3** — Missed Opportunities | Unrepresented sectors, geographies, or risk profiles |

Consensus is reached when C signals `satisfied: true` after Round 3.

### D — Tiebreaker (`backend/agents/tiebreaker.py`)

Triggered automatically by A after Round 3 without consensus. Receives only the strongest argument from each side (B and C), renders a binding verdict, and can also trigger an M-update if the stalemate reveals a disputed macro fact.

---

## ✨ Features

- **🧠 6-agent LLM pipeline** — specialized agents collaborate like an institutional investment team
- **🌍 US + Japan coverage** — themes, data sources, and screening criteria for both markets
- **📊 Real financial data** — FRED, SEC EDGAR, EDINET, Yahoo Finance, Alpha Vantage, Polygon.io
- **📚 Motley Fool offline corpus** — ~2,800 articles indexed in ChromaDB for semantic search
- **🔄 M-update mechanism** — mid-run macro re-evaluation without discarding research
- **💬 3-round escalating critique** — B defends and revises vs C's devil's advocate
- **⚖️ Tiebreaker arbitration** — D resolves B/C stalemates with binding verdicts
- **📈 Confidence-weighted scoring** — transparent, consistent ranking formula
- **🔁 Full persistence** — every LLM call saved to disk for audit trail and resume
- **▶️ Resume capability** — continue a run from any saved phase via API or UI
- **📡 SSE streaming** — real-time agent status and detail events to the React UI
- **🔑 Multi-key rotation** — comma-separated NVIDIA NIM API keys for rate-limit resilience
- **🔄 Retry with exponential backoff** — handles 429/502/503 and NVIDIA "DEGRADED" errors
- **📱 Export/Load JSON** — save and restore full run state (portfolio + events)
- **📋 Past runs history** — browse, inspect, and resume previous runs

---

## 🛠 Tech Stack

### Backend

| Technology | Purpose |
|------------|---------|
| **Python 3.13+** | Runtime |
| **FastAPI** | Web framework (async, SSE support) |
| **Uvicorn** | ASGI server |
| **OpenAI SDK** | LLM client for NVIDIA NIM |
| **ChromaDB** | Vector store for Motley Fool corpus |
| **sentence-transformers** | Embedding model for semantic search |
| **pytest + pytest-asyncio** | Test framework |

### Frontend

| Technology | Purpose |
|------------|---------|
| **React 19** | UI framework |
| **Vite 6** | Build tool / dev server |
| **@tanstack/react-query** | Data fetching & caching |

### LLM Provider

| Component | Detail |
|-----------|--------|
| **Model** | `deepseek-ai/deepseek-v4-pro` |
| **Provider** | NVIDIA NIM (OpenAI-compatible API) |
| **Endpoint** | `https://integrate.api.nvidia.com/v1` |

### MCP Servers (local processes)

| Server | Purpose |
|--------|---------|
| **sec-edgar-mcp** | Structured EDGAR filing data |
| **edinet-mcp** | Structured EDINET XBRL filing data |

---

## 🏁 Getting Started

### Prerequisites

- Python 3.13+
- Node.js 20+
- NVIDIA NIM API key (free tier available at [build.nvidia.com](https://build.nvidia.com))
- Tavily API key (free tier: 1,000 queries/month at [app.tavily.com](https://app.tavily.com))

### 1. Clone and Set Up Python

```powershell
git clone <repo-url>
cd stock-agent
python -m venv venv
venv\Scripts\pip install -r requirements.txt
```

### 2. Configure Environment

```powershell
cp .env.example .env
```

Edit `.env` with your API keys:

```env
NVIDIA_NIM_API_KEY=nvapi-key1,nvapi-key2      # Comma-separated for key rotation
TAVILY_API_KEY=tvly-...
FRED_API_KEY=...
EDINET_API_KEY=...
ALPHA_VANTAGE_API_KEY=...
POLYGON_API_KEY=...

NIM_BASE_URL=https://integrate.api.nvidia.com/v1
NIM_MODEL=deepseek-ai/deepseek-v4-pro
MAX_RESEARCHERS=6
CRITIQUE_ROUNDS=3
```

### 3. Install Frontend Dependencies

```powershell
cd frontend
npm install
cd ..
```

### 4. (Optional) Index Motley Fool Corpus

For the offline semantic search feature:

```powershell
venv\Scripts\python scripts/index_motley_fool.py
```

Scans `data/articles/`, chunks articles into ~500-token passages, embeds with sentence-transformers, and stores in `data/motley_fool_index/`. The system works without this (queries gracefully return empty).

### 5. Run Everything

```powershell
.\start.ps1
```

Or individually:

```powershell
# Terminal 1: Backend
venv\Scripts\python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2: Frontend
cd frontend && npm run dev
```

### 6. Trigger a Run

```powershell
curl -X POST http://localhost:8000/api/run `
  -H "Content-Type: application/json" `
  -d '{"budget":"1000000","date":"2026-06-20"}'
```

**Or via the UI:** Open http://localhost:5173, enter budget and date, click **Run**.

---

## ⚙️ Configuration

### Environment Variables (`.env`)

| Variable | Default | Description |
|----------|---------|-------------|
| `NVIDIA_NIM_API_KEY` | — | Comma-separated NVIDIA NIM API keys (round-robin rotation) |
| `NIM_BASE_URL` | `https://integrate.api.nvidia.com/v1` | NIM API base URL |
| `NIM_MODEL` | `deepseek-ai/deepseek-v4-pro` | Model identifier |
| `TAVILY_API_KEY` | — | Web search (primary) |
| `FRED_API_KEY` | — | US macro data |
| `EDINET_API_KEY` | — | Japan EDINET filings |
| `ALPHA_VANTAGE_API_KEY` | — | US equities data |
| `POLYGON_API_KEY` | — | US equities data |
| `SEC_EDGAR_USER_AGENT` | `StockPortfolioAgent/1.0 (research@example.com)` | EDGAR API user agent |
| `MAX_RESEARCHERS` | `6` | Maximum parallel research agents |
| `CRITIQUE_ROUNDS` | `3` | Critique escalation rounds |

### Runtime Parameters

Budget and purchase date are provided per run (via UI or API), not in `.env`.

---

## 📁 Project Structure

```
stock-agent/
│
├── .env                          # API keys and system config (not committed)
├── .env.example                  # Template for .env
├── start.ps1                     # PowerShell launcher (Windows)
├── requirements.txt              # Python dependencies
├── CLAUDE.md                     # Claude Code project instructions
│
├── backend/
│   ├── main.py                   # FastAPI app, SSE endpoints, run/resume API
│   ├── orchestrator.py           # Agent A: state machine, phase handlers, dispatch, resume
│   ├── run_logger.py             # Per-run disk persistence + resume helpers
│   ├── agents/
│   │   ├── _base.py              # Shared: call_llm (rate-limit, retry, key rotation), extract_json, build_agent_prompt
│   │   ├── macro.py              # Agent M — Macro Strategist
│   │   ├── portfolio.py          # Agent B — Portfolio Manager
│   │   ├── researcher.py         # Agent X — Researchers (parametric, many instances)
│   │   ├── critic.py             # Agent C — Critic
│   │   └── tiebreaker.py         # Agent D — Tiebreaker
│   ├── tools/
│   │   ├── fred.py               # FRED macro data API wrapper
│   │   ├── edgar.py              # SEC EDGAR + sec-edgar-mcp client
│   │   ├── edinet.py             # EDINET + edinet-mcp client
│   │   ├── alpha_vantage.py      # Alpha Vantage REST client
│   │   ├── polygon.py            # Polygon.io REST client
│   │   ├── yfinance_client.py    # Yahoo Finance wrapper (TSE ticker normalisation)
│   │   ├── web_search.py         # Tavily (primary) + DuckDuckGo (fallback)
│   │   └── motley_fool.py        # ChromaDB query client for offline corpus
│   ├── runs/                     # Per-run folders with full agent call logs
│   └── logs/                     # Server logs (DEBUG level)
│
├── frontend/
│   ├── index.html
│   ├── package.json
│   └── src/
│       ├── App.jsx               # Root layout, run/resume handlers
│       ├── RunForm.jsx           # Budget/date input + resume folder
│       ├── ActivityFeed.jsx      # SSE consumer, live agent status, collapsible details
│       ├── PortfolioTable.jsx    # Final portfolio with thesis, volume, allocation
│       ├── ServerLogPanel.jsx    # Draggable real-time log viewer
│       └── RunHistory.jsx        # Past runs list
│
├── data/
│   └── articles/
│       ├── macro/                # ~1,825 Motley Fool macro articles
│       ├── epic_exclusive/       # ~919 bull/bear deep dives
│       └── ticker_analysis/      # ~99 ticker-specific analyses
│
├── scripts/
│   └── index_motley_fool.py      # One-time ChromaDB index builder
│
├── tests/
│   ├── test_orchestrator.py      # State machine, phase transitions, dedup, resume
│   ├── test_agents.py            # Agent output format validation
│   ├── test_agents_base.py       # extract_json, build_agent_prompt, call_llm
│   └── test_tools.py             # Ticker normalisation, error handling
│
├── docs/
│   ├── CHANGELOG-v0.3.md         # v0.3 release notes
│   └── ...                       # Additional documentation
│
├── stock-agent-architecture.md   # Full architecture specification
├── research-structure.md         # Curated research themes (17 themes)
├── tech-stack.md                 # Technology choices and system design
└── data-sources.md               # All data sources with access methods
```

---

## 📊 Research Themes

The Portfolio Manager (B) selects **8–12 themes** per run from a curated universe of 17 themes organized by geography:

### United States Themes

| ID | Theme | Example Tickers |
|----|-------|----------------|
| US-01 | AI & Data Center Infrastructure | NVDA, AMD, AVGO, MRVL, EQIX |
| US-02 | Enterprise Software & Cloud | MSFT, CRM, NOW, PANW, ORCL |
| US-03 | Healthcare & Life Sciences | LLY, UNH, MRK, ABBV, JNJ |
| US-04 | US Financials | JPM, GS, BLK, V, MA |
| US-05 | Defense & Aerospace | LMT, RTX, NOC, GD, GE |
| US-06 | Energy & Industrial Transition | EPD, ETN, NEE, CAT, PWR |
| US-07 | Consumer & Retail | COST, WMT, AMZN, MCD, PEP |

### Japan Themes

| ID | Theme | Example Tickers |
|----|-------|----------------|
| JP-01 | Financials (Rate Normalisation) | 8316.T, 8766.T, 8604.T |
| JP-02 | Industrials & Factory Automation | 6954.T, 6861.T, 6273.T |
| JP-03 | Semiconductor Equipment | 8035.T, 6146.T, 7735.T |
| JP-04 | Trading Companies (Sogo Shosha) | 8058.T, 8031.T, 8001.T |
| JP-05 | Tech & Entertainment | 6758.T, 7974.T, 9684.T |
| JP-06 | Consumer & Defensive | 4452.T, 9983.T, 2502.T |
| JP-07 | Auto & Mobility | 7203.T, 7267.T, 6902.T |
| JP-08 | Real Estate & REITs | 8951.T, 8960.T, 3288.T |

### Global Themes

| ID | Theme |
|----|-------|
| G-01 | AI Infrastructure |
| G-02 | Climate/Energy Transition |

Each theme defines rationale, screening criteria, and example tickers. See [`research-structure.md`](research-structure.md) for the full specification.

---

## 📐 Scoring Formula

The Portfolio Manager ranks all deduplicated tickers using a **confidence-weighted return score**:

```
Score = (base_case_return × confidence_weight) − (bear_downside × (1 − confidence_weight))
```

| Confidence | Weight |
|------------|--------|
| High | 0.7 |
| Medium | 0.5 |
| Low | 0.3 |

**Budget allocation** is proportional to score, subject to constraints (no single holding >25% of budget, minimum industry diversity, US/Japan balance within M's recommended range). Any deviation must be documented with explicit reasoning.

---

## 🔌 Data Sources

| Source | Used By | Access | Coverage |
|--------|---------|--------|----------|
| [FRED](https://fred.stlouisfed.org) | M | Free REST API | US macro (Fed funds, CPI, GDP, USD/JPY) |
| [SEC EDGAR](https://www.sec.gov/edgar) | X | Free REST API + `sec-edgar-mcp` | 10-K/10-Q, insider trading, 13F |
| [EDINET](https://disclosure.edinet-fsa.go.jp) | X | Free API + `edinet-mcp` | Japan XBRL filings (annual/quarterly) |
| [Alpha Vantage](https://www.alphavantage.co) | X | Free tier REST API | US prices, fundamentals, estimates |
| [Polygon.io](https://polygon.io) | X | Free tier REST API | US OHLCV, financials, real-time quotes |
| [Yahoo Finance](https://finance.yahoo.com) | X | `yfinance` library | Price data, TSE coverage |
| [Tavily](https://tavily.com) | M, X | API (1k free queries/month) | AI-optimized web search |
| DuckDuckGo | M, X | No API key needed | Web search fallback |
| Motley Fool (offline) | M, X | Local ChromaDB | ~2,843 offline articles |

Web search uses **Tavily** as primary with **DuckDuckGo** as zero-cost fallback. See [`data-sources.md`](data-sources.md) for full details.

---

## 📚 Motley Fool Offline Corpus

A key differentiator — **~2,843 local Motley Fool articles** indexed in **ChromaDB** for offline semantic search:

| Type | Count | Folder | Used By |
|------|-------|--------|---------|
| Macro commentary | 1,825 | `data/articles/macro/` | M agent |
| Epic Exclusive (bull/bear) | 919 | `data/articles/epic_exclusive/` | X agents |
| Ticker analysis | 99 | `data/articles/ticker_analysis/` | X agents |

**How it works:**

- `backend/tools/motley_fool.py` — async ChromaDB query client
- Three query modes: `query` (broad), `query + ticker` (filtered), `query + article_type` (type-filtered)
- Supplements web search results — added to agent prompts alongside `web_search_results`
- Lazy-init singleton — no startup cost

**Setup** (one-time):

```powershell
venv\Scripts\python scripts/index_motley_fool.py
```

---

## 🔁 Resilience & Retry Logic

The system is built to handle NVIDIA NIM API instability gracefully:

| Layer | Location | Strategy |
|-------|----------|----------|
| OpenAI client | `AsyncOpenAI(max_retries=0)` | Disabled — handled at application layer |
| `call_llm` | `backend/agents/_base.py` | Infinite retry on 429/502/503/`DEGRADED`, exponential backoff (capped 30s), round-robin key rotation |
| `_call_agent` | `backend/orchestrator.py` | 3 attempts with 0s/1s/2s backoff |

**Rate limiting:** 500ms minimum interval enforced between all LLM calls.

**Key rotation:** Comma-separated `NVIDIA_NIM_API_KEY` values are distributed round-robin. Retry attempts use fresh API keys to avoid per-key throttling.

**SSE integration:** Retry events are streamed to the frontend so users see:

```
Agent X — retry #1, key #2/3, waiting 3.2s...
```

---

## 🧪 Testing

```powershell
# All tests
venv\Scripts\python -m pytest

# Single file
venv\Scripts\python -m pytest tests/test_orchestrator.py -v

# Single test
venv\Scripts\python -m pytest tests/test_agents.py::TestAgentM_Macro::test_output_format -v

# With live output
venv\Scripts\python -m pytest -s
```

All tests mock the OpenAI client via `conftest.py` — **no real API calls** during testing.

| Test File | Coverage |
|-----------|----------|
| `tests/test_orchestrator.py` | State machine, phase transitions, dedup, event emission, M-update logic, resume, research task normalization |
| `tests/test_agents.py` | Agent output format validation, graceful fallbacks, round escalation |
| `tests/test_agents_base.py` | `extract_json` (code blocks, think tags, nested JSON), `build_agent_prompt`, `call_llm` |
| `tests/test_tools.py` | Ticker normalization (TSE `.T` suffix), graceful error handling |

---

## 📖 Documentation

| Document | Description |
|----------|-------------|
| [`stock-agent-architecture.md`](stock-agent-architecture.md) | Full architecture: state machine, agent roles, scoring, communication protocol, persistence, resume |
| [`research-structure.md`](research-structure.md) | Curated universe of 17 research themes with screening criteria |
| [`tech-stack.md`](tech-stack.md) | Technology choices, system design, dependencies |
| [`data-sources.md`](data-sources.md) | All data sources with access methods, rationale, and cost |
| [`docs/CHANGELOG-v0.3.md`](docs/CHANGELOG-v0.3.md) | v0.3 deep integration release notes |
| [`planned-update-for-v0.3.md`](planned-update-for-v0.3.md) | Motley Fool offline corpus integration plan |

---

## 🙏 Acknowledgments

- **DeepSeek** for the V4-Pro model powering the agents
- **NVIDIA NIM** for hosted inference
- **Motley Fool** for the article corpus (used for research purposes only)
- All the open-source financial data providers (FRED, SEC EDGAR, EDINET, Alpha Vantage, Polygon.io, Yahoo Finance)

---

> **Disclaimer:** This is a **proof-of-concept** project. The portfolio outputs are for experimental and educational purposes only. They do not constitute financial advice. Always consult a qualified financial advisor before making investment decisions.