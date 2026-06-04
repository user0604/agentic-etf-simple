# Multi-Agent Stock Portfolio System — Architecture Design

> **Purpose:** PoC for an AI-driven stock purchase planner.  
> **Input parameters:** Budget (e.g. ¥1,000,000), purchase date (e.g. June 9, 2026)  
> **Output:** A ranked, allocated portfolio of US/Japan stocks optimized for 5-year return

---

## 1. System Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                           A — Orchestrator                            │
│          (event-driven supervisor, quality gate, phase manager)       │
└───────┬──────────────────────────────────────────────┬───────────────┘
        │ dispatches                                   │ monitors all signals
        ▼                                             ▼
┌───────────────┐                      ┌──────────────────────────┐
│  M — Macro    │◄─── update signal ───│  B — Portfolio Manager   │◄────────────┐
│    Agent      │◄─── update signal ───│   (proposer/optimizer)   │             │
└───────┬───────┘◄─── update signal ───│                          │             │ revises after
        │ macro brief                  └────────────┬─────────────┘             │ each round
        │ (reruns when updated)                     │ issues + approves         │
        ▼                                           │ research plans            │
                             ┌─────────────────────────────────────┐            │
                             │         X1 … Xn — Researchers       │            │
                             │  plan → B approval → execute        │            │
                             │       (pseudo-parallel batch)        │            │
                             └─────────────────────────────────────┘            │
                                                                                │
                             ┌─────────────────────────────────────┐            │
                             │          C — Critic Agent            │────────────┘
                             │   (3 rounds, escalating, stateful)  │
                             └─────────────────────────────────────┘
                                            │ stalemate
                                            ▼
                             ┌─────────────────────────────────────┐
                             │          D — Tie-breaker             │
                             │  (triggered automatically by A)     │
                             └─────────────────────────────────────┘
```

**Full workflow:**

```
Phase 1 — MACRO
  A triggers M → M produces macro brief

Phase 2 — PLANNING
  A activates B with macro brief
  B defines research tasks (industries, themes, budget targets, FX rate)

Phase 3 — RESEARCH (per batch)
  A dispatches research briefs to X agents
  Each X submits research plan → B reviews and approves/rejects → X executes
  X agents run pseudo-parallel within each batch
  A deduplicates outputs across agents before forwarding to B
  B may dispatch additional X batches if gaps remain after reviewing results

