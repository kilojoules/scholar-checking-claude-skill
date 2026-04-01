"""Academic API client wrappers with rate limiting."""

import os
import re
import sys
import time
import xml.etree.ElementTree as ET

import requests


TIMEOUT = 10  # seconds
USER_AGENT = 'ScholarChecker/0.1 (Claude Code plugin; mailto:scholar-checker@example.com)'


def _parse_display_name(name):
    """Parse a display name like 'First Last' into {given, family}.

    Also strips DBLP disambiguation suffixes like 'Yao 0006'.
    """
    if not name:
        return {'given': '', 'family': ''}
    # Strip DBLP disambiguation suffixes (trailing space + 4 digits)
    name = re.sub(r'\s+\d{4}$', '', name.strip())
    parts = name.rsplit(' ', 1)
    if len(parts) == 2:
        return {'given': parts[0], 'family': parts[1]}
    return {'given': '', 'family': name}


class RateLimiter:
    """Simple rate limiter using sleep."""

    def __init__(self, min_interval):
        self.min_interval = min_interval
        self.last_call = 0

    def wait(self):
        elapsed = time.time() - self.last_call
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self.last_call = time.time()


class CrossRefClient:
    """CrossRef API client. Best general coverage, high rate limit."""

    BASE_URL = 'https://api.crossref.org'

    def __init__(self):
        self.limiter = RateLimiter(0.05)  # 20 req/s with polite pool
        self.session = requests.Session()
        self.session.headers['User-Agent'] = USER_AGENT

    def lookup_doi(self, doi):
        """Look up a specific DOI. Returns normalized result or None."""
        self.limiter.wait()
        try:
            resp = self.session.get(
                f'{self.BASE_URL}/works/{doi}',
                timeout=TIMEOUT)
            if resp.status_code != 200:
                return None
            data = resp.json().get('message', {})
            return self._normalize(data)
        except Exception as e:
            print(f'  CrossRef DOI lookup error: {e}', file=sys.stderr)
            return None

    def search_by_title(self, title, rows=3):
        """Search for papers by title. Returns list of normalized results."""
        self.limiter.wait()
        try:
            resp = self.session.get(
                f'{self.BASE_URL}/works',
                params={'query.title': title, 'rows': rows},
                timeout=TIMEOUT)
            if resp.status_code != 200:
                return []
            items = resp.json().get('message', {}).get('items', [])
            return [self._normalize(item) for item in items]
        except Exception as e:
            print(f'  CrossRef search error: {e}', file=sys.stderr)
            return []

    def _normalize(self, item):
        title_list = item.get('title', [])
        title = title_list[0] if title_list else ''

        authors = []
        for a in item.get('author', []):
            authors.append({
                'family': a.get('family', ''),
                'given': a.get('given', ''),
            })

        # Year from published-print or published-online or created
        year = None
        for date_key in ['published-print', 'published-online', 'created']:
            date_parts = item.get(date_key, {}).get('date-parts', [[]])
            if date_parts and date_parts[0] and date_parts[0][0]:
                year = date_parts[0][0]
                break

        venue = ''
        container = item.get('container-title', [])
        if container:
            venue = container[0]
        elif item.get('event', {}).get('name'):
            venue = item['event']['name']

        return {
            'source': 'crossref',
            'title': title,
            'authors': authors,
            'year': year,
            'venue': venue,
            'doi': item.get('DOI'),
            'arxiv_id': None,
            'url': item.get('URL'),
        }


