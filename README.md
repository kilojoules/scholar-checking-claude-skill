# Scholar Checking — Claude Code Plugin

A Claude Code plugin that verifies BibTeX citations against academic databases to catch hallucinated or incorrect references.

## What it checks

For each entry in your `.bib` file:

| Field | How it's verified |
|-------|-------------------|
| **Title** | Fuzzy match against database records |
| **Authors** | Author list comparison (family name + initial) |
| **Year** | Exact match, flags off-by-one (preprint vs. published) |
| **Venue** | Journal/conference name with abbreviation expansion |
| **DOI** | Confirms it resolves to the correct paper |
| **arXiv ID** | Validates against arXiv API |

## Databases queried

- [CrossRef](https://www.crossref.org/) — DOI registry, best general coverage
- [OpenAlex](https://openalex.org/) — 240M+ scholarly works, free
- [Semantic Scholar](https://www.semanticscholar.org/) — AI-powered academic search
- [DBLP](https://dblp.org/) — Computer science bibliography
- [arXiv](https://arxiv.org/) — Preprint server

No API keys required. All APIs are queried at their free tier rate limits.

## Installation

```
/install kilojoules-scholar-checking
```

Or for local development:

```
claude --plugin-dir /path/to/scholar-checking-claude-skill
```

## Usage

```
/check-refs path/to/references.bib
```

### Options

- **`--fix`** — Generate corrected BibTeX entries for mismatches
- **`--context path/to/paper.tex`** — Cross-reference citation keys against your LaTeX file

### Examples

```
/check-refs references.bib
/check-refs refs.bib --fix
/check-refs refs.bib --context paper.tex
```

## Requirements

Python 3.7+ with:
- `bibtexparser` — BibTeX parsing
- `requests` — HTTP client

Install dependencies:

```
pip install bibtexparser requests
```

## Optional: Semantic Scholar API key

For higher rate limits with Semantic Scholar, set:

```
export SEMANTIC_SCHOLAR_API_KEY=your_key_here
```

Get a free key at https://www.semanticscholar.org/product/api

## How it works

1. Parses your `.bib` file and cleans LaTeX formatting
2. For entries with DOI or arXiv ID: does direct lookup (authoritative)
3. For other entries: searches by title across multiple databases
4. Compares metadata (title, authors, year, venue) using fuzzy matching
5. Claude Code reads the results and presents a human-readable report

Non-academic entries (software, websites, blogs) are automatically detected and skipped.

## License

MIT
