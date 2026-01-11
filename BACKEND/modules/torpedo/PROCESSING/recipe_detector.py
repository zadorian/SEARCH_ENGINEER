#!/usr/bin/env python3
"""
RECIPE DETECTOR - Auto-detect extraction patterns from news search pages.

Analyzes HTML to find:
1. Search Results Recipe - container, title, url, snippet, date selectors
2. Article Recipe - headline, body, author, date selectors

Used by news_processor.py to generate extraction recipes for each source.
"""

import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from bs4 import BeautifulSoup, Tag
from collections import Counter


@dataclass
class SearchRecipe:
    """Recipe for extracting search results from a news site."""
    container: str  # CSS selector for result container
    title: str      # Selector for title (relative to container)
    url: str        # Selector for URL (relative to container)
    snippet: str    # Selector for snippet text
    date: Optional[str] = None  # Selector for date
    confidence: float = 0.0  # How confident we are in this recipe

    def to_dict(self) -> Dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class ArticleRecipe:
    """Recipe for extracting article content."""
    headline: str
    body: str
    author: Optional[str] = None
    date: Optional[str] = None
    confidence: float = 0.0

    def to_dict(self) -> Dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


class RecipeDetector:
    """
    Detects extraction patterns from HTML.

    Strategy:
    1. Find repeating container elements (article, div, li with similar structure)
    2. Within containers, find title links, snippet paragraphs, dates
    3. Generate CSS selectors based on detected patterns
    """

    # Common container patterns
    CONTAINER_TAGS = ['article', 'div', 'li', 'section']
    CONTAINER_CLASSES = ['result', 'item', 'entry', 'post', 'article', 'news', 'story', 'card']

    # Common title patterns
    TITLE_TAGS = ['h1', 'h2', 'h3', 'h4', 'a']
    TITLE_CLASSES = ['title', 'headline', 'heading', 'name', 'link']

    # Common snippet patterns
    SNIPPET_TAGS = ['p', 'div', 'span']
    SNIPPET_CLASSES = ['snippet', 'description', 'summary', 'excerpt', 'text', 'preview', 'teaser']

    # Common date patterns
    DATE_TAGS = ['time', 'span', 'div', 'p']
    DATE_CLASSES = ['date', 'time', 'published', 'datetime', 'timestamp', 'when']

    def __init__(self):
        pass

    def detect_search_recipe(self, html: str, query: str = None) -> Optional[SearchRecipe]:
        """
        Detect search results extraction recipe from HTML.

        Args:
            html: Raw HTML from search results page
            query: The search query (helps identify relevant content)

        Returns:
            SearchRecipe with CSS selectors, or None if detection failed
        """
        soup = BeautifulSoup(html, 'html.parser')

        # Strategy 1: Look for <article> tags (common pattern)
        articles = soup.find_all('article')
        if len(articles) >= 3:
            recipe = self._analyze_containers(articles, 'article')
            if recipe and recipe.confidence > 0.5:
                return recipe

        # Strategy 2: Look for repeated div/li with result-like classes
        for class_hint in self.CONTAINER_CLASSES:
            containers = soup.find_all(class_=re.compile(class_hint, re.I))
            if len(containers) >= 3:
                # Get the tag name of first container
                tag = containers[0].name
                selector = f'{tag}.{class_hint}' if tag else f'.{class_hint}'
                recipe = self._analyze_containers(containers, selector)
                if recipe and recipe.confidence > 0.5:
                    return recipe

        # Strategy 3: Find links with substantial text and look for their parent pattern
        recipe = self._detect_from_links(soup, query)
        if recipe and recipe.confidence > 0.4:
            return recipe

        # Strategy 4: Fallback - generic extraction
        return self._generic_recipe(soup)

    def _analyze_containers(self, containers: List[Tag], container_selector: str) -> Optional[SearchRecipe]:
        """Analyze a set of containers to find common patterns."""
        if len(containers) < 2:
            return None

        title_patterns = Counter()
        url_patterns = Counter()
        snippet_patterns = Counter()
        date_patterns = Counter()

        for container in containers[:10]:  # Analyze first 10
            # Find title (usually the first substantial link)
            for tag in ['h1', 'h2', 'h3', 'h4']:
                h = container.find(tag)
                if h:
                    a = h.find('a')
                    if a and len(a.get_text(strip=True)) > 10:
                        title_patterns[f'{tag} > a'] += 1
                        url_patterns[f'{tag} > a[href]'] += 1
                        break
            else:
                # No heading with link, look for prominent link
                links = container.find_all('a')
                for a in links:
                    text = a.get_text(strip=True)
                    if 20 < len(text) < 200:
                        # Get selector for this link
                        classes = a.get('class', [])
                        if classes:
                            title_patterns[f'a.{classes[0]}'] += 1
                            url_patterns[f'a.{classes[0]}[href]'] += 1
                        else:
                            title_patterns['a'] += 1
                            url_patterns['a[href]'] += 1
                        break

            # Find snippet (paragraph with substantial text)
            for p in container.find_all('p'):
                text = p.get_text(strip=True)
                if 30 < len(text) < 500:
                    classes = p.get('class', [])
                    if classes:
                        snippet_patterns[f'p.{classes[0]}'] += 1
                    else:
                        snippet_patterns['p'] += 1
                    break

            # Find date
            time_tag = container.find('time')
            if time_tag:
                date_patterns['time'] += 1
            else:
                for tag in container.find_all(['span', 'div']):
                    classes = tag.get('class', [])
                    for c in classes:
                        if any(d in c.lower() for d in ['date', 'time', 'published']):
                            date_patterns[f'{tag.name}.{c}'] += 1
                            break

        # Pick most common patterns
        title_sel = title_patterns.most_common(1)[0][0] if title_patterns else 'a'
        url_sel = url_patterns.most_common(1)[0][0] if url_patterns else 'a[href]'
        snippet_sel = snippet_patterns.most_common(1)[0][0] if snippet_patterns else 'p'
        date_sel = date_patterns.most_common(1)[0][0] if date_patterns else None

        # Calculate confidence
        total_votes = sum(title_patterns.values()) + sum(snippet_patterns.values())
        max_votes = len(containers) * 2
        confidence = min(1.0, total_votes / max_votes) if max_votes > 0 else 0.0

        return SearchRecipe(
            container=container_selector,
            title=title_sel,
            url=url_sel,
            snippet=snippet_sel,
            date=date_sel,
            confidence=confidence
        )

    def _detect_from_links(self, soup: BeautifulSoup, query: str = None) -> Optional[SearchRecipe]:
        """Detect pattern by finding substantial links and their parent structure."""
        # Find all links with meaningful text
        candidate_links = []
        for a in soup.find_all('a', href=True):
            text = a.get_text(strip=True)
            href = a.get('href', '')

            # Filter for article-like links
            if 25 < len(text) < 200 and href and not href.startswith('#'):
                # Skip navigation links
                if any(nav in href.lower() for nav in ['/category/', '/tag/', '/author/', 'javascript:']):
                    continue
                candidate_links.append(a)

        if len(candidate_links) < 3:
            return None

        # Find common parent pattern
        parent_tags = Counter()
        for a in candidate_links[:10]:
            parent = a.find_parent(['article', 'div', 'li', 'section'])
            if parent:
                tag = parent.name
                classes = parent.get('class', [])
                if classes:
                    parent_tags[f'{tag}.{classes[0]}'] += 1
                else:
                    parent_tags[tag] += 1

        if not parent_tags:
            return None

        container_sel = parent_tags.most_common(1)[0][0]

        # Now analyze those containers
        containers = soup.select(container_sel)[:10]
        if containers:
            return self._analyze_containers(containers, container_sel)

        return None

    def _generic_recipe(self, soup: BeautifulSoup) -> SearchRecipe:
        """Fallback generic recipe when specific detection fails."""
        # Check for common patterns
        if soup.find_all('article'):
            return SearchRecipe(
                container='article',
                title='h1 a, h2 a, h3 a, a',
                url='a[href]',
                snippet='p',
                date='time',
                confidence=0.3
            )

        return SearchRecipe(
            container='div',
            title='a',
            url='a[href]',
            snippet='p',
            date='time, .date',
            confidence=0.2
        )

    def detect_article_recipe(self, html: str) -> Optional[ArticleRecipe]:
        """
        Detect article content extraction recipe.

        Args:
            html: Raw HTML from article page

        Returns:
            ArticleRecipe with CSS selectors
        """
        soup = BeautifulSoup(html, 'html.parser')

        # Find headline (usually h1)
        headline_sel = None
        for h1 in soup.find_all('h1'):
            text = h1.get_text(strip=True)
            if 20 < len(text) < 300:
                classes = h1.get('class', [])
                if classes:
                    headline_sel = f'h1.{classes[0]}'
                else:
                    headline_sel = 'h1'
                break

        # Find body (article, main content div)
        body_sel = None
        for selector in ['article', 'div.article-body', 'div.content', 'div.story-body', 'main']:
            el = soup.select_one(selector)
            if el and len(el.get_text(strip=True)) > 500:
                body_sel = selector
                break

        if not body_sel:
            # Look for div with most paragraph content
            for div in soup.find_all('div'):
                paras = div.find_all('p')
                if len(paras) >= 3:
                    total_text = sum(len(p.get_text()) for p in paras)
                    if total_text > 500:
                        classes = div.get('class', [])
                        body_sel = f'div.{classes[0]}' if classes else 'div'
                        break

        # Find author
        author_sel = None
        for class_hint in ['author', 'byline', 'writer']:
            el = soup.find(class_=re.compile(class_hint, re.I))
            if el:
                tag = el.name
                classes = el.get('class', [])
                author_sel = f'{tag}.{classes[0]}' if classes else f'.{class_hint}'
                break

        # Find date
        date_sel = None
        time_tag = soup.find('time')
        if time_tag:
            date_sel = 'time'
        else:
            for class_hint in ['date', 'published', 'datetime']:
                el = soup.find(class_=re.compile(class_hint, re.I))
                if el:
                    classes = el.get('class', [])
                    date_sel = f'.{classes[0]}' if classes else f'.{class_hint}'
                    break

        if not headline_sel and not body_sel:
            return None

        return ArticleRecipe(
            headline=headline_sel or 'h1',
            body=body_sel or 'article',
            author=author_sel,
            date=date_sel,
            confidence=0.6 if (headline_sel and body_sel) else 0.3
        )

    def extract_with_recipe(self, html: str, recipe: SearchRecipe) -> List[Dict]:
        """
        Extract search results using a recipe.

        Args:
            html: Raw HTML
            recipe: SearchRecipe with selectors

        Returns:
            List of extracted results with title, url, snippet, date
        """
        soup = BeautifulSoup(html, 'html.parser')
        results = []

        containers = soup.select(recipe.container)

        for container in containers:
            result = {}

            # Extract title
            title_el = container.select_one(recipe.title)
            if title_el:
                result['title'] = title_el.get_text(strip=True)

            # Extract URL
            url_el = container.select_one(recipe.url)
            if url_el:
                result['url'] = url_el.get('href', '')

            # Extract snippet
            snippet_el = container.select_one(recipe.snippet)
            if snippet_el:
                result['snippet'] = snippet_el.get_text(strip=True)

            # Extract date
            if recipe.date:
                date_el = container.select_one(recipe.date)
                if date_el:
                    result['date'] = date_el.get('datetime') or date_el.get_text(strip=True)

            # Only add if we got meaningful data
            if result.get('title') and len(result['title']) > 10:
                results.append(result)

        return results


# Test
if __name__ == '__main__':
    import httpx

    # Test with Repubblica
    url = 'https://ricerca.repubblica.it/ricerca/repubblica?query=mafia'
    try:
        r = httpx.get(url, timeout=30, follow_redirects=True)

        detector = RecipeDetector()
        recipe = detector.detect_search_recipe(r.text, 'mafia')

        print(f'Detected Recipe:')
        print(f'  Container: {recipe.container}')
        print(f'  Title: {recipe.title}')
        print(f'  URL: {recipe.url}')
        print(f'  Snippet: {recipe.snippet}')
        print(f'  Date: {recipe.date}')
        print(f'  Confidence: {recipe.confidence:.2f}')

        print()
        print('Extracted Results:')
        results = detector.extract_with_recipe(r.text, recipe)
        for r in results[:5]:
            print(f"  - {r.get('title', '')[:60]}...")
            print(f"    {r.get('snippet', '')[:80]}...")
            print(f"    {r.get('url', '')[:60]}")
            print()

    except Exception as e:
        print(f'Error: {e}')
