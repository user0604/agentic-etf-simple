# Tech Stack & System Design — Multi-Agent Stock Portfolio System

> This document describes the complete local system: what runs where, how components
> communicate, and why each technology was chosen.
> Read alongside `stock-agent-architecture.md` and `data-sources.md`.

---

## 1. System at a Glance

```
┌─────────────────────────────────────────────────────────────────┐
│                        Your Local Machine                        │
│                                                                  │
│  ┌───────────────┐        ┌──────────────────────────────────┐  │
│  │  React UI     │◄──────►│  Python Backend (FastAPI)        │  │
│  │  (browser)    │  HTTP  │  - Orchestrator (Agent A logic)  │  │
│  └───────────────┘        │  - Agent runners (M, B, C, D, X) │  │
│                           │  - Session & state management    │  │
│                           │  - Data source clients           │  │
│                           └──────────┬───────────────────────┘  │
│                                      │                           │
│              ┌───────────────────────┼───────────────────────┐  │
│              │                       │                       │  │
│              ▼                       ▼                       ▼  │
│   ┌─────────────────┐   ┌─────────────────┐   ┌──────────────┐ │
│   │ sec-edgar-mcp   │   │  edinet-mcp     │   │ External APIs│ │
│   │ (local process) │   │ (local process) │   │ (internet)   │ │
│   └─────────────────┘   └─────────────────┘   └──────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

**Request flow for a single run:**
1. User sets budget + purchase date in React UI → clicks Run (or pastes a run folder path → clicks Resume from Folder)
2. React sends POST to FastAPI backend (or POST to `/api/run/resume` with folder path)
3. Backend runs the agent pipeline (A orchestrates M → B → X agents → C/D loop; or resumes from the last completed phase)
4. Each agent call hits the NVIDIA NIM API; X agents also call data sources
5. Backend streams agent status events back to React via SSE — including collapsible detail payloads (macro briefs, research plans, debate contents)
6. Each agent call is automatically persisted to disk in a per-run folder (`backend/runs/{timestamp}_{runid}/`)
7. React renders live agent activity (with expandable detail sections) and final portfolio table

---

## 2. Technology Choices

### Backend — Python + FastAPI

**Why Python:**
Best ecosystem for this project's needs — `anthropic` SDK, `yfinance`, `fredapi`,
`edinet-tools`, `sec-api`, `asyncio` for pseudo-parallel agent dispatch, and `pandas`
for any data wrangling are all first-class Python libraries. No equivalent breadth
exists in any other language for financial data tooling.

**Why FastAPI:**
- Native `async/await` support — essential for pseudo-parallel agent dispatch
  (`asyncio.gather` across X agents) without blocking
- Built-in SSE (Server-Sent Events) support for streaming agent status to the UI
- Automatic OpenAPI docs at `/docs` — useful during development
- Lightweight — no ORM, no database needed for a local PoC

**Why not a simple script:**
Budget and purchase date are external parameters; the system needs to be re-runnable.
A FastAPI server with a React UI provides a clean parameter input layer and run history
without requiring a full database setup.

---

### Frontend — React + Vite

**Why React:**
Handles the live-updating agent activity feed naturally with state management.
The run UI has several dynamic parts — agent status indicators, streaming log,
portfolio table — that would be awkward in plain HTML/JS.

**Why Vite:**
Fastest local dev server setup for React. No configuration needed beyond
`npm create vite@latest`. Hot module reload makes UI iteration fast.

**UI layout (three sections):**

```
┌──────────────────────┬──────────────────────────────────────────┐
│  Run Parameters      │  Agent Activity Feed                     │
│  (hidden while       │  ──────────────────────────────────────  │
│   running)           │  [⟳] Orchestrator: Starting run          │
│                      │  [✓] Macro Strategist: Brief complete    │
│  Past Runs           │  [✓] Portfolio Builder (B): Tasks issued │
│  ─────────────────   │  [⟳] Research Agent X1: Working...       │
│  2026-06-01 ¥1M      │  [✓] Critic (C): Round 1 done            │
│  2026-05-15 ¥500K    │  [▶ Show details] Critique content       │
│                      │  [✓] Tiebreaker (D): Approved             │
│                      │  ──────────────────────────────────────  │
│                      │  Portfolio Table (thesis, volume,        │
│                      │  allocation, confidence per holding)     │
│                      │  ⬇ Export to JSON  ⬆ Load from JSON     │
└──────────────────────┴──────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────────┐
│ Pipeline (status bar, always visible while running)              │
│ ✓ Macro Strategist | ● Portfolio Builder | → Critic, Tiebreaker │
└─────────────────────────────────────────────────────────────────┘
```

**GUI features during this session's implementation:**

- **Timestamp on every event**: Each activity feed line shows a local-time timestamp (HH:mm:ss) in the user's timezone, added client-side when the SSE event is received.
- **Run Parameters panel disappears** while a run is in progress, replaced by a compact "Run in Progress" indicator showing the Run ID and a pulsing dot.
- **Agent status bar** pinned to the bottom of the viewport while a run is active. Shows three labeled columns: `Finished:` (✓ completed agents), `Working:` (● with pulsing dot), and `Up next:` (→ pending) — all displayed with agent role names (e.g. "Macro Strategist" not "M").
- **Smart detail formatting**: The collapsible "Show details" sections render structured content as readable paragraphs and tables instead of raw JSON dumps:
  - Research tasks: formatted list with topic, industry, geography, and budget badge
  - Critique rounds: styled verdict badge, issues with severity tags, strengths list, suggested adjustments
  - Portfolio drafts: inline table of tickers with allocation %, confidence, expected return
  - Macro briefs: key-value pairs replacing `_` with ` ` and capitalizing labels
  - Research candidates: individual cards showing ticker, sector, price, return, and confidence
  - Tiebreaker verdict: large styled APPROVED or REVISE badge with reasoning
- **Smart detail formatting**: The collapsible "Show details" sections render structured content as readable paragraphs and tables instead of raw JSON dumps:
  - Research tasks: formatted list with topic, industry, geography, and budget badge
  - Critique rounds: styled verdict badge, issues with severity tags, strengths list, suggested adjustments
  - Portfolio drafts: inline table of tickers with allocation %, confidence, expected return
  - Macro briefs: key-value pairs replacing `_` with ` ` and capitalizing labels
  - Research candidates: individual cards showing ticker, sector, price, return, and confidence
  - Tiebreaker verdict: large styled APPROVED or REVISE badge with reasoning
- **Agent role naming everywhere**: The activity feed and status bar display human-readable role names (e.g. "Macro Strategist (M)", "Portfolio Builder (B)", "Critic (C)", "Tiebreaker (D)", "Research Agent X1") instead of raw single-letter codes.
- **Portfolio enrichment**: Final portfolio table includes columns for sector, estimated share price, computed share volume, and an expandable "View" button for the full investment thesis per holding. The thesis is sourced from the research cache — no additional LLM calls needed.
- **Export / Load JSON**: After any completed run, an "⬇ Export to JSON" button saves the full portfolio data, event log, and run metadata as a downloadable `.json` file. "⬆ Load from JSON" opens a file picker to load a previously exported file and reconstruct the exact screen state (portfolio table + activity feed) without re-running.

---

### Agent Execution — OpenAI SDK via NVIDIA NIM

Each agent (M, B, C, D, X) is a function that:
1. Builds a prompt (system + user content, including relevant context)
2. Calls `openai.chat.completions.create()` via NVIDIA NIM's OpenAI-compatible API
   with `model="deepseek-ai/deepseek-v4-pro"`
3. Parses the response text + status JSON block
4. Returns structured output to the orchestrator

All agent calls go through a shared `call_llm` helper in `backend/agents/_base.py`
that enforces:

- **Global rate limiting:** A 0.5-second minimum interval between all LLM calls
  (module-level `_last_call_time` state shared across all agents), preventing
  NIM's per-second rate cap from being hit.
- **Exponential backoff on retry:** 429 (rate limit), 502, and 503 errors trigger
  retry with `wait = min(2^attempt + jitter, 30s)` for up to 5 attempts.
- **API key rotation:** If `NVIDIA_NIM_API_KEY` contains multiple comma-separated
  keys, each retry attempt creates a fresh `AsyncOpenAI` client using the next
  key in the cycle. Logs which key index is being used per attempt.
- **Immediate raise on non-retryable errors:** 400, 401, 404 errors raise
  immediately without retry.

The orchestrator's `_call_agent` method adds a further 3-attempt outer retry
layer with 2^attempt backoff for transient agent function failures.

**Why DeepSeek-V4-Pro (not Llama 3.3 70B):**
The system requires multi-step reasoning — B defending portfolio allocations,
C stress-testing assumptions across 3 escalating rounds, D evaluating argument
quality. DeepSeek-V4-Pro is purpose-built for chain-of-thought reasoning
and significantly outperforms Llama 3.3 70B on structured critique and analytical
tasks. It is served through NVIDIA NIM's OpenAI-compatible endpoint at
`https://integrate.api.nvidia.com/v1/chat/completions`.