Phase 4 — DRAFT
  B constructs draft portfolio using confidence-weighted scoring
  B declares FX rate (derived from M's brief) — applied uniformly to all tickers

Phase 5 — CRITIQUE LOOP (up to 3 rounds, one exchange per round)
  Round 1: C critiques internal consistency (one killer argument)
           B revises with explicit reasoning
           A validates B's response is substantive
  Round 2: C must first explicitly confirm Round 1 issues are resolved,
           then critiques the biggest thesis assumption
           B revises with explicit reasoning
  Round 3: C must first explicitly confirm Rounds 1–2 issues are resolved,
           then raises missed opportunities
           B revises with explicit reasoning
           C issues final sign-off: confirms all prior issues resolved AND
           raises no new objection → consensus reached → proceed to Phase 6
  If C cannot sign off after Round 3: A triggers D

  Consensus rule: C's Round 3 final response explicitly confirms all prior
  rounds resolved AND raises no new objection after B's Round 3 revision.
  A detects consensus by parsing C's status signal (see Section 5).

Phase 5b — TIE-BREAK (if needed)
  D receives strongest argument from B + strongest from C
  D issues verdict: who revises, and what specifically must change
  B or C revises per verdict → loop ends

Phase 6 — FINAL
  A collects final portfolio and renders output with full audit trail

M-UPDATE (can interrupt Phases 2–5)
  Signal from B, C, or D → A triggers M update
  M documents exactly what changed and why previous version was insufficient
  A restarts from Phase 2 (B re-plans), keeping all cached X research results
  Critique loop restarts from Round 1 after each M-update
  A maintains M-update changelog in output
```

---

## 2. Agent Definitions

### A — Orchestrator
**Role:** Project manager, event-driven dispatcher, quality gate, and phase controller.

**Responsibilities:**
- Maintains task queue and agent state map (see Section 3)
- On each agent completion event: checks for idle agents + available matching tasks → dispatches
- Enforces phase ordering — no agent can act outside its valid phase
- Validates researcher outputs before forwarding to B (minimum bar: has ticker, has thesis, has fully populated scenario schema)
- Enforces B's responses to C are substantive — not just acknowledgment
- Automatically triggers D if B and C have not converged after Round 3
- Deduplicates researcher outputs: if multiple X agents return the same ticker, A merges into one entry (keeping the richer schema) before passing to B
- Listens for M-update signals from B, C, or D — triggers M, then restarts from Phase 2 with research cache intact
- Maintains M-update changelog across the session

**Why event-driven, not timer-based:**  
Polling adds latency and wastes compute. Each agent ends its output with a structured status signal (Section 5) that A parses to update state and decide next action. The system is naturally self-pacing — fast agents immediately pick up queued work.

**Why A deduplicates (not B):**  
B's job is allocation, not data hygiene. If B receives two entries for NVDA — one from a US tech researcher and one from a US AI researcher — it could double-count budget or treat duplication as a stronger signal. Neither is correct. A cleaning the data before B sees it keeps B's logic uncontaminated. Duplication of search coverage does not imply better risk/return.

**Why A triggers D automatically (not B or C self-reporting stalemate):**  
Self-reporting failure creates an incentive problem — neither B nor C wants to concede. A counting rounds objectively removes that incentive and makes stalemate detection deterministic.

**Why A feeds X plans to B sequentially (not batched):**  
B reviews one research plan at a time, in the order X agents submit them. This allows B to adjust its approval criteria based on what earlier plans are already covering — e.g. if X1's plan heavily covers US large-cap growth, B can redirect X2 away from overlap before it executes. Batching would be faster but would lose this adaptive steering capability.

---

### M — Macro Agent
**Role:** Establishes and maintains the global investment context.

**Responsibilities:**
- Assess current macro environment: US Fed and Bank of Japan policy, USD/JPY trend, inflation, recession risk indicators, geopolitical factors relevant to a 5-year horizon
- Recommend US vs. Japan weighting rationale
- Identify macro tailwinds and headwinds by sector
- Produce a macro brief consumed by B and all X agents as shared context
- On update: document exactly what changed, what new information prompted the update, and why the previous version was insufficient

**Why M can be re-triggered mid-workflow:**  
If B, C, or D identifies that the portfolio rests on a macro assumption M never addressed or got wrong, all downstream work is compromised. Correcting M and re-running B's plan (while keeping X's research cache) is cheaper than producing a flawed final output. Fixing premises is always worth the cost.

**Why there is no hard cap on M updates:**  
A properly executed M should not need frequent correction — researchers find micro-level stock facts, not macro contradictions. In practice, M being triggered more than twice signals either a poor initial M run or a genuinely volatile macro environment, both of which are worth surfacing in the audit trail rather than suppressing with an arbitrary limit.

**Why M is separate from B:**  
Macro analysis and portfolio construction are distinct cognitive tasks. Merging them into one agent empirically degrades output quality on both — LLMs perform better with narrower, well-defined roles.

**Why X agents cannot trigger M updates:**  
Researchers operate at the micro level (individual stock fundamentals). A finding that, say, a specific company has weaker earnings than expected is not a macro signal. Allowing X agents to trigger M updates would risk conflating security-level findings with macro thesis changes, creating noise. Only B, C, and D — agents that reason at the portfolio level — have the context to identify genuine macro gaps.

---

### B — Portfolio Manager
**Role:** The strategic brain. Plans research, constructs the portfolio, defends and revises it through critique.

**Responsibilities:**
- Given M's macro brief, define research tasks: industries, themes, geographic split, budget targets per theme
- Declare the FX rate (USD/JPY) to be used uniformly across all tickers, derived from M's brief
- Review each X agent's research plan before execution — approve or reject with specific feedback
- Receive deduplicated, validated researcher outputs from A and construct draft portfolio
- Apply confidence-weighted scoring formula (Section 6) and document any deviations with explicit reasoning
- Dispatch additional X batches if research gaps remain
- Revise portfolio after each critique round with explicit reasoning (not just acknowledgment)
- Signal A if M update is needed, with specific justification
- After M update: revise plan, identify new research gaps, dispatch additional X agents if needed; reuse all prior research results

**Why B reviews X's research plan before execution:**  
A researcher that misunderstands its brief will return useless results. Early plan review by B — before the researcher expends effort — catches misalignment cheaply. It also gives B visibility into what angle each researcher is taking, preventing unintentional duplication of scope.

**Why B dictates the FX rate (not each researcher independently):**  
If each researcher uses its own USD/JPY assumption, B's scoring formula becomes incoherent — comparing a US stock's return estimated at ¥145/$ against a Japan stock estimated at ¥150/$ is an apples-to-oranges comparison. A single B-declared rate makes all estimates commensurable.

**Why B keeps prior research after M update:**  
M updating its macro brief does not invalidate a researcher's finding that, say, a specific Japanese industrial company has strong order books. The facts remain; what changes is B's interpretation and weighting of those facts. Discarding and re-running all research would waste significant time and cost for no benefit.

**Why B's critique responses must be substantive:**  
A checks this explicitly. If B can simply say "acknowledged, adjusted" without reasoning, C's critique rounds become a rubber stamp. Requiring explicit reasoning forces genuine engagement and makes the revision auditable.

---

### X — Researcher Agents (X1…Xn)
**Role:** Domain specialists. Each scoped to one industry, theme, or geography.

**Two-phase execution:**

```
Phase A — Plan submission
  X receives brief from A (industry/theme, budget range, macro context, FX rate, existing portfolio state)
  X produces research plan: intended sources, candidate screening criteria, approach
  X submits plan to B via A for approval

Phase B — Execution (after B approval)
  X executes research using web search and financial data APIs
  X populates ticker evaluation schema for top 1–2 candidates
  X submits results with status signal to A
  X may include follow-up research requests if gaps were found
```

**Why plan approval before execution:**  
Catching a misaligned research angle before execution is far cheaper than discarding completed research. It also gives B strategic visibility into the research effort — B can redirect scope ("focus on value, not growth plays") before effort is wasted.

**Why each researcher is scoped to one industry/theme:**  
Narrow scope produces deeper, less obvious results. A researcher asked "find the best stock globally" anchors on widely-known names. One asked "find the best Japanese defensive consumer stock given JPY strengthening trend and Bank of Japan rate normalization" will surface genuinely differentiated candidates.

**Why researchers share a common tool layer:**  
Embedding API call logic in each agent's prompt creates inconsistency and makes bugs hard to trace. A shared tool layer (web search and financial data API wrappers — see `data-sources.md`) called uniformly ensures consistent data format and simpler debugging.

**Why X agents cannot trigger M updates:**  
See M section above. Micro-level findings do not constitute macro signals.

**Why identical plans after M-update reuse cached results (not re-dispatch):**  
When B re-plans after an M-update and dispatches new X agents, A compares each plan's hash against the research cache. If the plan is unchanged, the research scope is unchanged — re-running it would produce the same output at unnecessary cost. A short-circuits dispatch and marks `cache_hit: true`. Only new or modified plans go through B review and fresh execution. This gives B full strategic oversight without penalizing the common case where M's update doesn't affect a particular research scope.

---

### C — Critic Agent
**Role:** Designated devil's advocate. Stateful across rounds and M-update restarts.

**Why one exchange per round (not open-ended back-and-forth):**  
This mirrors professional investment committee practice. In real committees, the critic prepares a written challenge in advance, the PM defends or concedes in one session, and the chair calls it resolved or not — then both parties go away before the next topic. Open-ended within-session back-and-forth tends to devolve into positional arguing rather than considered revision. The clean break between rounds produces more disciplined responses from B and a cleaner audit trail. This is how credit committees and risk review boards operate.

**Why one killer argument per round (not a checklist):**  
A checklist critic produces minor issues B can address superficially. A single, sharp argument forces genuine strategic revision. This mirrors how real investment committees use a devil's advocate role.

**Why C is stateful (remembers prior arguments):**  
On M-update restart, the critique loop resets to Round 1 — but C should not re-raise issues B has already adequately addressed. C's memory of prior rounds prevents wasted rounds re-litigating settled points and forces C to focus on what the macro update specifically changes about its previous assessment.

**Three escalating challenge types:**

| Round | Focus | What C attacks | C's obligation before raising new argument |
|-------|-------|---------------|-------------------------------------------|
| **1 — Internal Consistency** | Concentration risk, holding correlations, currency imbalance, budget arithmetic | The portfolio's internal coherence | None (first round) |
| **2 — Thesis Stress Test** | The single biggest macro assumption B is making | M's brief, B's FX rate, the confidence weights | Must explicitly confirm Round 1 is resolved |
| **3 — Missed Opportunities** | What is entirely absent | Unrepresented sectors, geographies, or risk profiles | Must explicitly confirm Rounds 1–2 are resolved |

**Consensus rule:**  
After B's Round 3 revision, C issues a final response. Consensus is reached if and only if C explicitly confirms all prior rounds resolved AND raises no new objection. A parses C's status signal to detect this — C does not self-declare "consensus," it signals `"satisfied": true` in its status block, which A reads as the consensus trigger.

**Why this ordering:**  
Internal errors must be fixed before stress-testing assumptions — a portfolio with a budget arithmetic error is not worth stress-testing. Assumptions must be stress-tested before asking what's missing — adding new holdings to a fragile thesis compounds the fragility.

**Why C sees only B's draft (not raw researcher outputs):**  
C's role is to critique the portfolio decision, not audit the research process. If C had raw researcher access, it would effectively become a second B — second-guessing allocation rather than stress-testing the portfolio as a whole. The separation keeps roles clean.

**On M-update restart:**  
C restarts at Round 1 but carries its full argument history. Its instruction explicitly states: *do not re-raise issues B has already addressed — focus on what the macro update changes about your prior assessment.*

---

### D — Tie-breaker Agent
**Role:** Renders a binding verdict when B and C cannot reach consensus after Round 3.

**Trigger:** Automatically by A after Round 3 completes without convergence. Not self-reported by B or C.

**Inputs:** D receives only:
- B's strongest argument for its current portfolio position
- C's strongest argument against it

D does not receive the full conversation history. This is intentional — D judges argument quality, not persistence or volume.

**Output:**
```
Verdict:         [B revises | C revises | both partially revise]
Reasoning:       [which argument was stronger, and specifically why]
Required change: [concrete, specific instruction to the revising party]
```

**Why D is stateless per invocation:**  
If D had access to the full B/C exchange, it could be swayed by who argued more extensively rather than who argued more correctly. Receiving only the strongest argument from each side forces D to evaluate logical merit alone.

**Why D can also trigger M update:**  
A stalemate between B and C sometimes reveals a disputed macro fact that neither can resolve — because M's brief was ambiguous or incomplete. D is in the best position to identify this, having seen both sides' strongest arguments. Giving D the ability to signal M update rather than forcing an arbitrary verdict produces a better outcome.

---

## 3. Event-Driven Orchestration State

A maintains this structure at all times, persisted to disk via RunLogger (see Section 8):

```json
{
  "phase": "macro | planning | research | draft | critique_1 | critique_2 | critique_3 | tiebreak | final",
  "m_update_count": 0,
  "m_update_changelog": [],
  "agents": {
    "M": "idle | working | done",
    "B": "idle | plan_review | working | done",
    "X1": "idle | plan_submitted | plan_approved | working | done",
    "C": "idle | working | done",
    "D": "idle | working | done"
  },
  "research_cache": {
    "japan_industrials": { "ticker": "...", "schema": {} },
    "us_semiconductors":  { "ticker": "...", "schema": {} }
  },
  "task_queue": [
    { "task": "research_japan_defensive", "assigned_to": null, "status": "pending" }
  ],
  "dedup_log": ["NVDA appeared in X1 and X3 — merged, X1 schema used as richer source"],
  "outputs": {
    "macro_brief": null,
    "portfolio_draft": null,
    "critique_1": null,
    "critique_2": null,
    "critique_3": null,
    "tiebreak_verdict": null,
    "portfolio_final": null
  }
}
```

**Key state additions vs. earlier version:**
- `m_update_count` and `m_update_changelog`: full audit trail of every M update
- `plan_submitted` / `plan_approved` states for X agents: tracks B's review gate
- `research_cache`: persists across M-update restarts; keyed by topic not agent ID
- `dedup_log`: records every deduplication decision A made, for auditability

**Dispatch rule:**  
On every agent completion event:  
`if agent.status == "done" AND task_queue has unassigned task matching agent.capability AND phase allows it → dispatch`

---

## 4. Ticker Evaluation Schema (Researcher Output)

Every researcher must return this structure for each candidate ticker. Incomplete schemas are rejected by A and returned for completion before B sees them.

```
Ticker:             [symbol + exchange]
Industry:           [sector + sub-sector]
Thesis:             [2–3 sentence investment case]
FX rate used:       [must match B's declared rate]

Bull case:          [what must go right | estimated 5yr upside %]
Base case:          [most likely outcome | estimated 5yr return %]
Bear case:          [what kills the thesis | estimated downside %]

Confidence:         [low | medium | high]
Confidence reason:  [explicit justification — not just "strong fundamentals"]

Known catch:        [the specific flaw or risk identified]
Catch severity:     [how much it narrows the bull case, and why]

Data sources:       [list of sources used]
```

**Why the schema includes FX rate used:**  
A can verify that each researcher applied B's declared rate. Any mismatch is caught before B's scoring runs, preventing silent comparability errors.

**Why "good buy" is not a field:**  
There is no objective measure to compare a catch against cheapness. The schema makes subjectivity visible and consistent — B computes a score from it, C attacks the score's assumptions, D arbitrates if needed. The debate *is* the evaluation process; a single verdict field would short-circuit it.

**Why confidence must have an explicit reason:**  
"High confidence" without justification is noise that B cannot act on and C cannot attack. Explicit reasoning surfaces the actual basis of conviction, making it debatable.

---

## 5. Agent Communication Protocol

Each agent ends its output with a structured status block that A parses. Blocks are agent-type-specific but share a common `m_update_signal` field.

**X agent (researcher):**
```json
{
  "agent": "X1",
  "status": "done | needs_retry | blocked | plan_submitted",
  "output_key": "japan_industrials",
  "plan_hash": "abc123",
  "cache_hit": false,
  "quality_issues": [],
  "follow_up_requests": [
    { "task": "research_japan_defensive", "reason": "sector too thin — no quality candidates found at target budget" }
  ],
  "m_update_signal": { "triggered": false, "reason": null }
}
```

**C agent (critic):**
```json
{
  "agent": "C",
  "status": "done",
  "round": 2,
  "prior_rounds_resolved": true,
  "satisfied": false,
  "m_update_signal": { "triggered": false, "reason": null }
}
```

**B and D agents:**
```json
{
  "agent": "B",
  "status": "done",
  "m_update_signal": { "triggered": false, "reason": null }
}
```

**Why `m_update_signal` is in every agent's status block:**  
Any of B, C, or D may identify a macro gap at any point. Standardizing the signal field means A's parsing logic is uniform — it checks the same field regardless of which agent fired.

**Why `satisfied` is a signal field (not a natural language declaration):**  
A detects consensus by reading `C.satisfied == true` after Round 3, not by parsing C's prose. This makes consensus detection deterministic and unambiguous — C cannot accidentally or implicitly trigger it mid-argument.

**Why `prior_rounds_resolved` is explicit:**  
A uses this to enforce the escalation rule — C cannot raise a Round 2 argument if it signals `prior_rounds_resolved: false`. This structurally prevents C from skipping round types or revisiting settled issues without flagging it explicitly.

**Why `plan_hash` is in X's status block:**  
After an M-update, A compares each new X plan's hash against the research cache keys. An identical hash means the plan is unchanged — A short-circuits dispatch and marks `cache_hit: true`, reusing the prior result without re-running the researcher.

**Why follow-up requests are agent-initiated (for X agents):**  
Researchers may discover mid-task that a sector is too thin or that a promising lead requires adjacent research. Allowing X to request follow-up tasks — which A queues and B approves — produces a more adaptive system than a rigid pre-planned task list.

---

## 6. Portfolio Scoring (B's Allocation Logic)

B ranks all deduplicated tickers using a confidence-weighted return score:

```
Score = (base_case_return × confidence_weight) − (bear_case_downside × (1 − confidence_weight))
```

| Confidence | Weight |
|------------|--------|
| High       | 0.7    |
| Medium     | 0.5    |
| Low        | 0.3    |

**Why these weights are deliberately arbitrary:**  
Their value is consistency, not precision. Every ticker is judged by the same formula, making relative rankings meaningful even if absolute numbers are not trustworthy. B must document any deviation from formula-based ranking with explicit reasoning.

**Why C is told the weights exist:**  
In Round 2, C's job is to attack B's biggest assumption. The confidence weights are the most consequential hidden assumption in the system. Making them explicit to C ensures they get stress-tested rather than taken for granted.

**Budget allocation after scoring:**  
B allocates budget proportionally to score, subject to constraints it defines in its plan (e.g. no single ticker > 25% of budget, at least 3 industries represented, US/Japan balance within M's recommended range). Constraint violations must be documented with reasoning.

---

## 7. M-Update Protocol

When B, C, or D signals an M update:

```
1. A pauses current phase
2. A triggers M with: current macro brief + the specific gap or error identified + signalling agent's reasoning
3. M produces updated brief, documenting:
   - What changed
   - What new information or identified gap prompted the change
   - Why the previous version was insufficient
4. A appends update to m_update_changelog
5. A activates B with updated macro brief + full research cache
6. B revises its plan; dispatches new X agents if gaps identified
7. Critique loop restarts from Round 1
8. C receives updated macro brief + its full prior argument history
   C instruction: do not re-raise resolved issues; focus on what the macro update changes
```

**Why no hard cap on M updates:**  
A properly executed M should not require frequent correction — researchers find security-level facts, not macro contradictions. If M is being corrected repeatedly, that itself is a signal worth surfacing (poor initial M run, or genuinely volatile macro environment). The audit trail in `m_update_changelog` makes this visible without suppressing potentially valid corrections with an arbitrary limit.

**Why the critique loop restarts from Round 1 after M update:**  
C's Round 1 (internal consistency) conclusions may change after B revises its plan. Skipping to Round 2 or 3 could miss newly introduced inconsistencies in B's revised portfolio.

---

## 8. Persistence and Resume

Every agent interaction during a run is automatically persisted to disk, enabling
full audit trails and the ability to resume a run from any point.

### Per-Run Folder Layout

Each run creates a timestamped folder in `backend/runs/`:

```
backend/runs/
└── 2026-06-03T14-32-00_abc123/
    ├── _meta.json                  # Run metadata (budget, date, run_id, started_at)
    ├── 001_M_macro.json            # Full LLM prompt + response + parsed result
    ├── 001_M_macro_summary.txt     # Human-readable excerpt of the call
    ├── 002_B_planning.json
    ├── 003_X1_research.json
    ├── ...                         # One JSON per agent call, sequenced by call order
    ├── _final_portfolio.json       # Final portfolio output (holdings, audit trail)
    └── _m_updates.json             # M-update changelog (each update with reason + phase)
```

Each JSON file contains:
- `sequence`, `agent`, `phase` — identity metadata
- `system_prompt` / `user_message` / `response_text` — the full LLM exchange
- `parsed_result` — the structured JSON output the agent returned
- `detail` — optional rich payload for collapsible UI rendering

Summary `.txt` files provide truncated excerpts of each call for quick scanning.

### RunLogger Implementation

The `RunLogger` class (`backend/run_logger.py`) is initialized by the orchestrator
at run start:

```python
from backend.run_logger import RunLogger
self._logger = RunLogger(run_id, budget, purchase_date)
```

The orchestrator's `_call_agent` method calls `logger.log_call()` after every
agent invocation, popping internal fields (`_prompt`, `_user_message`, `_response_text`,
`_detail`) from the result dict before persisting. Additional methods:
- `save_final_portfolio()` — called during Phase FINAL
- `save_m_update_changelog()` — called during Phase FINAL

### Resume From Saved Run

The system can resume a run from any saved folder, continuing from the last
completed phase:

1. **`Orchestrator.from_run_folder(folder_path)`** — classmethod that:
   - Loads `_meta.json` for budget, date, run_id
   - Scans all `NNN_agent_phase.json` files in sequence order
   - Rebuilds `outputs` dict (macro_brief, research_tasks, portfolio_draft, etc.)
   - Restores `research_cache` from researcher call logs
   - Restores `m_update_count` and `m_update_changelog`
   - Determines next phase from the last completed phase:
     `macro → planning → research → draft → critique_1 → critique_2 → critique_3 → tiebreak → final`

2. **`POST /api/run/resume`** — FastAPI endpoint accepting `{folder: "..."}`.
   Returns `{run_id, resumed_from, phase}` and sets up SSE streaming for the
   resumed run.

3. **Resume UI** — RunForm.jsx includes a "Run Folder Path" text input and
   "Resume from Folder" button, wired to the App.jsx `handleResume` callback.

### Why Persist Every Call (Not Just the Result)

- **Audit trail:** Every prompt, response, and parsed output is preserved —
  no black-box agent decisions. Useful for debugging, refinement, and trust.
- **Resume fidelity:** The full state can be reconstructed from disk without
  relying on in-memory state that may be lost on server restart.
- **Retry resilience:** If a run fails mid-pipeline, the user can inspect the
  saved folder, fix the underlying issue, and resume without losing prior work.
- **Human review:** Summary text files allow quick scanning of agent outputs
  without opening JSON or digging through the UI.


