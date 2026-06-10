"""ChromaDB query client for local Motley Fool article search.

Exposes an async query function that follows the same pattern as web_search.py:
async function, returns list[dict], safe under any error.
"""

import asyncio
import logging
import os

logger = logging.getLogger(__name__)

# Lazy-init ChromaDB client (module-level singleton pattern)
_client = None
_collection = None


def _get_collection():
    """Get the ChromaDB collection (lazy init)."""
    global _client, _collection
    if _collection is not None:
        return _collection

    import chromadb

    index_path = os.getenv(
        "MOTLEY_FOOL_INDEX_PATH",
        os.path.join(os.path.dirname(__file__), "..", "..", "data", "motley_fool_index"),
    )

    try:
        _client = chromadb.PersistentClient(path=os.path.abspath(index_path))
        _collection = _client.get_collection("motley_fool")
        logger.info("Connected to Motley Fool index at %s (%d chunks)",
                     index_path, _collection.count())
    except Exception as e:
        logger.warning("Could not open Motley Fool index at %s: %s", index_path, e)
        _collection = None

    return _collection


async def query_motley_fool(
    query: str,
    ticker: str = None,
    article_type: str = None,
    top_k: int = 5,
) -> list[dict]:
    """Semantic search over the local Motley Fool article corpus.

    Args:
        query: Free-text search query.
        ticker: Optional ticker symbol to filter by.
        article_type: Optional article type (folder name) to filter by.
        top_k: Maximum results to return.

    Returns:
        List of dicts with keys: title, date, article_type, passage, ticker,
        source_file, score. Empty list on any error.
    """
    collection = await asyncio.to_thread(_get_collection)
    if collection is None:
        logger.warning("Motley Fool index not available (run scripts/index_motley_fool.py first)")
        return []

    try:
        # Build ChromaDB where-filter
        where_filters = {}
        if ticker:
            where_filters["ticker"] = ticker.upper()
        if article_type:
            where_filters["article_type"] = article_type

        results = await asyncio.to_thread(
            collection.query,
            query_texts=[query],
            n_results=top_k,
            where=where_filters if where_filters else None,
        )

        if not results or not results.get("ids") or not results["ids"][0]:
            return []

        output = []
        metadatas = results.get("metadatas", [[]])[0] or []
        documents = results.get("documents", [[]])[0] or []
        distances = results.get("distances", [[]])[0] or []

        for i in range(len(metadatas)):
            meta = metadatas[i]
            output.append({
                "title": meta.get("title", ""),
                "date": meta.get("date", ""),
                "article_type": meta.get("article_type", ""),
                "passage": documents[i] if i < len(documents) else "",
                "ticker": meta.get("ticker", ""),
                "source_file": meta.get("source_file", ""),
                "score": 1.0 - distances[i] if i < len(distances) else 1.0,
            })

        return output

    except Exception as e:
        logger.warning("Motley Fool query failed: %s", e)
        return []