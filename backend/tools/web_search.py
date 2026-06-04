"""Web search tool — Tavily primary + DuckDuckGo fallback.
Provides a unified search interface used by M and X agents.
All blocking I/O runs in a thread pool to avoid event loop blocking.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)


async def web_search(query: str, max_results: int = 5) -> list[dict]:
    """Search the web using Tavily, falling back to DuckDuckGo on failure.

    Args:
        query: Search query string.
        max_results: Maximum number of results to return.

    Returns:
        list of dicts with keys: title, url, content, source.
    """
    result = await _tavily_search(query, max_results)
    if result:
        return result
    logger.warning("Tavily search failed, falling back to DuckDuckGo")
    return await _duckduckgo_search(query, max_results)


async def _tavily_search(query: str, max_results: int = 5) -> list[dict] | None:
    """Search via Tavily API. Runs sync call in thread pool."""
    import os

    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        logger.warning("TAVILY_API_KEY not set, skipping Tavily search")
        return None

    def _search():
        from tavily import TavilyClient
        client = TavilyClient(api_key=api_key)
        return client.search(query, max_results=max_results)

    try:
        response = await asyncio.to_thread(_search)
        results = []
        for r in response.get("results", []):
            results.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": r.get("content", ""),
                "source": "tavily",
            })
        return results
    except Exception as e:
        logger.warning(f"Tavily search failed: {e}")
        return None


async def _duckduckgo_search(query: str, max_results: int = 5) -> list[dict]:
    """Search via DuckDuckGo (no API key needed). Runs sync call in thread pool."""

    def _search():
        from duckduckgo_search import DDGS
        results = []
        with DDGS() as ddgs:
            for i, r in enumerate(ddgs.text(query, max_results=max_results)):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "content": r.get("body", ""),
                    "source": "duckduckgo",
                })
                if i >= max_results - 1:
                    break
        return results

    try:
        return await asyncio.to_thread(_search)
    except Exception as e:
        logger.error(f"DuckDuckGo search failed: {e}")
        return []