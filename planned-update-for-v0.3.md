# Planned Updates for v0.3

> These changes introduce local Motley Fool article search via a ChromaDB vector store,
> replacing the current web-search-only approach for Motley Fool content.

---

## 1. New Dependencies

Add to `requirements.txt`:

```
chromadb
sentence-transformers
```

---

## 2. New Files

### `scripts/index_motley_fool.py`
One-time setup script. Traverses all subdirectories under `data/articles/`, reads
each folder's `index.md` manifest for title lookup, then reads and processes each
`.md` article in that folder. Extracts metadata (ticker, date, title) via regex,
derives `article_type` from the folder name (e.g. `ticker_analysis`, `macro`,
`epic_exclusive`), chunks each article into ~500-token passages, embeds them using
`sentence-transformers`, and stores everything — including `article_type` — in a
ChromaDB collection at `data/motley_fool_index/`.

Must be re-run whenever new articles or folders are added to the corpus.

### `backend/tools/motley_fool.py`
ChromaDB query client for use by X agents. Exposes one function:

```python
def query_motley_fool(query: str, ticker: str = None, top_k: int = 5) -> list[dict]
```

Two query modes:
- `query` only — broad semantic search across all articles (candidate discovery)
- `query` + `ticker` — semantic search filtered to articles mentioning that specific
  ticker (deep dive once a candidate is identified)

### `backend/tools/motley_fool.py`
ChromaDB query client for use by X agents. Exposes one function:

```python
def query_motley_fool(
    query: str,
    ticker: str = None,
    article_type: str = None,
    top_k: int = 5
) -> list[dict]
```

Three query modes:
- `query` only — broad semantic search across all articles (candidate discovery)
- `query` + `ticker` — semantic search filtered to articles mentioning that specific
  ticker (deep dive once a candidate is identified)
- any combination + `article_type` — further filters to a specific folder/type
  (e.g. `article_type="ticker_analysis"` when researching a specific stock,
  `article_type="macro"` when M needs qualitative macro context)

Each result returns: article title, date, article_type, relevant passage, source filename.
Loads each folder's `index.md` manifest at module startup for fast title lookup.

---

## 3. New Directories

```
data/
├── motley_fool_index/            # ChromaDB collection (auto-created by index script)
└── articles/
    ├── ticker_analysis/          # Example folder — name becomes article_type metadata
    │   ├── index.md              # Manifest for this folder (title + filename per article)
    │   └── *.md
    ├── macro/
    │   ├── index.md
    │   └── *.md
    ├── epic_exclusive/
    │   ├── index.md
    │   └── *.md
    └── <other_type>/             # Add folders freely — indexing script auto-discovers
        ├── index.md
        └── *.md
```

Each subfolder name becomes the `article_type` value in ChromaDB metadata.
Each subfolder must contain its own `index.md` manifest.
Place articles into the appropriate subfolder before running the index script.

---

## 4. Environment Variables

Add to `.env`:

```env
MOTLEY_FOOL_ARTICLES_PATH=data/articles
MOTLEY_FOOL_INDEX_PATH=data/motley_fool_index
```

---

## 5. Change to X Agent Behaviour

X agents (US researchers) gain a new tool call: `query_motley_fool`.

Usage pattern:
1. At research start — broad query (e.g. `"best long term semiconductor buys"`)
   to surface Motley Fool-recommended candidates before deep research begins
2. Once a candidate ticker is identified — ticker-filtered query (optionally also
   filtered to `article_type="ticker_analysis"`) to retrieve all available Motley
   Fool reasoning on that ticker, used to populate the thesis and bull/bear cases
   in the evaluation schema

M agent may also call `query_motley_fool` with `article_type="macro"` to supplement
FRED data with Motley Fool's qualitative macro commentary.

Web search remains as fallback for any ticker or theme not covered by the local corpus.

---

## 6. Setup Instructions Change

Add the following step between "Configure environment" and "Install frontend
dependencies" in the setup sequence:

```bash
# One-time: index Motley Fool articles
# Ensure articles are placed in typed subfolders under data/articles/
# Each subfolder must have its own index.md manifest
python scripts/index_motley_fool.py
# Re-run whenever new articles or new folders are added
```

---

## 7. No Changes Required

- `stock-agent-architecture.md` — Motley Fool is already modelled as a tool call
  from X agents; the implementation detail is below the architecture layer
- All other backend files, agents, and frontend components
- MCP server setup
- Run history and state management
