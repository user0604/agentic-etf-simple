# Data Sources — Multi-Agent Stock Portfolio System

> This document is standalone and referenced by `stock-agent-architecture.md`.  
> It lists all data sources available to the agent system, with access method, coverage, cost, and assigned agent(s).

---

## 1. Active Sources

### Macro & Economic Data

| Source | Data type | Used by | Access method | Cost |
|--------|-----------|---------|---------------|------|
| FRED (Federal Reserve Economic Data) | Interest rates, inflation, GDP, FX, employment | M | Official REST API | Free |
| Web search (Anthropic API built-in) | News, analyst articles, macro commentary | M, X | API (built-in) | Included |

**Why FRED over web search alone for macro data:**  
FRED is the authoritative primary source for US macro indicators, maintained by the St. Louis Fed. It covers 800,000+ time series including Fed funds rate, CPI, GDP, and USD/JPY — precisely what M needs to set macro context. Web search retrieves commentary about macro data; FRED retrieves the data itself. Both are needed: FRED for structured facts, web search for interpretation and Bank of Japan context (which FRED does not cover).

---

### US Equities — Fundamentals & Qualitative Research

| Source | Data type | Used by | Access method | Cost |
|--------|-----------|---------|---------------|------|
| SEC EDGAR | 10-K/10-Q filings, insider trading (Form 4), institutional holdings (13F), earnings | X | Official REST API (`data.sec.gov`) + `sec-edgar-mcp` MCP server | Free |
| Alpha Vantage | Prices, fundamentals, earnings estimates | X | Official REST API | Free tier / paid |
| Polygon.io | Historical OHLCV, financials, real-time quotes | X | Official REST API | Free tier / paid |
| Motley Fool | Stock Advisor picks and investment reasoning | X | Web search (no API) | Via membership |

**Why EDGAR is the primary US fundamental source:**  
EDGAR is the authoritative origin — all US public companies file directly with the SEC. Alpha Vantage and Polygon.io derive their fundamental data from EDGAR anyway, adding latency and potential transcription errors. For deep due diligence (10-K risk factors, insider selling via Form 4, 13F institutional concentration), direct EDGAR access is essential. Alpha Vantage and Polygon.io remain useful for price history and quick lookups without implementing EDGAR parsing.

**Why Alpha Vantage and Polygon.io alongside EDGAR:**  
EDGAR is filing-centric — retrieving structured time-series price data or earnings estimates requires more work than a direct API call to Alpha Vantage or Polygon.io. The two serve complementary roles: EDGAR for primary-source depth, Alpha Vantage/Polygon.io for price and quantitative series.

**Why Motley Fool via web search:**  
No official API exists and scraping is against ToS. Web search retrieves the same editorial content — current Stock Advisor picks, analyst reasoning, and investment theses — without brittle infrastructure. Treated as one qualitative input among many, not a primary data source.

---

### Japan Equities — Fundamentals & Price Data

| Source | Data type | Used by | Access method | Cost |
|--------|-----------|---------|---------------|------|
| EDINET (FSA) | Annual securities reports, quarterly filings, large shareholding reports (XBRL) | X | Official REST API (`api.edinet-fsa.go.jp`) + `edinet-mcp` MCP server | Free (API key, no approval process) |
| Yahoo Finance (yfinance) | TSE price history, basic fundamentals, broad coverage | X | Python library | Free |

**Why EDINET is the primary Japan fundamental source:**  
EDINET is Japan's equivalent of SEC EDGAR — operated by the Financial Services Agency, it contains every annual and quarterly securities report filed by TSE-listed companies. The v2 API (launched April 2024) provides free programmatic access with XBRL parsing, normalised across J-GAAP, IFRS, and US-GAAP. This is authoritative primary-source data. yfinance remains useful for price history and quick lookups, but EDINET is the source of record for Japan fundamentals.

**Why `edinet-mcp` is significant:**  
The `edinet-mcp` MCP server parses EDINET XBRL filings into structured DataFrames and exposes them directly to AI agents, including cross-period financial diffs (revenue growth, operating margin trends). X agents can query structured Japan financials without writing XBRL parsing code, and every data point links back to the original FSA filing for auditability.

**Why yfinance is kept alongside EDINET:**  
EDINET's API is date-based (query by filing date, not ticker), making broad universe scanning slower. yfinance provides quick ticker-based lookups — price, P/E, market cap — for initial candidate screening before an X agent decides whether to pull the full EDINET filing.

---

## 2. Good Information Sources — Currently Not Technically Viable

These sources offer genuinely differentiated investment information not fully covered by Section 1. They are excluded solely due to access constraints, and documented here for reconsideration if their access model changes.

### TradingView
**Why it's valuable:** World-class charting, 160,000+ global instruments, professional-grade technical indicators, and a large community of published trading ideas and analyses — not replicated by any active source.  
**Why it's not viable:** No public API for market data. The three developer APIs (Charting Library, Datafeed API, Broker REST API) are for charting UI integration and broker routing only. Third-party scrapers exist but are unofficial and fragile.  
**Revisit if:** TradingView launches a retail data API.

### Koyfin
**Why it's valuable:** Institutional-quality equity research at retail price — 100,000+ global securities, 5,900+ screening criteria, earnings transcripts, analyst estimates, macro dashboards, and IFRS/GAAP financials powered by Capital IQ. Ranked #1 in the 2025 Kitces AdvisorTech Study for Investment Research & Analytics. The screening depth and transcript access are not matched by any active source.  
**Why it's not viable:** Explicitly no API, by design. Koyfin's data providers (Capital IQ, etc.) prohibit API redistribution.  
**Revisit if:** Koyfin launches an export/API tier, or data providers change redistribution terms.

### Reddit Investing Communities (r/wallstreetbets, r/stocks, r/investing)
**Why it's valuable:** Genuine retail sentiment signal with free, official API access (PRAW, ApeWisdom). Provides ticker mention counts, buzz scores, and sentiment scores across 50+ subreddits in near real-time — a signal type no active source covers.  
**Why it's not viable for this system:** Reddit sentiment is a short-term momentum signal, not a 5-year fundamental signal. A fund built on WSB sentiment performed well in 2021 but broke down once the amplifying conditions (rapid community growth, media coverage, herd behavior) normalized. For a 5-year horizon it is noise — and potentially an anti-signal, as heavily hyped stocks tend to mean-revert.  
**Revisit if:** The investment horizon changes to short/medium term, or a well-validated sentiment-to-5yr-return correlation is established in the literature.

---

## 3. Source Assignment Summary

| Agent | Sources used |
|-------|-------------|
| M (Macro) | FRED API, Web search |
| X (US researcher) | SEC EDGAR + `sec-edgar-mcp`, Alpha Vantage, Polygon.io, Motley Fool (web search) |
| X (Japan researcher) | EDINET + `edinet-mcp`, yfinance, Web search |
| B (Portfolio Manager) | Receives structured outputs from X agents — no direct data source access |
| C, D | No data source access — operate on B's portfolio draft only |
