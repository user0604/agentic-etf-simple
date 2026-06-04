"""Alpha Vantage REST client — stock prices and fundamentals.
Provides async wrappers around the alpha_vantage package.
Free tier: 5 API calls/min, 500 calls/day.
"""

import asyncio
import logging
import os
from datetime import date, timedelta
from typing import Any

logger = logging.getLogger(__name__)


def _get_api_key() -> str:
    key = os.getenv("ALPHA_VANTAGE_API_KEY")
    if not key:
        raise ValueError("ALPHA_VANTAGE_API_KEY not set in environment")
    return key


async def get_daily_prices(ticker: str, outputsize: str = "compact") -> list[dict]:
    """Fetch daily OHLCV price data for a ticker.

    Args:
        ticker: Stock ticker symbol.
        outputsize: 'compact' (last 100 days) or 'full' (up to 20 years).

    Returns:
        List of {date, open, high, low, close, volume} dicts.
    """
    def _fetch():
        from alpha_vantage.timeseries import TimeSeries
        ts = TimeSeries(key=_get_api_key(), output_format="json")
        data, meta = ts.get_daily(symbol=ticker, outputsize=outputsize)
        records = []
        for dt_str, vals in sorted(data.items()):
            records.append({
                "date": dt_str,
                "open": float(vals.get("1. open", 0)),
                "high": float(vals.get("2. high", 0)),
                "low": float(vals.get("3. low", 0)),
                "close": float(vals.get("4. close", 0)),
                "volume": int(vals.get("5. volume", 0)),
            })
        return records

    try:
        return await asyncio.to_thread(_fetch)
    except Exception as e:
        logger.error(f"Alpha Vantage daily prices failed for {ticker}: {e}")
        return []


async def get_quote(ticker: str) -> dict[str, Any]:
    """Fetch a real-time stock quote."""
    def _fetch():
        from alpha_vantage.timeseries import TimeSeries
        ts = TimeSeries(key=_get_api_key(), output_format="json")
        data, meta = ts.get_quote_endpoint(symbol=ticker)

        # Alpha Vantage returns keys like "01. symbol", "02. open", etc.
        return {
            "ticker": ticker,
            "price": float(data.get("05. price", 0)),
            "change": float(data.get("09. change", 0)),
            "change_pct": data.get("10. change percent", "").replace("%", ""),
            "volume": int(data.get("06. volume", 0)),
            "previous_close": float(data.get("08. previous close", 0)),
            "day_high": float(data.get("03. high", 0)),
            "day_low": float(data.get("04. low", 0)),
            "pe_ratio": float(data.get("12. PERatio", 0)) if data.get("12. PERatio", "None") != "None" else None,
        }

    try:
        return await asyncio.to_thread(_fetch)
    except Exception as e:
        logger.error(f"Alpha Vantage quote failed for {ticker}: {e}")
        return {"ticker": ticker, "error": str(e)}


async def get_income_statement(ticker: str) -> list[dict]:
    """Fetch annual income statements."""
    def _fetch():
        from alpha_vantage.fundamentaldata import FundamentalData
        fd = FundamentalData(key=_get_api_key(), output_format="json")
        data, meta = fd.get_income_statement_annual(symbol=ticker)
        reports = data.get("annualReports", [])
        return [
            {
                "fiscal_date": r.get("fiscalDateEnding", ""),
                "total_revenue": float(r.get("totalRevenue", 0)),
                "net_income": float(r.get("netIncome", 0)),
                "gross_profit": float(r.get("grossProfit", 0)),
                "ebit": float(r.get("ebit", 0)),
                "eps": float(r.get("reportedEPS", 0)) if r.get("reportedEPS") else None,
            }
            for r in reports[:5]
        ]

    try:
        return await asyncio.to_thread(_fetch)
    except Exception as e:
        logger.error(f"Alpha Vantage income statement failed for {ticker}: {e}")
        return []


async def get_balance_sheet(ticker: str) -> list[dict]:
    """Fetch annual balance sheets."""
    def _fetch():
        from alpha_vantage.fundamentaldata import FundamentalData
        fd = FundamentalData(key=_get_api_key(), output_format="json")
        data, meta = fd.get_balance_sheet_annual(symbol=ticker)
        reports = data.get("annualReports", [])
        return [
            {
                "fiscal_date": r.get("fiscalDateEnding", ""),
                "total_assets": float(r.get("totalAssets", 0)),
                "total_liabilities": float(r.get("totalLiabilities", 0)),
                "shareholder_equity": float(r.get("totalShareholderEquity", 0)),
                "cash": float(r.get("cashAndCashEquivalentsAtCarryingValue", 0)),
                "long_term_debt": float(r.get("longTermDebt", 0)),
            }
            for r in reports[:5]
        ]

    try:
        return await asyncio.to_thread(_fetch)
    except Exception as e:
        logger.error(f"Alpha Vantage balance sheet failed for {ticker}: {e}")
        return []