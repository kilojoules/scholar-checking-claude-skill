"""BibTeX parsing utilities with LaTeX cleaning."""

import re
import sys
import bibtexparser


# LaTeX accent/command -> ASCII mapping
LATEX_ACCENTS = {
    r'\"': {'a': 'a', 'e': 'e', 'i': 'i', 'o': 'o', 'u': 'u',
            'A': 'A', 'E': 'E', 'I': 'I', 'O': 'O', 'U': 'U'},
    r"\'": {'a': 'a', 'e': 'e', 'i': 'i', 'o': 'o', 'u': 'u',
            'A': 'A', 'E': 'E', 'I': 'I', 'O': 'O', 'U': 'U'},
    r'\`': {'a': 'a', 'e': 'e', 'i': 'i', 'o': 'o', 'u': 'u'},
    r'\^': {'a': 'a', 'e': 'e', 'i': 'i', 'o': 'o', 'u': 'u'},
    r'\~': {'a': 'a', 'n': 'n', 'o': 'o'},
    r'\c': {'c': 'c', 'C': 'C', 's': 's', 'S': 'S'},
}

LATEX_SPECIAL = {
    r'\o': 'o', r'\O': 'O',
    r'\aa': 'a', r'\AA': 'A',
    r'\ae': 'ae', r'\AE': 'AE',
    r'\ss': 'ss',
    r'\l': 'l', r'\L': 'L',
    r'\i': 'i',
}


def clean_latex(text):
    """Strip LaTeX commands and convert accents to ASCII.

    Examples:
        G{\"o}{\c{c}}men -> Gocmen
        R{\'e}thor{\'e} -> Rethore
        Friis-M{\o}ller -> Friis-Moller
        {M}onte {C}arlo -> Monte Carlo
        \textbf{Quick} -> Quick
    """
    if not text:
        return text

    s = text

    # Handle accented characters: {\"o}, {\c{c}}, {\'e}, etc.
    for cmd, mapping in LATEX_ACCENTS.items():
        escaped_cmd = re.escape(cmd)
        # Pattern: {\cmd{char}} or {\cmd char} or \cmd{char}
        for char, replacement in mapping.items():
            # {\"o} or {\"{o}}
            s = re.sub(
                r'\{' + escaped_cmd + r'\{' + re.escape(char) + r'\}\}', replacement, s)
            s = re.sub(
                r'\{' + escaped_cmd + re.escape(char) + r'\}', replacement, s)
            # \"{o} or \"o
            s = re.sub(
                escaped_cmd + r'\{' + re.escape(char) + r'\}', replacement, s)
            s = re.sub(
                escaped_cmd + re.escape(char) + r'(?![a-zA-Z])', replacement, s)

    # Handle special characters: {\o}, \o, etc.
    for cmd, replacement in LATEX_SPECIAL.items():
        escaped_cmd = re.escape(cmd)
        s = re.sub(r'\{' + escaped_cmd + r'\}', replacement, s)
        s = re.sub(escaped_cmd + r'(?![a-zA-Z])', replacement, s)

    # Strip LaTeX formatting commands: \textbf{X} -> X, \emph{X} -> X, etc.
    s = re.sub(r'\\(?:textbf|textit|emph|textrm|textsc|texttt)\{([^}]*)\}', r'\1', s)

    # Strip \url{...}
    s = re.sub(r'\\url\{([^}]*)\}', r'\1', s)

    # Strip remaining LaTeX commands (e.g., \&, \%, \-)
    s = s.replace(r'\&', '&')
    s = s.replace(r'\%', '%')
    s = s.replace(r'\-', '')
    s = s.replace(r'\ ', ' ')

    # Remove brace protection: {LLM} -> LLM, {M}onte -> Monte
    s = re.sub(r'\{([^{}]*)\}', r'\1', s)
    # Second pass for nested braces
    s = re.sub(r'\{([^{}]*)\}', r'\1', s)

    # Clean up whitespace
    s = re.sub(r'\s+', ' ', s).strip()

    return s


def parse_authors(author_string):
    """Parse BibTeX author string into structured list.

    Input: "Last, First and Last, First and others"
    Output: [{"family": "Last", "given": "First"}, ...]
    """
    if not author_string:
        return []

    cleaned = clean_latex(author_string)
    # Split on " and " (case-insensitive)
    parts = re.split(r'\s+and\s+', cleaned, flags=re.IGNORECASE)

    authors = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if part.lower() in ('others', 'et al.', 'et al', '{others}'):
            continue

        if ',' in part:
            # "Last, First" format
            segments = part.split(',', 1)
            family = segments[0].strip()
            given = segments[1].strip() if len(segments) > 1 else ''
        else:
            # "First Last" format
            words = part.split()
            if len(words) == 1:
                family = words[0]
                given = ''
            else:
                family = words[-1]
                given = ' '.join(words[:-1])

        authors.append({'family': family, 'given': given})

    return authors


