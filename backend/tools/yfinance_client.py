"""yfinance wrapper — Yahoo Finance data for equity research.
Provides price history, fundamentals, and basic screening for both
US and Japan (TSE) tickers with TSE ticker normalization.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)

TSE_SUFFIX = ".T"  # Yahoo Finance suffix for Tokyo Stock Exchange


def _normalize_ticker(ticker: str, exchange: str = None) -> str:
    """Normalize ticker symbol for yfinance.

    - If exchange is 'TSE' or 'JP', append .T suffix if not present.
    - Otherwise return as-is.
    """
    if exchange and exchange.upper() in ("TSE", "JP", "TYO"):
        if not ticker.endswith(TSE_SUFFIX):
            return ticker + TSE_SUFFIX
    return ticker.upper()


async def get_price_history(ticker: str, exchange: str = None, period: str = "5y") -> list[dict]:
    """Fetch historical OHLCV price data.

    Args:
        ticker: Stock ticker symbol.
        exchange: Exchange identifier (e.g. 'TSE', 'NASDAQ').
        period: Time period ('1y', '5y', 'max', etc.).

    Returns:
        List of {date, open, high, low, close, volume} dicts.
    """
    import yfinance as yf

    symbol = _normalize_ticker(ticker, exchange)

    def _fetch():
        stock = yf.Ticker(symbol)
        hist = stock.history(period=period)
        records = []
        for dt, row in hist.iterrows():
            records.append({
                "date": dt.strftime("%Y-%m-%d"),
                "open": round(float(row["Open"]), 2),
                "high": round(float(row["High"]), 2),
                "low": round(float(row["Low"]), 2),
                "close": round(float(row["Close"]), 2),
                "volume": int(row["Volume"]),
            })
        return records

    try:
        return await asyncio.to_thread(_fetch)
    except Exception as e:
        logger.error(f"Failed to fetch price history for {symbol}: {e}")
        return []


async def get_fundamentals(ticker: str, exchange: str = None) -> dict:
    """Fetch key fundamental data for a ticker.

    Returns:
        dict with market_cap, pe_ratio, pb_ratio, dividend_yield,
        revenue, net_income, sector, industry, and business_summary.
    """
    import yfinance as yf

    symbol = _normalize_ticker(ticker, exchange)

    def _fetch():
        stock = yf.Ticker(symbol)
        info = stock.info or {}

        # Map Japanese field names if present
        return {
            "ticker": ticker.upper(),
            "symbol": symbol,
            "name": info.get("longName") or info.get("shortName", ""),
            "market_cap": info.get("marketCap"),
            "market_cap_display": _format_large_number(info.get("marketCap")),
            "pe_ratio": info.get("trailingPE") or info.get("forwardPE"),
            "pb_ratio": info.get("priceToBook"),
            "dividend_yield": info.get("dividendYield"),
            "dividend_yield_pct": round(info.get("dividendYield", 0) * 100, 2) if info.get("dividendYield") else None,
            "revenue": info.get("totalRevenue"),
            "net_income": info.get("netIncomeToCommon"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "business_summary": info.get("longBusinessSummary", "")[:500],
            "exchange": info.get("exchange"),
            "currency": info.get("currency"),
            "previous_close": info.get("previousClose"),
            "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
            "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
        }

    try:
        return await asyncio.to_thread(_fetch)
    except Exception as e:
        logger.error(f"Failed to fetch fundamentals for {symbol}: {e}")
        return {"ticker": ticker.upper(), "symbol": symbol, "error": str(e)}


async def search_tickers(query: str) -> list[dict]:
    """Search for tickers by name or keyword.

    Uses yfinance's search functionality.

    Returns:
        List of {ticker, name, exchange, type} dicts.
    """
    import yfinance as yf

    def _search():
        results = yf.Search(query)
        quotes = results.quotes or []
        matches = []
        for q in quotes[:10]:
            matches.append({
                "ticker": q.get("symbol", ""),
                "name": q.get("shortname", q.get("longname", "")),
                "exchange": q.get("exchange", ""),
                "type": q.get("quoteType", ""),
            })
        return matches

    try:
        return await asyncio.to_thread(_search)
    except Exception as e:
        logger.warning(f"Ticker search failed for '{query}': {e}")
        return []


def _format_large_number(val: float | None) -> str:
    """Format a large number for display (e.g. 1.2T, 450B)."""
    if val is None:
        return None
    try:
        val = float(val)
        if val >= 1e12:
            return f"{val/1e12:.1f}T"
        elif val >= 1e9:
            return f"{val/1e9:.1f}B"
        elif val >= 1e6:
            return f"{val/1e6:.1f}M"
        else:
            return str(int(val))
    except (ValueError, TypeError):
        return str(val)