"""EDINET tools — access Japan FSA electronic disclosure via REST API.

Provides async wrappers for EDINET v2 API (api.edinet-fsa.go.jp).
API key is free, no approval process required.

EDINET is Japan's equivalent of SEC EDGAR — annual securities reports,
quarterly filings, and large shareholding reports in XBRL format.

Usage from X agents:
    from backend.tools.edinet import get_documents, get_company_info
"""

import asyncio
import logging
import os
from datetime import date, timedelta
from typing import Any

logger = logging.getLogger(__name__)

EDINET_BASE = "https://api.edinet-fsa.go.jp/v2"


def _get_api_key() -> str:
    key = os.getenv("EDINET_API_KEY")
    if not key:
        raise ValueError("EDINET_API_KEY not set in environment")
    return key


async def _edinet_request(path: str, params: dict = None) -> dict | None:
    """Make an async GET request to EDINET v2 API."""
    import httpx

    if params is None:
        params = {}
    params["Subscription-Key"] = _get_api_key()

    url = f"{EDINET_BASE}{path}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            logger.warning(f"EDINET 404: {path}")
            return None
        logger.error(f"EDINET HTTP error {e.response.status_code}: {path}")
        raise
    except Exception as e:
        logger.error(f"EDINET request failed: {path} — {e}")
        raise


async def get_company_info(edinet_code: str) -> dict[str, Any]:
    """Get company information by EDINET code.

    EDINET codes are 5-character alphanumeric identifiers
    assigned to all TSE-listed companies.

    Args:
        edinet_code: 5-character EDINET company code.

    Returns:
        Dict with company name, address, sector, etc.
    """
    data = await _edinet_request("/documents.json", {
        "date": date.today().isoformat(),
        "type": 2,  # Annual securities report
    })
    if not data:
        return {"edinet_code": edinet_code, "error": "No data"}

    results = data.get("results", [])
    for doc in results:
        if doc.get("edinetCode") == edinet_code:
            return {
                "edinet_code": edinet_code,
                "name": doc.get("filerName", ""),
                "name_english": doc.get("filerNameEn", ""),
                "type": doc.get("docType", ""),
                "type_name": _doc_type_name(doc.get("docType", "")),
            }

    return {"edinet_code": edinet_code, "name": None}


async def get_documents(
    date_from: str = None,
    date_to: str = None,
    doc_type: int = 2,
    max_results: int = 20,
) -> list[dict]:
    """Search for EDINET documents by date range and type.

    Document types:
        1 - Yukashoken Hokokusho (Annual Securities Report)
        2 - Shihanki Hokokusho (Quarterly Report)
        3 - Kessan Tanshin (Earnings Report)
        5 - Hanenki Hokokusho (Semi-annual Report)

    Args:
        date_from: Start date (YYYY-MM-DD). Defaults to 7 days ago.
        date_to: End date (YYYY-MM-DD). Defaults to today.
        doc_type: Document type code (2=quarterly, 5=semi-annual, 120=annual).
        max_results: Max results to return.

    Returns:
        List of {doc_id, edinet_code, name, type, date, url} dicts.
    """
    if not date_to:
        date_to = date.today().isoformat()
    if not date_from:
        date_from = (date.today() - timedelta(days=30)).isoformat()

    data = await _edinet_request("/documents.json", {
        "date": date_to,
        "type": doc_type,
    })
    if not data:
        return []

    results = data.get("results", [])
    documents = []
    for doc in results[:max_results]:
        doc_date = doc.get("docDescription", "")
        documents.append({
            "doc_id": doc.get("docID", ""),
            "edinet_code": doc.get("edinetCode", ""),
            "name": doc.get("filerName", ""),
            "name_english": doc.get("filerNameEn", ""),
            "type": doc.get("docType", ""),
            "type_name": _doc_type_name(doc.get("docType", "")),
            "date": doc.get("submitDateTime", ""),
            "period": doc.get("docDescription", ""),
            "url": f"https://disclosure.edinet-fsa.go.jp/E01EW/BLMainController.jsp?uji.bean=ee.bean.parent.EECommonSearchBean&PARENT.judgeLang=jp&TID=W001S103&FID={doc.get('docID', '')}",
        })

    return documents


async def get_document_detail(doc_id: str) -> dict[str, Any] | None:
    """Get detailed information about a specific document.

    Args:
        doc_id: EDINET document ID.

    Returns:
        Dict with document metadata and download URL.
    """
    import httpx

    params = {
        "Subscription-Key": _get_api_key(),
        "type": 2,
    }

    # Search for the specific document
    data = await _edinet_request(f"/documents/{doc_id}", params)
    if not data:
        return None

    return {
        "doc_id": doc_id,
        "status": data.get("status", ""),
        "message": data.get("message", ""),
        "result": data.get("result", None),
    }


async def download_xbrl(doc_id: str) -> bytes | None:
    """Download XBRL filing data for a document.

    The XBRL contains structured financial data (financial statements,
    notes, audit reports) in machine-readable format.

    Args:
        doc_id: EDINET document ID.

    Returns:
        Raw XBRL file content as bytes, or None on failure.
    """
    import httpx

    params = {
        "Subscription-Key": _get_api_key(),
        "type": 2,
    }

    url = f"{EDINET_BASE}/documents/{doc_id}/download"
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            return resp.content
    except Exception as e:
        logger.error(f"EDINET XBRL download failed for {doc_id}: {e}")
        return None


def _doc_type_name(code: str | int) -> str:
    """Map EDINET document type code to human-readable name."""
    types = {
        "1": "Annual Securities Report",
        "2": "Quarterly Report",
        "3": "Earnings Report",
        "4": "Semi-annual Report",
        "5": "Corporate Governance Report",
        "6": "Large Shareholding Report",
        "7": "Offering Documents",
        "8": "Tender Offer",
        "9": "Other Reports",
        "10": "Amendments",
    }
    return types.get(str(code), f"Type {code}")


async def search_by_company_name(name: str, max_results: int = 10) -> list[dict]:
    """Search for recent filings by company name.

    Args:
        name: Company name (Japanese or English).
        max_results: Max results.

    Returns:
        List of {doc_id, edinet_code, name, type, date} dicts.
    """
    data = await _edinet_request("/documents.json", {
        "date": date.today().isoformat(),
        "type": 2,
    })
    if not data:
        return []

    results = data.get("results", [])
    matches = []
    for doc in results:
        if name.lower() in doc.get("filerName", "").lower() or name.lower() in doc.get("filerNameEn", "").lower():
            matches.append({
                "doc_id": doc.get("docID", ""),
                "edinet_code": doc.get("edinetCode", ""),
                "name": doc.get("filerName", ""),
                "name_english": doc.get("filerNameEn", ""),
                "type": doc.get("docType", ""),
                "type_name": _doc_type_name(doc.get("docType", "")),
                "date": doc.get("submitDateTime", ""),
            })
            if len(matches) >= max_results:
                break

    return matches