**Why OpenAI SDK (not Anthropic SDK) with NIM:**
NVIDIA NIM exposes an OpenAI-compatible chat completions API. The `openai` Python
SDK is the natural client. Response parsing uses `response.choices[0].message.content`
instead of the Anthropic SDK's `response.content[0].text`. The model string is
passed in the `model` field of each request.

**Pseudo-parallel X agent dispatch:**
```python
results = await asyncio.gather(
    run_researcher(openai_client, brief_1),
    run_researcher(openai_client, brief_2),
    run_researcher(openai_client, brief_3),
)
```
All researcher calls are dispatched simultaneously and awaited together.
Sequential B review of plans happens before this gather call.

---

### MCP Servers — Separate Local Processes

`sec-edgar-mcp` and `edinet-mcp` run as independent local processes alongside
the Python backend. The backend communicates with them via stdio (standard MCP
transport), managed by the Anthropic SDK's MCP client support.

**Why separate processes (not integrated into backend):**
- Zero custom code — both MCP servers are installed and run with one command each
- Lifecycle independence — MCP server crashes don't take down the backend
- Standard pattern — matches how Claude Desktop and other MCP clients work
- Upgradeable independently — when a new version of `edinet-mcp` releases, update
  it without touching the backend

**Startup:** both MCP servers are started automatically by a single shell script
(`start.sh`) before the backend launches. They are stopped when the backend exits.

