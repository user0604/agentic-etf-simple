"""Polygon.io REST client — historical OHLCV and financials.
Provides async wrappers around the polygon-api-client package.
"""

import asyncio
import logging
import os
from datetime import date, timedelta
from typing import Any

logger = logging.getLogger(__name__)


def _get_api_key() -> str:
    key = os.getenv("POLYGON_API_KEY")
    if not key:
        raise ValueError("POLYGON_API_KEY not set in environment")
    return key


async def get_aggregates(
    ticker: str,
    timespan: str = "day",
    from_date: str = None,
    to_date: str = None,
) -> list[dict]:
    """Fetch aggregate (OHLCV) bars for a ticker.

    Args:
        ticker: Stock ticker symbol.
        timespan: 'minute', 'hour', 'day', 'week', 'month', 'quarter', 'year'.
        from_date: Start date (YYYY-MM-DD). Defaults to 1 year ago.
        to_date: End date (YYYY-MM-DD). Defaults to today.

    Returns:
        List of {date, open, high, low, close, volume} dicts.
    """
    if not from_date:
        from_date = (date.today() - timedelta(days=365)).isoformat()
    if not to_date:
        to_date = date.today().isoformat()

    def _fetch():
        from polygon import RESTClient
        with RESTClient(api_key=_get_api_key()) as client:
            aggs = client.get_aggs(
                ticker=ticker,
                multiplier=1,
                timespan=timespan,
                from_=from_date,
                to=to_date,
            )
            records = []
            for a in aggs:
                records.append({
                    "date": date.fromtimestamp(a.timestamp / 1000).isoformat(),
                    "open": a.open,
                    "high": a.high,
                    "low": a.low,
                    "close": a.close,
                    "volume": a.volume,
                })
            return records

    try:
        return await asyncio.to_thread(_fetch)
    except Exception as e:
        logger.error(f"Polygon aggregates failed for {ticker}: {e}")
        return []


async def get_daily_open_close(ticker: str, dt: str = None) -> dict[str, Any]:
    """Fetch a single day's open/close data."""
    if not dt:
        dt = date.today().isoformat()

    def _fetch():
        from polygon import RESTClient
        with RESTClient(api_key=_get_api_key()) as client:
            result = client.get_daily_open_close(ticker=ticker, date=dt)
            return {
                "ticker": ticker,
                "date": dt,
                "open": result.open,
                "high": result.high,
                "low": result.low,
                "close": result.close,
                "volume": result.volume,
                "after_hours": result.after_hours,
            }

    try:
        return await asyncio.to_thread(_fetch)
    except Exception as e:
        logger.error(f"Polygon daily open/close failed for {ticker}: {e}")
        return {"ticker": ticker, "date": dt, "error": str(e)}


async def get_ticker_details(ticker: str) -> dict[str, Any]:
    """Fetch detailed information about a ticker."""
    def _fetch():
        from polygon import RESTClient
        with RESTClient(api_key=_get_api_key()) as client:
            details = client.get_ticker_details(ticker=ticker)
            if not details:
                return {"ticker": ticker, "error": "No details found"}
            return {
                "ticker": ticker,
                "name": details.name,
                "market_cap": details.market_cap,
                "description": details.description,
                "sector": details.sector if hasattr(details, 'sector') else None,
                "industry": details.industry if hasattr(details, 'industry') else None,
                "sic_description": details.sic_description,
                "exchange": details.primary_exchange,
                "currency": details.currency_name,
                "active": details.active,
            }

    try:
        return await asyncio.to_thread(_fetch)
    except Exception as e:
        logger.error(f"Polygon ticker details failed for {ticker}: {e}")
        return {"ticker": ticker, "error": str(e)}


async def get_financials(ticker: str) -> list[dict]:
    """Fetch financial statements for a ticker."""
    def _fetch():
        from polygon import RESTClient
        with RESTClient(api_key=_get_api_key()) as client:
            results = client.list_financials(ticker=ticker, limit=5)
            reports = []
            for r in results:
                reports.append({
                    "fiscal_period": r.fiscal_period,
                    "fiscal_year": r.fiscal_year,
                    "start_date": r.start_date,
                    "end_date": r.end_date,
                    "source": r.source_filing_url,
                    "financials": r.financials.to_dict() if hasattr(r, 'financials') and r.financials else {},
                })
            return reports

    try:
        return await asyncio.to_thread(_fetch)
    except Exception as e:
        logger.error(f"Polygon financials failed for {ticker}: {e}")
        return []