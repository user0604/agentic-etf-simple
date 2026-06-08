"""One-time script: index Motley Fool articles into a local ChromaDB vector store.

Usage:
    python scripts/index_motley_fool.py

Expects articles in typed subfolders under data/articles/ (configurable via
MOTLEY_FOOL_ARTICLES_PATH env var). Each subfolder name becomes the article_type.
Each subfolder must contain an index.md manifest.

Output: ChromaDB persistence at data/motley_fool_index/ (configurable via
MOTLEY_FOOL_INDEX_PATH env var).

Re-run whenever articles are added or changed.
"""

import os
import re
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────────────
ARTICLES_PATH = os.getenv("MOTLEY_FOOL_ARTICLES_PATH",
                          os.path.join(os.path.dirname(__file__), "..", "data", "articles"))
INDEX_PATH = os.getenv("MOTLEY_FOOL_INDEX_PATH",
                       os.path.join(os.path.dirname(__file__), "..", "data", "motley_fool_index"))

CHUNK_SIZE = 500  # approximate tokens per chunk
COLLECTION_NAME = "motley_fool"


def generate_index_manifest(folder_path: str) -> dict:
    """Auto-generate index.md for a folder that has .md files but no index.md.

    Scans all .md files (excluding index.md itself), sorts them alphabetically,
    derives a display title from the filename, and writes a markdown table.
    Returns the same {filename: title} mapping as load_index_manifest().
    """
    md_files = sorted(
        f for f in os.listdir(folder_path)
        if f.endswith(".md") and f.lower() != "index.md"
    )
    if not md_files:
        return {}

    manifest_path = os.path.join(folder_path, "index.md")
    logger.info("Auto-generating %s with %d entries ...", manifest_path, len(md_files))

    lines = ["| # | File | Title | Size |\n", "|---|------|-------|------|\n"]
    mapping = {}
    for idx, fname in enumerate(md_files, start=1):
        # Derive title: remove .md, replace dashes/underscores with spaces, title-case
        title = os.path.splitext(fname)[0]
        title = title.replace("-", " ").replace("_", " ")
        title = " ".join(w.capitalize() if w.islower() else w for w in title.split())
        mapping[fname] = title
        lines.append(f"| {idx} | {fname} | {title} | N/A |\n")

    with open(manifest_path, "w", encoding="utf-8") as f:
        f.writelines(lines)

    logger.info("  Wrote %d entries to %s", len(md_files), manifest_path)
    return mapping


def load_index_manifest(folder_path: str) -> dict:
    """Read index.md and return {filename: title} mapping.

    Expects a markdown table format:
        | # | File | Title | Size |
        |---|------|-------|------|
        | 1 | filename.md | Article Title Text | 4.0K |
    """
    manifest_path = os.path.join(folder_path, "index.md")
    if not os.path.isfile(manifest_path):
        logger.warning(f"No index.md found in {folder_path}")
        return {}
    mapping = {}
    with open(manifest_path, "r", encoding="utf-8") as f:
        for line in f:
            # Skip header, separator, and empty lines
            stripped = line.strip()
            if not stripped or stripped.startswith("| #") or stripped.startswith("|---"):
                continue
            # Parse table row: | num | filename.md | title text | size |
            m = re.match(r"\|\s*\d+\s*\|\s*(.+?\.md)\s*\|\s*(.+?)\s*\|", stripped)
            if m:
                mapping[m.group(1).strip()] = m.group(2).strip()
    return mapping


def extract_metadata(text: str) -> dict:
    """Extract ticker and date from article body via regex."""
    meta = {}
    m = re.search(r"(?i)(?:ticker|symbol):\s*([A-Z]{1,5})", text)
    if m:
        meta["ticker"] = m.group(1).upper()
    m = re.search(r"(?i)(?:date|published):\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2})", text)
    if m:
        meta["date"] = m.group(1)
    return meta


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE) -> list[str]:
    """Split text into ~chunk_size-token chunks at sentence boundaries."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks = []
    current = []
    current_len = 0
    for s in sentences:
        s = s.strip()
        if not s:
            continue
        approx_tokens = len(s.split())
        if current_len + approx_tokens > chunk_size and current:
            chunks.append(" ".join(current))
            current = []
            current_len = 0
        current.append(s)
        current_len += approx_tokens
    if current:
        chunks.append(" ".join(current))
    return chunks if chunks else [text]


def main():
    articles_path = os.path.abspath(ARTICLES_PATH)
    index_path = os.path.abspath(INDEX_PATH)

    if not os.path.isdir(articles_path):
        logger.error(f"Articles path not found: {articles_path}")
        sys.exit(1)

    logger.info("Scanning %s ...", articles_path)
    os.makedirs(index_path, exist_ok=True)

    # Collect all article files
    articles = []  # (article_type, filepath, title)
    for entry in sorted(os.scandir(articles_path), key=lambda e: e.name):
        if not entry.is_dir():
            continue
        article_type = entry.name
        manifest = load_index_manifest(entry.path)
        if not manifest:
            # Try auto-generating index.md if .md files exist
            manifest = generate_index_manifest(entry.path)
        if not manifest:
            logger.warning(f"No index.md or .md files in {article_type} — skipping folder")
            continue
        for fname, title in manifest.items():
            fpath = os.path.join(entry.path, fname)
            if os.path.isfile(fpath):
                articles.append((article_type, fpath, title))
            else:
                logger.warning(f"File listed in index.md not found: {fpath}")

    if not articles:
        logger.error(f"No articles found under {articles_path}")
        sys.exit(1)

    logger.info("Found %d articles across %d type folders", len(articles),
                len(set(a[0] for a in articles)))

    # Build documents, metadatas, ids
    documents = []
    metadatas = []
    ids = []
    doc_id = 0

    for article_type, fpath, title in articles:
        with open(fpath, "r", encoding="utf-8") as f:
            text = f.read()
        text_meta = extract_metadata(text)
        chunks = chunk_text(text)

        for ci, chunk in enumerate(chunks):
            documents.append(chunk)
            metadatas.append({
                "title": title,
                "article_type": article_type,
                "source_file": os.path.basename(fpath),
                "ticker": text_meta.get("ticker", ""),
                "date": text_meta.get("date", ""),
                "chunk_index": ci,
                "total_chunks": len(chunks),
            })
            ids.append(f"{article_type}_{doc_id:06d}")
            doc_id += 1

    logger.info("Generated %d chunks from %d articles", len(documents), len(articles))

    # Embed and store in ChromaDB
    import chromadb
    client = chromadb.PersistentClient(path=index_path)

    try:
        collection = client.get_collection(COLLECTION_NAME)
        logger.info("Deleting existing collection '%s' ...", COLLECTION_NAME)
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass  # collection didn't exist — that's fine

    collection = client.create_collection(COLLECTION_NAME)

    # Batch insert to avoid memory pressure
    BATCH = 100
    for i in range(0, len(documents), BATCH):
        batch_end = min(i + BATCH, len(documents))
        collection.add(
            documents=documents[i:batch_end],
            metadatas=metadatas[i:batch_end],
            ids=ids[i:batch_end],
        )
        logger.info("  Indexed %d / %d chunks", batch_end, len(documents))

    logger.info("Done! Collection '%s' has %d chunks at %s",
                COLLECTION_NAME, collection.count(), index_path)


if __name__ == "__main__":
    main()