**Why MCP over direct API calls for EDGAR and EDINET:**
The MCP servers handle XBRL parsing, filing retrieval, and data normalisation
internally. Without them, the backend would need to implement XBRL parsing for
both US GAAP and J-GAAP/IFRS — significant engineering work. The MCP servers
provide structured, agent-ready output (DataFrames, JSON) with no parsing code required.

---

### Data Source Clients

All data source clients live in a shared `tools/` module imported by X agent runners.
This is the "shared tool layer" referenced in the architecture document.

```
backend/
└── tools/
    ├── fred.py              # fredapi wrapper — macro series for M
    ├── edgar.py             # sec-edgar-mcp client + data.sec.gov REST calls
    ├── edinet.py            # edinet-mcp client + edinet-tools wrapper
    ├── alpha_vantage.py     # Alpha Vantage REST client
    ├── polygon.py           # Polygon.io REST client
    ├── yfinance.py          # yfinance wrapper with TSE ticker normalisation
    ├── web_search.py        # Tavily primary + DuckDuckGo fallback
    └── __init__.py
```

**Web search — Tavily (primary) + DuckDuckGo (fallback):**
NVIDIA NIM does not provide a built-in web search tool (unlike Anthropic API).
Tavily is purpose-built for AI agents with a Python SDK, 1,000 free queries/month,
and returns structured, LLM-ready content. If Tavily is unavailable or rate-limited,
the tool falls back to DuckDuckGo (`duckduckgo_search` library) which requires no
API key. M and X agents use this unified `web_search` wrapper; their prompts do not
need to distinguish between the two backends.

**Why a shared tools module:**
Consistent data format across all X agents. If Alpha Vantage changes its response
schema, one file changes — not every researcher agent prompt. Also makes unit
testing straightforward: mock the tools module, test agent logic independently.

---

### State Management — In-Memory + Per-Run Folder Persistence

**No database.** State is managed in three ways:

1. **In-memory during a run:** The orchestrator holds the full agent state dict
   (phase, task queue, research cache, outputs) in a Python object for the duration
   of the run. This is sufficient — runs are synchronous from the backend's perspective.

2. **Per-run folder persistence (RunLogger):** Every agent call during a run is
   automatically saved to a dedicated folder on disk via `backend/run_logger.py`:
   ```
   backend/runs/
   └── 2026-06-03T14-32-00_abc123/
       ├── _meta.json                  # Run metadata (budget, date, run_id)
       ├── 001_M_macro.json            # Full LLM prompt + response + parsed result
       ├── 001_M_macro_summary.txt     # Human-readable summary of the same call
       ├── 002_B_planning.json
       ├── 003_X1_research.json
       ├── ...
       ├── _final_portfolio.json       # Final portfolio output
       └── _m_updates.json             # M-update changelog
   ```
   Each JSON file contains the full system prompt, user message, raw LLM response,
   parsed result, and optional detail payload (for collapsible UI rendering).
   Summary text files provide a human-readable excerpt of each call.

