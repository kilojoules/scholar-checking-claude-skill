"""Fuzzy matching logic for comparing BibTeX entries against API results."""

import re
import string
import unicodedata
from difflib import SequenceMatcher

# Common venue abbreviation expansions
VENUE_ALIASES = {
    'neurips': 'advances in neural information processing systems',
    'nips': 'advances in neural information processing systems',
    'icml': 'international conference on machine learning',
    'iclr': 'international conference on learning representations',
    'cvpr': 'conference on computer vision and pattern recognition',
    'iccv': 'international conference on computer vision',
    'eccv': 'european conference on computer vision',
    'aaai': 'association for the advancement of artificial intelligence',
    'ijcai': 'international joint conference on artificial intelligence',
    'acl': 'association for computational linguistics',
    'emnlp': 'empirical methods in natural language processing',
    'naacl': 'north american chapter of the association for computational linguistics',
    'sigir': 'special interest group on information retrieval',
    'kdd': 'knowledge discovery and data mining',
    'www': 'world wide web',
    'chi': 'conference on human factors in computing systems',
    'uist': 'user interface software and technology',
    'osdi': 'operating systems design and implementation',
    'sosp': 'symposium on operating systems principles',
    'isca': 'international symposium on computer architecture',
    'micro': 'international symposium on microarchitecture',
    'sc': 'supercomputing',
    'hpca': 'high performance computer architecture',
    'dac': 'design automation conference',
    'fpl': 'field-programmable logic and applications',
    'jfm': 'journal of fluid mechanics',
    'torque': 'the science of making torque from wind',
    'wes': 'wind energy science',
}


def normalize_title(title):
    """Lowercase, strip accents, strip punctuation, collapse whitespace."""
    if not title:
        return ''
    s = _strip_accents(title).lower()
    # Remove punctuation
    s = s.translate(str.maketrans('', '', string.punctuation))
    # Collapse whitespace
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def title_similarity(bib_title, api_title):
    """Compare two titles, return similarity score 0-1."""
    t1 = normalize_title(bib_title)
    t2 = normalize_title(api_title)
    if not t1 or not t2:
        return 0.0
    return SequenceMatcher(None, t1, t2).ratio()


def _strip_accents(text):
    """Strip Unicode accent marks (ö→o, ç→c, é→e, etc.)."""
    nfkd = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in nfkd if unicodedata.category(c) != 'Mn')


def _normalize_family_name(name):
    """Normalize a family name for comparison."""
    if not name:
        return ''
    s = _strip_accents(name).lower().strip()
    # Strip DBLP disambiguation suffixes like "Yao 0006"
    s = re.sub(r'\s+\d{4}$', '', s)
    return re.sub(r'\s+', ' ', s)


def _initial(given):
    """Get first initial from a given name."""
    if not given:
        return ''
    given = given.strip()
    return given[0].lower() if given else ''


def author_similarity(bib_authors, api_authors, bib_truncated=False):
    """Compare author lists.

    If bib_truncated is True (the bib used "and others" / "et al."),
    scoring checks that bib authors are a subset of API authors rather
    than penalizing for missing co-authors.

    Returns dict with:
        score: float 0-1
        matched: list of matched author pairs
        missing_in_bib: authors in API but not in bib
        extra_in_bib: authors in bib but not in API
    """
    if not bib_authors and not api_authors:
        return {'score': 1.0, 'matched': [], 'missing_in_bib': [], 'extra_in_bib': []}
    if not bib_authors or not api_authors:
        return {'score': 0.0, 'matched': [], 'missing_in_bib': api_authors or [], 'extra_in_bib': bib_authors or []}

    matched = []
    unmatched_api = list(range(len(api_authors)))
    unmatched_bib = list(range(len(bib_authors)))

    # Match by family name similarity
    for bi in range(len(bib_authors)):
        best_score = 0.0
        best_ai = None
        bib_family = _normalize_family_name(bib_authors[bi].get('family', ''))

        for ai in unmatched_api:
            api_family = _normalize_family_name(api_authors[ai].get('family', ''))
            score = SequenceMatcher(None, bib_family, api_family).ratio()
            if score > best_score:
                best_score = score
                best_ai = ai

        if best_score >= 0.80 and best_ai is not None:
            matched.append({
                'bib': bib_authors[bi],
                'api': api_authors[best_ai],
                'family_score': best_score,
            })
            unmatched_api.remove(best_ai)
            if bi in unmatched_bib:
                unmatched_bib.remove(bi)

    missing_in_bib = [api_authors[i] for i in unmatched_api]
    extra_in_bib = [bib_authors[i] for i in unmatched_bib]

    if bib_truncated:
        # Truncated list ("et al."): score by how many bib authors were found
        # in the API results. Missing API authors are expected, not penalized.
        score = len(matched) / len(bib_authors) if bib_authors else 0.0
    else:
        # Full list: score relative to the larger list
        max_count = max(len(bib_authors), len(api_authors))
        score = len(matched) / max_count if max_count > 0 else 0.0

    return {
        'score': score,
        'matched': matched,
        'missing_in_bib': missing_in_bib,
        'extra_in_bib': extra_in_bib,
    }