class OpenAlexClient:
    """OpenAlex API client. Excellent free coverage."""

    BASE_URL = 'https://api.openalex.org'

    def __init__(self):
        self.limiter = RateLimiter(0.1)  # 10 req/s polite
        self.session = requests.Session()
        self.session.headers['User-Agent'] = USER_AGENT

    def search_by_title(self, title, per_page=3):
        """Search for papers by title."""
        self.limiter.wait()
        try:
            resp = self.session.get(
                f'{self.BASE_URL}/works',
                params={
                    'search': title,
                    'per_page': per_page,
                },
                timeout=TIMEOUT)
            if resp.status_code != 200:
                return []
            results = resp.json().get('results', [])
            return [self._normalize(r) for r in results]
        except Exception as e:
            print(f'  OpenAlex search error: {e}', file=sys.stderr)
            return []

    def _normalize(self, item):
        title = item.get('title', '') or ''

        authors = []
        for authorship in item.get('authorships', []):
            author = authorship.get('author', {})
            display_name = author.get('display_name', '')
            if display_name:
                authors.append(_parse_display_name(display_name))

        year = item.get('publication_year')

        venue = ''
        location = item.get('primary_location', {}) or {}
        source = location.get('source', {}) or {}
        venue = source.get('display_name', '') or ''

        doi = item.get('doi', '')
        if doi and doi.startswith('https://doi.org/'):
            doi = doi[len('https://doi.org/'):]

        return {
            'source': 'openalex',
            'title': title,
            'authors': authors,
            'year': year,
            'venue': venue,
            'doi': doi or None,
            'arxiv_id': None,
            'url': item.get('id'),
        }


class SemanticScholarClient:
    """Semantic Scholar API client. Good but rate-limited."""

    BASE_URL = 'https://api.semanticscholar.org/graph/v1'

    def __init__(self, api_key=None):
        self.api_key = api_key or os.environ.get('SEMANTIC_SCHOLAR_API_KEY')
        self.limiter = RateLimiter(1.0 if not self.api_key else 0.1)
        self.session = requests.Session()
        if self.api_key:
            self.session.headers['x-api-key'] = self.api_key

    def search_by_title(self, title, limit=3):
        """Search for papers by title."""
        self.limiter.wait()
        try:
            resp = self.session.get(
                f'{self.BASE_URL}/paper/search',
                params={
                    'query': title,
                    'limit': limit,
                    'fields': 'title,authors,year,venue,externalIds',
                },
                timeout=TIMEOUT)
            if resp.status_code == 429:
                print('  Semantic Scholar rate limited (429)', file=sys.stderr)
                return []
            if resp.status_code != 200:
                return []
            data = resp.json().get('data', [])
            return [self._normalize(item) for item in data if item]
        except Exception as e:
            print(f'  Semantic Scholar search error: {e}', file=sys.stderr)
            return []

    def _normalize(self, item):
        title = item.get('title', '') or ''

        authors = []
        for a in item.get('authors', []):
            name = a.get('name', '')
            if name:
                authors.append(_parse_display_name(name))

        ext_ids = item.get('externalIds', {}) or {}
        doi = ext_ids.get('DOI')
        arxiv_id = ext_ids.get('ArXiv')

        return {
            'source': 'semantic_scholar',
            'title': title,
            'authors': authors,
            'year': item.get('year'),
            'venue': item.get('venue', '') or '',
            'doi': doi,
            'arxiv_id': arxiv_id,
            'url': None,
        }


class DblpClient:
    """DBLP API client. CS papers only."""

    BASE_URL = 'https://dblp.org/search/publ/api'

    def __init__(self):
        self.limiter = RateLimiter(0.2)  # 5 req/s
        self.session = requests.Session()

    def search_by_title(self, title, max_results=3):
        """Search for papers by title."""
        self.limiter.wait()
        try:
            resp = self.session.get(
                self.BASE_URL,
                params={'q': title, 'h': max_results, 'format': 'json'},
                timeout=TIMEOUT)
            if resp.status_code != 200:
                return []
            result = resp.json().get('result', {})
            hits = result.get('hits', {}).get('hit', [])
            return [self._normalize(h.get('info', {})) for h in hits]
        except Exception as e:
            print(f'  DBLP search error: {e}', file=sys.stderr)
            return []

    def _normalize(self, info):
        title = info.get('title', '').rstrip('.')

        # Authors can be a string or a dict with 'author' key
        author_data = info.get('authors', {}).get('author', [])
        if isinstance(author_data, str):
            author_data = [author_data]
        elif isinstance(author_data, dict):
            author_data = [author_data]

        authors = []
        for a in author_data:
            name = a if isinstance(a, str) else a.get('text', '')
            if name:
                authors.append(_parse_display_name(name))

        year = info.get('year')
        if year:
            try:
                year = int(year)
            except ValueError:
                year = None

        venue = info.get('venue', '')

        doi = info.get('doi', '')
        # DBLP doi field is sometimes a path like "journals/corr/abs-2104-09864"
        if doi and not doi.startswith('10.'):
            doi = None

        return {
            'source': 'dblp',
            'title': title,
            'authors': authors,
            'year': year,
            'venue': venue,
            'doi': doi,
            'arxiv_id': None,
            'url': info.get('url'),
        }


