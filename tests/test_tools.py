"""Tests for tool wrappers — validates output structure and error handling."""

from unittest.mock import MagicMock, patch

import pytest


class TestYFinanceTickerNormalization:
    def test_us_ticker_no_suffix(self):
        from backend.tools.yfinance_client import _normalize_ticker
        assert _normalize_ticker("NVDA") == "NVDA"
        assert _normalize_ticker("AAPL", "NASDAQ") == "AAPL"

    def test_tse_ticker_gets_dot_t_suffix(self):
        from backend.tools.yfinance_client import _normalize_ticker
        assert _normalize_ticker("6758", "TSE") == "6758.T"
        assert _normalize_ticker("6758", "JP") == "6758.T"
        assert _normalize_ticker("9984", "TYO") == "9984.T"

    def test_tse_ticker_with_existing_suffix(self):
        from backend.tools.yfinance_client import _normalize_ticker
        # Should not double-suffix
        assert _normalize_ticker("6758.T", "TSE") == "6758.T"

    def test_no_exchange_passed(self):
        from backend.tools.yfinance_client import _normalize_ticker
        assert _normalize_ticker("NVDA") == "NVDA"
        assert _normalize_ticker("6758") == "6758"  # No exchange = no suffix


class TestYFinanceFundamentals:
    @pytest.mark.asyncio
    async def test_returns_expected_keys(self):
        from backend.tools.yfinance_client import get_fundamentals
        # This would try to call yfinance; we expect it to fail gracefully
        # if no network, but still return a dict with error info
        result = await get_fundamentals("NONEXISTENTTICKER123")
        assert isinstance(result, dict)
        assert "ticker" in result
        assert "symbol" in result

    @pytest.mark.asyncio
    async def test_price_history_returns_list(self):
        from backend.tools.yfinance_client import get_price_history
        result = await get_price_history("NONEXISTENTTICKER123")
        assert isinstance(result, list)


class TestFREDTool:
    @pytest.mark.asyncio
    async def test_get_series_error_handling(self):
        from backend.tools.fred import get_series
        with patch.dict("os.environ", {"FRED_API_KEY": ""}, clear=True):
            with pytest.raises(ValueError, match="FRED_API_KEY not set"):
                await get_series("FEDFUNDS")


class TestWebSearch:
    @pytest.mark.asyncio
    async def test_returns_empty_on_error(self):
        """web_search returns empty list (not crash) on all failures."""
        from backend.tools.web_search import web_search, _tavily_search, _duckduckgo_search
        with patch.dict("os.environ", {"TAVILY_API_KEY": ""}, clear=True):
            result = await web_search("test query")
            assert isinstance(result, list)


class TestEdgarTool:
    @pytest.mark.asyncio
    async def test_search_company_returns_list(self):
        from backend.tools.edgar import search_company
        # Will likely fail without network, but should return []
        result = await search_company("Microsoft")
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_get_company_filings_nonexistent_cik(self):
        from backend.tools.edgar import get_company_filings
        result = await get_company_filings("9999999999")
        assert isinstance(result, dict)
        assert "cik" in result
        assert "filings" in result


class TestEdinetTool:
    def test_doc_type_name_mapping(self):
        from backend.tools.edinet import _doc_type_name
        assert _doc_type_name("1") == "Annual Securities Report"
        assert _doc_type_name("2") == "Quarterly Report"
        assert _doc_type_name("3") == "Earnings Report"
        assert _doc_type_name("999") == "Type 999"


class TestAlphaVantage:
    @pytest.mark.asyncio
    async def test_returns_safe_structure_on_error(self):
        from backend.tools.alpha_vantage import get_quote, get_daily_prices
        with patch.dict("os.environ", {"ALPHA_VANTAGE_API_KEY": ""}, clear=True):
            result = await get_quote("AAPL")
            assert isinstance(result, dict)
            assert "ticker" in result

            result2 = await get_daily_prices("AAPL")
            assert isinstance(result2, list)


class TestPolygon:
    @pytest.mark.asyncio
    async def test_returns_safe_structure_on_error(self):
        from backend.tools.polygon import get_aggregates, get_ticker_details
        with patch.dict("os.environ", {"POLYGON_API_KEY": ""}, clear=True):
            result = await get_aggregates("AAPL")
            assert isinstance(result, list)
            result2 = await get_ticker_details("AAPL")
            assert isinstance(result2, dict)