3. **Run result JSON:** After a run completes, a summary JSON file is also saved
   to `backend/runs/{timestamp}_JPY{budget}.json` for the Past Runs list in the UI.

**Resume from saved run:**
The orchestrator can rebuild its full state from a saved run folder:
- `Orchestrator.from_run_folder(folder_path)` scans all `NNN_agent_phase.json`
  files in sequence, restores the outputs dict, research cache, M-update count,
  and determines the next phase to execute.
- The backend exposes `POST /api/run/resume` accepting `{folder: "..."}`.
- The React UI provides a "Resume from Folder" text input and button in the
  RunForm component.

**Why no database for a PoC:**
SQLite or Postgres would add setup complexity with no meaningful benefit at this
scale. JSON files are human-readable, trivially backed up, and sufficient for
run history and resume. Migrating to a database is straightforward if the project grows.

---

### Streaming — Server-Sent Events (SSE)

The backend streams agent status updates to the React UI in real time using SSE.
Each event is a small JSON payload:

```json
{ "agent": "X1", "status": "working", "message": "Fetching EDGAR 10-K for NVDA" }
{ "agent": "X1", "status": "done", "message": "Returned: NVDA, confidence high" }
{ "agent": "C",  "status": "working", "message": "Round 1 critique in progress" }
```

**Detail events for collapsible UI:**
In addition to status events, agents emit `detail` events containing rich payloads
(macro briefs, research plans, B/C/D debate contents) that the frontend renders
inside `DetailCollapsible` components — expandable `<pre>` blocks toggled by the user:

```json
{ "agent": "M", "status": "detail", "detail": { "fed_policy": "...", "boj_policy": "..." } }
{ "agent": "B", "status": "detail", "detail": { "tasks": [...], "fx_rate": "145.0" } }
```

The `ActivityFeed` component groups each detail event with the preceding status
event, so macro briefs, research plans, and critique arguments appear as collapsible
sections attached to the relevant agent status line.

**Why SSE over WebSockets:**
SSE is unidirectional (server → client), which is all that's needed here — the UI
displays what the backend is doing, it doesn't send messages back mid-run. SSE is
simpler to implement, natively supported by browsers, and FastAPI has built-in support
via `EventSourceResponse`. WebSockets would add complexity for no benefit.

---

### Configuration — `.env` File

All API keys and tunable parameters live in a single `.env` file at the project root:

```env
# API Keys (multiple NIM keys separated by commas for rotation on retry)
NVIDIA_NIM_API_KEY=nvapi-key1,nvapi-key2,nvapi-key3
TAVILY_API_KEY=tvly-...
ALPHA_VANTAGE_API_KEY=...
POLYGON_API_KEY=...
FRED_API_KEY=...
EDINET_API_KEY=...

# NIM configuration
NIM_BASE_URL=https://integrate.api.nvidia.com/v1
NIM_MODEL=deepseek-ai/deepseek-v4-pro

# Agent parameters
MAX_RESEARCHERS=6
CRITIQUE_ROUNDS=3
```

**Why NVIDIA API key can be a comma-separated list:**
NVIDIA NIM free-tier accounts have per-key rate limits. If a single key exhausts
its capacity (HTTP 429), the `call_llm` function cycles to the next key in the
list on each retry attempt. This distributes requests across multiple keys and
reduces throttling. The rotation is logged per-attempt in the server logs.

**Why NVIDIA API key replaces ANTHROPIC_API_KEY:**
All model inference goes through NVIDIA NIM's OpenAI-compatible endpoint.
The `NVIDIA_NIM_API_KEY` is used as a Bearer token in the `Authorization` header
by the OpenAI SDK client. `TAVILY_API_KEY` is required for web search (free tier:
1,000 queries/month at app.tavily.com).

Budget and purchase date are **not** in `.env` — they are runtime parameters passed
per run via the UI. Everything in `.env` is system-wide configuration that doesn't
change between runs.

---

## 3. Project Structure