def year_match(bib_year, api_year):
    """Compare years, accounting for preprint vs. published differences."""
    if bib_year is None or api_year is None:
        return {'match': bib_year is None and api_year is None,
                'off_by_one': False,
                'bib_year': bib_year, 'api_year': api_year}

    exact = bib_year == api_year
    off_by_one = abs(bib_year - api_year) == 1

    return {
        'match': exact,
        'off_by_one': off_by_one,
        'bib_year': bib_year,
        'api_year': api_year,
    }


def _expand_venue(venue):
    """Expand known venue abbreviations and normalize."""
    if not venue:
        return ''
    v = venue.lower().strip()

    # Normalize arXiv preprint strings to just "arxiv"
    if re.match(r'^arxiv\s+preprint', v) or v == 'arxiv':
        return 'arxiv'

    # Check if the venue itself is an abbreviation
    if v in VENUE_ALIASES:
        return VENUE_ALIASES[v]
    # Check if any abbreviation appears in the venue string
    for abbr, full in VENUE_ALIASES.items():
        if abbr == v or full in v:
            return full
    return v


def venue_similarity(bib_venue, api_venue):
    """Compare venue names with abbreviation expansion."""
    v1 = _expand_venue(bib_venue)
    v2 = _expand_venue(api_venue)
    if not v1 or not v2:
        return 0.0
    # Remove common prefixes like "Proceedings of the", "In"
    for prefix in ['proceedings of the ', 'proceedings of ', 'in ']:
        if v1.startswith(prefix):
            v1 = v1[len(prefix):]
        if v2.startswith(prefix):
            v2 = v2[len(prefix):]
    return SequenceMatcher(None, v1, v2).ratio()


def compute_overall_match(bib_entry, api_result):
    """Compute field-level match between a bib entry and an API result.

    Returns dict with per-field comparison and overall status.
    """
    fields = {}

    # Title
    t_score = title_similarity(bib_entry.get('title', ''), api_result.get('title', ''))
    fields['title'] = {
        'score': round(t_score, 3),
        'status': 'match' if t_score >= 0.85 else 'mismatch' if t_score >= 0.70 else 'no_match',
        'bib': bib_entry.get('title', ''),
        'api': api_result.get('title', ''),
    }

    # Authors
    bib_truncated = bib_entry.get('authors_truncated', False)
    a_result = author_similarity(bib_entry.get('authors', []), api_result.get('authors', []),
                                 bib_truncated=bib_truncated)
    fields['authors'] = {
        'score': round(a_result['score'], 3),
        'status': 'match' if a_result['score'] >= 0.70 else 'mismatch',
        'missing_in_bib': [f"{a.get('given', '')} {a.get('family', '')}".strip()
                           for a in a_result['missing_in_bib']],
        'extra_in_bib': [f"{a.get('given', '')} {a.get('family', '')}".strip()
                         for a in a_result['extra_in_bib']],
    }

    # Year
    y_result = year_match(bib_entry.get('year'), api_result.get('year'))
    if y_result['match']:
        y_status = 'match'
    elif y_result['off_by_one']:
        y_status = 'off_by_one'
    else:
        y_status = 'mismatch'
    fields['year'] = {
        'status': y_status,
        'bib': y_result['bib_year'],
        'api': y_result['api_year'],
    }

    # Venue
    v_score = venue_similarity(bib_entry.get('venue', ''), api_result.get('venue', ''))
    fields['venue'] = {
        'score': round(v_score, 3),
        'status': 'match' if v_score >= 0.60 else 'mismatch' if v_score > 0 else 'missing',
        'bib': bib_entry.get('venue', ''),
        'api': api_result.get('venue', ''),
    }

    # DOI
    bib_doi = bib_entry.get('doi')
    api_doi = api_result.get('doi')
    if bib_doi and api_doi:
        fields['doi'] = {
            'status': 'match' if bib_doi.lower() == api_doi.lower() else 'mismatch',
            'bib': bib_doi,
            'api': api_doi,
        }
    elif api_doi and not bib_doi:
        fields['doi'] = {'status': 'missing_in_bib', 'suggested': api_doi}
    else:
        fields['doi'] = {'status': 'both_missing'}

    # arXiv ID
    bib_arxiv = bib_entry.get('arxiv_id')
    api_arxiv = api_result.get('arxiv_id')
    if bib_arxiv and api_arxiv:
        # Strip version suffix for comparison
        b = re.sub(r'v\d+$', '', bib_arxiv)
        a = re.sub(r'v\d+$', '', api_arxiv)
        fields['arxiv_id'] = {
            'status': 'match' if b == a else 'mismatch',
            'bib': bib_arxiv,
            'api': api_arxiv,
        }
    elif api_arxiv and not bib_arxiv:
        fields['arxiv_id'] = {'status': 'missing_in_bib', 'suggested': api_arxiv}
    else:
        fields['arxiv_id'] = {'status': 'both_missing'}

    # Overall status
    title_ok = fields['title']['status'] == 'match'
    year_ok = fields['year']['status'] in ('match', 'off_by_one')
    authors_ok = fields['authors']['status'] == 'match'

    if title_ok and year_ok and authors_ok:
        overall = 'verified'
    elif fields['title']['score'] >= 0.70:
        overall = 'mismatch'
    else:
        overall = 'not_found'

    return {
        'status': overall,
        'fields': fields,
    }