class ArxivClient:
    """arXiv API client. Authoritative for arXiv IDs."""

    BASE_URL = 'http://export.arxiv.org/api/query'

    def __init__(self):
        self.limiter = RateLimiter(3.0)  # Conservative: 1 req per 3s
        self.session = requests.Session()

    def lookup_by_id(self, arxiv_id):
        """Look up a paper by arXiv ID."""
        self.limiter.wait()
        try:
            resp = self.session.get(
                self.BASE_URL,
                params={'id_list': arxiv_id, 'max_results': 1},
                timeout=TIMEOUT)
            if resp.status_code != 200:
                return None
            entries = self._parse_atom(resp.text)
            return entries[0] if entries else None
        except Exception as e:
            print(f'  arXiv lookup error: {e}', file=sys.stderr)
            return None

    def search_by_title(self, title, max_results=3):
        """Search arXiv by title (less reliable than ID lookup)."""
        self.limiter.wait()
        try:
            # Escape special characters for arXiv query
            query = f'ti:"{title}"'
            resp = self.session.get(
                self.BASE_URL,
                params={'search_query': query, 'max_results': max_results},
                timeout=TIMEOUT)
            if resp.status_code != 200:
                return []
            return self._parse_atom(resp.text)
        except Exception as e:
            print(f'  arXiv search error: {e}', file=sys.stderr)
            return []

    def _parse_atom(self, xml_text):
        """Parse arXiv Atom XML response."""
        ns = {'atom': 'http://www.w3.org/2005/Atom',
              'arxiv': 'http://arxiv.org/schemas/atom'}

        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return []

        results = []
        for entry in root.findall('atom:entry', ns):
            title_el = entry.find('atom:title', ns)
            title = title_el.text.strip().replace('\n', ' ') if title_el is not None and title_el.text else ''

            authors = []
            for author_el in entry.findall('atom:author', ns):
                name_el = author_el.find('atom:name', ns)
                if name_el is not None and name_el.text:
                    authors.append(_parse_display_name(name_el.text.strip()))

            # Extract year from published date
            pub_el = entry.find('atom:published', ns)
            year = None
            if pub_el is not None and pub_el.text:
                match = re.search(r'(\d{4})', pub_el.text)
                if match:
                    year = int(match.group(1))

            # Extract arXiv ID from id element
            id_el = entry.find('atom:id', ns)
            arxiv_id = None
            if id_el is not None and id_el.text:
                match = re.search(r'(\d{4}\.\d{4,5}(?:v\d+)?)', id_el.text)
                if match:
                    arxiv_id = match.group(1)

            # arXiv doesn't have venue/DOI directly
            # Check for DOI link
            doi = None
            for link in entry.findall('atom:link', ns):
                href = link.get('href', '')
                if 'doi.org' in href:
                    doi = re.sub(r'^https?://(?:dx\.)?doi\.org/', '', href)

            results.append({
                'source': 'arxiv',
                'title': title,
                'authors': authors,
                'year': year,
                'venue': 'arXiv',
                'doi': doi,
                'arxiv_id': arxiv_id,
                'url': id_el.text if id_el is not None else None,
            })

        return results
