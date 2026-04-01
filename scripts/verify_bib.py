#!/usr/bin/env python3
"""Main orchestrator for BibTeX citation verification."""

import argparse
import json
import sys
import time

from parse_bib import parse_bib_file
from api_clients import (
    CrossRefClient, OpenAlexClient, SemanticScholarClient,
    DblpClient, ArxivClient,
)
from matching import title_similarity, compute_overall_match


def verify_entry(entry, clients, verbose=False):
    """Verify a single BibTeX entry against academic databases.

    Returns dict with status, best_match, and field_comparison.
    """
    if entry['classification'] != 'academic':
        return {
            'key': entry['key'],
            'status': 'skipped',
            'reason': entry['classification'],
            'bib': _bib_summary(entry),
        }

    title = entry['title']
    doi = entry.get('doi')
    arxiv_id = entry.get('arxiv_id')

    if verbose:
        print(f"  Checking: {entry['key']} - {title[:60]}...", file=sys.stderr)

    candidates = []

    # Phase 1: Direct lookups (authoritative)
    if doi:
        if verbose:
            print(f"    DOI lookup: {doi}", file=sys.stderr)
        result = clients['crossref'].lookup_doi(doi)
        if result:
            candidates.append(result)

    if arxiv_id:
        if verbose:
            print(f"    arXiv lookup: {arxiv_id}", file=sys.stderr)
        result = clients['arxiv'].lookup_by_id(arxiv_id)
        if result:
            candidates.append(result)

    # Check if Phase 1 gave us a strong match
    best = _find_best_match(entry, candidates)
    if best and best['match']['fields']['title']['score'] >= 0.85:
        return _build_result(entry, best)

    # Phase 2: Title search (fallback chain)
    api_order = [
        ('crossref', lambda t: clients['crossref'].search_by_title(t)),
        ('openalex', lambda t: clients['openalex'].search_by_title(t)),
        ('semantic_scholar', lambda t: clients['semantic_scholar'].search_by_title(t)),
        ('dblp', lambda t: clients['dblp'].search_by_title(t)),
    ]

    for api_name, search_fn in api_order:
        if verbose:
            print(f"    Searching {api_name}...", file=sys.stderr)
        try:
            results = search_fn(title)
            candidates.extend(results)
        except Exception as e:
            print(f"    {api_name} error: {e}", file=sys.stderr)

        # Check if we have a strong match — stop early
        best = _find_best_match(entry, candidates)
        if best and best['match']['fields']['title']['score'] >= 0.85:
            return _build_result(entry, best)

    # No strong match found — return best we have or not_found
    best = _find_best_match(entry, candidates)
    if best:
        return _build_result(entry, best)

    return {
        'key': entry['key'],
        'status': 'not_found',
        'bib': _bib_summary(entry),
        'apis_searched': [name for name, _ in api_order],
    }


def _find_best_match(entry, candidates):
    """Find the best matching candidate for a bib entry."""
    if not candidates:
        return None

    best = None
    best_score = -1

    for candidate in candidates:
        match = compute_overall_match(entry, candidate)
        score = match['fields']['title']['score']
        if score > best_score:
            best_score = score
            best = {'candidate': candidate, 'match': match}

    # Only return if title similarity is at least 0.70
    if best and best_score >= 0.70:
        return best
    return None


def _build_result(entry, best):
    """Build the result dict for a matched entry."""
    return {
        'key': entry['key'],
        'status': best['match']['status'],
        'bib': _bib_summary(entry),
        'best_match': {
            'source': best['candidate']['source'],
            'title': best['candidate']['title'],
            'authors': [f"{a.get('given', '')} {a.get('family', '')}".strip()
                        for a in best['candidate'].get('authors', [])],
            'year': best['candidate'].get('year'),
            'venue': best['candidate'].get('venue', ''),
            'doi': best['candidate'].get('doi'),
            'arxiv_id': best['candidate'].get('arxiv_id'),
            'url': best['candidate'].get('url'),
        },
        'field_comparison': best['match']['fields'],
    }


def _bib_summary(entry):
    """Create a summary of the bib entry for output."""
    return {
        'title': entry.get('title', ''),
        'authors': [f"{a.get('given', '')} {a.get('family', '')}".strip()
                    for a in entry.get('authors', [])],
        'year': entry.get('year'),
        'venue': entry.get('venue', ''),
        'doi': entry.get('doi'),
        'arxiv_id': entry.get('arxiv_id'),
    }


def main():
    parser = argparse.ArgumentParser(description='Verify BibTeX citations against academic databases')
    parser.add_argument('bib_file', help='Path to .bib file')
    parser.add_argument('--verbose', action='store_true', help='Print progress to stderr')
    parser.add_argument('--max-entries', type=int, default=0, help='Max entries to process (0 = all)')
    parser.add_argument('--batch-delay', type=float, default=0.5,
                        help='Delay between entries in seconds (default: 0.5)')
    args = parser.parse_args()

    # Parse bib file
    try:
        entries = parse_bib_file(args.bib_file)
    except FileNotFoundError:
        print(json.dumps({'error': f'File not found: {args.bib_file}'}))
        sys.exit(1)
    except Exception as e:
        print(json.dumps({'error': f'Parse error: {str(e)}'}))
        sys.exit(1)

    if args.max_entries > 0:
        entries = entries[:args.max_entries]

    print(f"Parsed {len(entries)} entries from {args.bib_file}", file=sys.stderr)

    # Initialize API clients
    clients = {
        'crossref': CrossRefClient(),
        'openalex': OpenAlexClient(),
        'semantic_scholar': SemanticScholarClient(),
        'dblp': DblpClient(),
        'arxiv': ArxivClient(),
    }

    # Process entries
    results = []
    rate_limited = False

    for i, entry in enumerate(entries):
        if i > 0 and entry['classification'] == 'academic':
            time.sleep(args.batch_delay)

        print(f"[{i+1}/{len(entries)}] {entry['key']}", file=sys.stderr)

        result = verify_entry(entry, clients, verbose=args.verbose)
        results.append(result)

    # Summary
    summary = {
        'verified': sum(1 for r in results if r['status'] == 'verified'),
        'mismatch': sum(1 for r in results if r['status'] == 'mismatch'),
        'not_found': sum(1 for r in results if r['status'] == 'not_found'),
        'skipped': sum(1 for r in results if r['status'] == 'skipped'),
    }

    output = {
        'file': args.bib_file,
        'total_entries': len(entries),
        'summary': summary,
        'entries': results,
    }

    print(json.dumps(output, indent=2))


if __name__ == '__main__':
    main()