def extract_arxiv_id(entry):
    """Extract arXiv ID from various BibTeX fields."""
    # Check eprint field first
    eprint = entry.get('eprint', '')
    if eprint:
        match = re.search(r'(\d{4}\.\d{4,5}(?:v\d+)?)', eprint)
        if match:
            return match.group(1)

    # Check journal field: "arXiv preprint arXiv:XXXX.XXXXX"
    journal = entry.get('journal', '')
    match = re.search(r'arXiv[:\s]+(\d{4}\.\d{4,5}(?:v\d+)?)', journal, re.IGNORECASE)
    if match:
        return match.group(1)

    # Check url field
    url = entry.get('url', '')
    match = re.search(r'arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5}(?:v\d+)?)', url, re.IGNORECASE)
    if match:
        return match.group(1)

    # Check note field
    note = entry.get('note', '')
    match = re.search(r'arXiv[:\s]+(\d{4}\.\d{4,5}(?:v\d+)?)', note, re.IGNORECASE)
    if match:
        return match.group(1)

    return None


def extract_doi(entry):
    """Extract DOI from BibTeX entry."""
    doi = entry.get('doi', '')
    if doi:
        # Clean DOI: remove URL prefix if present
        doi = re.sub(r'^https?://(?:dx\.)?doi\.org/', '', doi.strip())
        return doi if doi else None

    # Check url field
    url = entry.get('url', '')
    match = re.search(r'doi\.org/(10\.\S+)', url)
    if match:
        return match.group(1)

    return None


def classify_entry(entry):
    """Classify a BibTeX entry as academic or non-academic.

    Returns: 'academic', 'software', 'website', or 'blog'
    """
    entry_type = entry.get('ENTRYTYPE', '').lower()
    title = entry.get('title', '').lower()
    note = entry.get('note', '')
    howpublished = entry.get('howpublished', '')
    url = entry.get('url', '')
    journal = entry.get('journal', '').lower()

    # Software: @misc with GitHub/GitLab URL and no journal
    if entry_type == 'misc':
        all_text = f"{note} {howpublished} {url}".lower()
        if any(host in all_text for host in ['github.com', 'gitlab.', 'pypi.org', 'cran.r-project']):
            if not journal:
                return 'software'

    # Blog posts
    if 'blog' in journal:
        return 'blog'

    # Websites
    if entry_type == 'misc' and not journal:
        if howpublished and 'url' in howpublished.lower():
            # Has URL but no journal — likely a website/online resource
            if not entry.get('eprint') and not entry.get('doi'):
                return 'website'

    return 'academic'


def parse_bib_file(filepath):
    """Parse a .bib file and return normalized entries.

    Returns list of dicts, each with:
        key, entry_type, title, authors, year, journal/booktitle,
        doi, arxiv_id, classification, raw (original entry dict)
    """
    with open(filepath, encoding='utf-8', errors='replace') as f:
        content = f.read()

    parser = bibtexparser.bparser.BibTexParser(common_strings=True)
    parser.ignore_nonstandard_types = False
    bib_db = bibtexparser.loads(content, parser=parser)

    entries = []
    for entry in bib_db.entries:
        key = entry.get('ID', 'unknown')
        title_raw = entry.get('title', '')
        title_clean = clean_latex(title_raw)
        author_raw = entry.get('author', '')
        authors = parse_authors(author_raw)

        year_str = entry.get('year', '')
        year = None
        if year_str:
            match = re.search(r'(\d{4})', str(year_str))
            if match:
                year = int(match.group(1))

        venue = entry.get('journal', '') or entry.get('booktitle', '')
        venue_clean = clean_latex(venue)

        entries.append({
            'key': key,
            'entry_type': entry.get('ENTRYTYPE', ''),
            'title': title_clean,
            'title_raw': title_raw,
            'authors': authors,
            'author_raw': author_raw,
            'year': year,
            'venue': venue_clean,
            'doi': extract_doi(entry),
            'arxiv_id': extract_arxiv_id(entry),
            'classification': classify_entry(entry),
            'raw': entry,
        })

    return entries


if __name__ == '__main__':
    import json
    if len(sys.argv) < 2:
        print("Usage: python parse_bib.py <bib_file>", file=sys.stderr)
        sys.exit(1)

    entries = parse_bib_file(sys.argv[1])
    for e in entries:
        del e['raw']  # Not JSON-serializable in all cases
    print(json.dumps(entries, indent=2))
