"""SEC EDGAR tools — access US company filings via data.sec.gov REST API.

Provides async wrappers for SEC EDGAR's public JSON API.
No API key required, but a valid User-Agent header is mandatory.

SEC rate limit: 10 requests/second. This tool does NOT use the
sec-edgar-mcp MCP server — that can be added as an enhancement.

Usage from X agents:
    from backend.tools.edgar import get_company_facts, search_company
"""

import asyncio
import json
import logging
import os
import re
import time
from typing import Any

logger = logging.getLogger(__name__)

SEC_BASE = "https://data.sec.gov"
SEC_HEADERS = {
    "User-Agent": "StockPortfolioAgent/1.0 (research@example.com)",
    "Accept": "application/json",
}

# In-memory rate limiter: last request timestamp
_last_request = 0.0
_MIN_INTERVAL = 0.15  # ~7 req/sec, under SEC's 10/sec limit


async def _sec_request(path: str) -> dict | None:
    """Make an async GET request to SEC EDGAR API with rate limiting."""
    global _last_request
    import httpx

    # Rate limit: ensure at least _MIN_INTERVAL seconds between requests
    now = time.monotonic()
    since_last = now - _last_request
    if since_last < _MIN_INTERVAL:
        await asyncio.sleep(_MIN_INTERVAL - since_last)
    _last_request = time.monotonic()

    url = f"{SEC_BASE}{path}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, headers=SEC_HEADERS)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            logger.warning(f"SEC 404: {path}")
            return None
        logger.error(f"SEC HTTP error {e.response.status_code}: {path}")
        raise
    except Exception as e:
        logger.error(f"SEC request failed: {path} — {e}")
        raise


def _pad_cik(cik: str | int) -> str:
    """Pad CIK number to 10 digits with leading zeros."""
    return str(cik).zfill(10)


def _extract_cik_from_text(text: str) -> str | None:
    """Extract CIK number from SEC text responses."""
    match = re.search(r"CIK=(\d+)", text)
    return match.group(1) if match else None


async def search_company(query: str) -> list[dict]:
    """Search for a company by name or ticker using SEC EDGAR browse API.

    Args:
        query: Company name or ticker symbol.

    Returns:
        List of {cik, name, ticker, exchange} dicts.
    """
    try:
        url = f"/cgi-bin/browse-edgar?action=getcompany&company={query}&output=json"
        data = await _sec_request(url)
        if not data:
            return []

        companies = []
        hits = data.get("hits", {}).get("hits", [])
        for hit in hits[:10]:
            src = hit.get("_source", {})
            cik = _extract_cik_from_text(src.get("cik_str", ""))
            if not cik:
                cik = str(hit.get("_id", ""))
            companies.append({
                "cik": cik,
                "name": src.get("name", ""),
                "ticker": src.get("ticker", ""),
                "exchange": src.get("exchange", ""),
            })
        return companies
    except Exception as e:
        logger.error(f"SEC company search failed for '{query}': {e}")
        return []


async def get_company_filings(cik: str | int) -> dict[str, Any]:
    """Get recent SEC filings for a company by CIK number.

    Args:
        cik: SEC CIK number (with or without leading zeros).

    Returns:
        Dict with company info, recent filings, and filing metadata.
    """
    padded = _pad_cik(cik)
    try:
        data = await _sec_request(f"/submissions/CIK{padded}.json")
        if not data:
            return {"cik": cik, "filings": []}

        filings = []
        for f in data.get("filings", {}).get("recent", {}).get("form", [])[:20]:
            idx = len(filings)
            forms = data["filings"]["recent"]
            filings.append({
                "form": f,
                "filing_date": forms.get("filingDate", [""])[idx] if idx < len(forms.get("filingDate", [])) else "",
                "description": forms.get("primaryDocument", [""])[idx] if idx < len(forms.get("primaryDocument", [])) else "",
                "report_date": forms.get("reportDate", [""])[idx] if idx < len(forms.get("reportDate", [])) else "",
            })

        return {
            "cik": cik,
            "name": data.get("name", ""),
            "sic": data.get("sicDescription", ""),
            "tickers": data.get("tickers", []),
            "exchanges": data.get("exchanges", []),
            "filings": filings,
            "filing_count": len(filings),
        }
    except Exception as e:
        logger.error(f"SEC filings lookup failed for CIK {cik}: {e}")
        return {"cik": cik, "filings": [], "error": str(e)}


