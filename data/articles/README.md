# Motley Fool Articles Corpus

Each subfolder under `articles/` represents an article type — the folder name
becomes the `article_type` metadata in ChromaDB (e.g. `epic_exclusive`, `macro`).

## Folder Structure

```
articles/
├── epic_exclusive/          # Individual stock bull-and-bear analyses
│   ├── index.md             # Manifest: markdown table mapping file → title
│   └── *.md                 # Article files
├── macro/                   # Macro-economic and company earnings commentary
│   ├── index.md
│   └── *.md
└── <other_type>/            # Add freely — index script auto-discovers
    ├── index.md
    └── *.md
```

## index.md Format (Markdown Table)

Each subfolder must have an `index.md` manifest using a markdown table:

```markdown
| # | File | Title | Size |
|---|------|-------|------|
| 1 | filename.md | Full Article Title | 4.0K |
| 2 | another-file.md | Another Article Title | 3.2K |
```

The `File` column must end with `.md`. The `Title` column is the display title.

## Indexing

Run this from the project root after adding or changing articles:

```bash
python scripts/index_motley_fool.py
```

This rebuilds the ChromaDB index at `data/motley_fool_index/`.