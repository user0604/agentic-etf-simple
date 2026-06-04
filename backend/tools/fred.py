"""FRED API wrapper — macro-economic data for Agent M.
Provides structured access to Federal Reserve Economic Data series.
"""

import logging
from datetime import date, timedelta
from typing import Any

logger = logging.getLogger(__name__)

# FRED series IDs relevant to the portfolio system
SERIES = {
    "fed_funds_rate": "FEDFUNDS",
    "cpi": "CPIAUCSL",
    "gdp": "GDP",
    "unemployment": "UNRATE",
    "usd_jpy": "DEXJPUS",
    "ten_year_breakeven": "T10YIE",
    "recession_prob": "RECPROUSM156N",
    "industrial_production": "INDPRO",
    "consumer_sentiment": "UMCSENT",
}


def _get_fred_client():
    """Lazy-init FRED client from env API key."""
    import os
    from fredapi import Fred
    api_key = os.getenv("FRED_API_KEY")
    if not api_key:
        raise ValueError("FRED_API_KEY not set in environment")
    return Fred(api_key=api_key)


async def get_series(series_id: str, days_back: int = 365 * 5) -> list[dict]:
    """Fetch a FRED time series.

    Args:
        series_id: FRED series ID (e.g. 'FEDFUNDS').
        days_back: How many days of history to fetch.

    Returns:
        List of {date, value} dicts sorted by date ascending.
    """
    try:
        fred = _get_fred_client()
        data = fred.get_series(series_id)
        cutoff = date.today() - timedelta(days=days_back)
        records = []
        for dt, val in data.items():
            if dt.date() >= cutoff and val is not None:
                records.append({"date": dt.strftime("%Y-%m-%d"), "value": round(float(val), 4)})
        return records
    except Exception as e:
        logger.error(f"Unexpected error fetching {series_id}: {e}")
        raise


async def get_latest_value(series_id: str) -> float | None:
    """Fetch the most recent observation for a FRED series."""
    try:
        fred = _get_fred_client()
        series = fred.get_series(series_id)
        if series.empty:
            return None
        val = series.iloc[-1]
        return round(float(val), 4) if val is not None else None
    except Exception as e:
        logger.warning(f"Failed to get latest {series_id}: {e}")
        return None


async def get_macro_snapshot() -> dict[str, Any]:
    """Fetch all key macro indicators for the portfolio system.

    Returns a dict with latest values and recent trends for each indicator.
    This is the primary entry point used by Agent M.
    """
    results = {}

    for name, series_id in SERIES.items():
        try:
            latest = await get_latest_value(series_id)
            # Get recent history to compute trend
            history = await get_series(series_id, days_back=180)
            recent_values = [r["value"] for r in history[-12:]] if len(history) >= 12 else [r["value"] for r in history]

            trend = None
            if len(recent_values) >= 2:
                if recent_values[-1] > recent_values[0] * 1.01:
                    trend = "rising"
                elif recent_values[-1] < recent_values[0] * 0.99:
                    trend = "falling"
                else:
                    trend = "stable"

            results[name] = {
                "latest": latest,
                "trend": trend,
                "observation_count": len(history),
                "series_id": series_id,
            }
        except Exception as e:
            logger.warning(f"Could not fetch {name}: {e}")
            results[name] = {"latest": None, "trend": None, "error": str(e)}

    return results