async def get_company_facts(cik: str | int) -> dict[str, Any]:
    """Get XBRL-tagged financial facts for a company.

    Args:
        cik: SEC CIK number.

    Returns:
        Dict with company info and available facts by taxonomy.
    """
    padded = _pad_cik(cik)
    try:
        data = await _sec_request(f"/api/xbrl/companyfacts/CIK{padded}.json")
        if not data:
            return {"cik": cik, "facts": {}}
        return {
            "cik": cik,
            "name": data.get("entityName", ""),
            "facts": data.get("facts", {}),
        }
    except Exception as e:
        logger.error(f"SEC company facts failed for CIK {cik}: {e}")
        return {"cik": cik, "facts": {}, "error": str(e)}


async def get_concept_value(cik: str | int, taxonomy: str = "us-gaap", concept: str = "RevenueFromContractWithCustomerExcludingAssessedTax") -> list[dict]:
    """Get the value of a specific XBRL concept for a company.

    Args:
        cik: SEC CIK number.
        taxonomy: XBRL taxonomy (e.g. 'us-gaap', 'dei').
        concept: Concept name (e.g. 'RevenueFromContractWithCustomerExcludingAssessedTax',
                 'NetIncomeLoss', 'Assets').

    Returns:
        List of {end, value, fy, fp, filed} for annual data points.
    """
    padded = _pad_cik(cik)
    try:
        path = f"/api/xbrl/companyconcept/CIK{padded}/{taxonomy}/{concept}.json"
        data = await _sec_request(path)
        if not data:
            return []

        units = data.get("units", {})
        annual_data = []
        for unit_key, entries in units.items():
            for entry in entries:
                if entry.get("fp") in ("FY",):  # Annual only
                    annual_data.append({
                        "end": entry.get("end", ""),
                        "value": entry.get("val"),
                        "fiscal_year": entry.get("fy"),
                        "fiscal_period": entry.get("fp"),
                        "filed": entry.get("filed", ""),
                        "unit": unit_key,
                        "frame": entry.get("frame", ""),
                    })
        annual_data.sort(key=lambda x: x["end"], reverse=True)
        return annual_data[:10]
    except Exception as e:
        logger.error(f"SEC concept lookup failed for CIK {cik}/{concept}: {e}")
        return []


async def get_sec_filing_text(cik: str | int, filing_form: str, filing_date: str, doc_name: str = None) -> str | None:
    """Get the raw text of a specific SEC filing.

    Args:
        cik: SEC CIK number.
        filing_form: Form type (e.g. '10-K', '10-Q').
        filing_date: Filing date (YYYY-MM-DD).
        doc_name: Primary document name (auto-resolved if None).

    Returns:
        Filing text content, or None if not found.
    """
    padded = _pad_cik(cik)
    import httpx

    try:
        # First get filings to find the accession number and document
        filings_data = await get_company_filings(cik)
        accession = None
        for f in filings_data.get("filings", []):
            if f["form"] == filing_form and f["filing_date"] == filing_date:
                accession = f["description"].replace("-", "").replace(".txt", "")
                if not doc_name:
                    doc_name = f["description"]
                break

        if not accession or not doc_name:
            logger.warning(f"SEC filing not found: CIK {cik}, {filing_form} on {filing_date}")
            return None

        # Fetch filing text
        url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{doc_name}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, headers=SEC_HEADERS)
            resp.raise_for_status()
            return resp.text[:50000]  # Limit to 50k chars for LLM consumption
    except Exception as e:
        logger.error(f"SEC filing text retrieval failed: {e}")
        return None