```
stock-agent/
│
├── .env                        # API keys and system config (not committed)
├── start.sh                    # Starts MCP servers + backend + opens browser
├── requirements.txt            # Python dependencies
│
├── backend/
│   ├── main.py                 # FastAPI app, SSE endpoint, run trigger + resume
│   ├── orchestrator.py         # Agent A logic: phase control, dispatch, state, resume
│   ├── run_logger.py           # Per-run disk persistence and resume helpers
│   ├── agents/
│   │   ├── _base.py            # Shared: call_llm (rate-limit, backoff, key rotation), extract_json, build_agent_prompt
│   │   ├── macro.py            # Agent M
│   │   ├── portfolio.py        # Agent B
│   │   ├── researcher.py       # Agent X (parametric — one function, many instances)
│   │   ├── critic.py           # Agent C
│   │   └── tiebreaker.py       # Agent D
│   ├── tools/
│   │   ├── fred.py
│   │   ├── edgar.py
│   │   ├── edinet.py
│   │   ├── alpha_vantage.py
│   │   ├── polygon.py
│   │   ├── yfinance_client.py
│   │   └── web_search.py
│   ├── runs/                   # Auto-created; stores per-run folders with agent call logs
│   └── logs/                   # Auto-created; server.log (DEBUG level)
│
└── frontend/
    ├── index.html
    ├── package.json
    └── src/
        ├── App.jsx             # Root layout: left panel + right panel, resume handler
        ├── RunForm.jsx         # Budget + date + resume folder input, Run + Resume buttons
        ├── ActivityFeed.jsx    # SSE consumer, live agent status, collapsible detail sections
        ├── PortfolioTable.jsx  # Final portfolio rendering
        └── RunHistory.jsx      # Past runs list from /runs endpoint
```

---

## 4. Local Development Setup

```bash
# 1. Clone and set up Python environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 2. Install MCP servers
uvx install sec-edgar-mcp
uvx install edinet-mcp

# 3. Configure environment
cp .env.example .env
# Fill in API keys in .env

# 4. Install frontend dependencies
cd frontend && npm install && cd ..

# 5. Start everything
./start.sh
# Opens http://localhost:5173 in browser
# Backend runs on http://localhost:8000
```

`start.sh` does the following in order:
```bash
#!/bin/bash
uvx sec-edgar-mcp &
uvx edinet-mcp &
uvenv python backend/main.py &
cd frontend && npm run dev
```

---

## 5. Key Dependencies

### Python
| Package | Purpose |
|---------|---------|
| `openai` | OpenAI SDK — NIM's chat completions API client |
| `fastapi` | Backend web framework |
| `uvicorn` | ASGI server for FastAPI |
| `sse-starlette` | SSE support for FastAPI |
| `fredapi` | FRED macro data client |
| `yfinance` | Yahoo Finance / TSE price data |
| `edinet-tools` | EDINET XBRL filing client |
| `sec-api` | SEC EDGAR filing client |
| `polygon-api-client` | Polygon.io client |
| `alpha_vantage` | Alpha Vantage client |
| `tavily-python` | Web search for AI agents (primary) |
| `duckduckgo_search` | Web search fallback (no API key needed) |
| `python-dotenv` | `.env` file loading |
| `pandas` | Data wrangling for financial outputs |

### Node / Frontend
| Package | Purpose |
|---------|---------|
| `react` + `react-dom` | UI framework |
| `vite` | Local dev server and build tool |
| `@tanstack/react-query` | Data fetching and cache for run history |

### MCP Servers (installed via uvx, not pip)
| Package | Purpose |
|---------|---------|
| `sec-edgar-mcp` | EDGAR filings → structured agent-ready data |
| `edinet-mcp` | EDINET XBRL filings → structured agent-ready data |

---

## 6. Decisions Made

The following decisions were resolved during the setup phase and are now settled:

1. **Model provider:** NVIDIA NIM with `deepseek-ai/deepseek-r1`. Replaces the originally
   planned `claude-sonnet-4-20250514` via Anthropic API. All agent calls use the OpenAI
   Python SDK against NIM's OpenAI-compatible endpoint at `https://integrate.api.nvidia.com/v1`.

2. **Web search:** Tavily (primary) + DuckDuckGo (fallback). Tavily provides structured,
   LLM-ready search results with 1,000 free queries/month. DuckDuckGo requires no API key
   and serves as a zero-cost fallback when Tavily is rate-limited or unavailable.

3. **Alpha Vantage vs. Polygon.io as primary US price source:**
   Both serve overlapping purposes. Alpha Vantage has a more generous free tier
   (500 req/day vs Polygon.io's limited free tier) but slower response times.
   Polygon.io has better real-time data but costs more. Decision can be deferred
   to implementation — the tools module abstracts the choice from agents.

4. **Run concurrency:**
   For a PoC, one run at a time. Multiple runs would require run-scoped state isolation.

5. **Frontend build for distribution:**
   For personal reuse, `npm run dev` is fine. Not a PoC concern.
