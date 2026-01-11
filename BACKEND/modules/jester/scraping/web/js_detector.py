"""
DRILL JS Detector - Detect pages requiring JavaScript rendering

This module determines whether a page needs to be rendered with Playwright
(slow path) or can be crawled with Colly/HTTP (fast path).

Strategy:
- Conservative by default: when in doubt, use Playwright
- Can be tuned for speed vs. coverage tradeoff
"""

import re
from dataclasses import dataclass
from typing import List, Optional, Set


@dataclass
class JSDetectionResult:
    """Result of JS rendering detection."""
    needs_js: bool
    reason: Optional[str] = None
    confidence: float = 0.0  # 0.0-1.0


class JSDetector:
    """
    Detect if a page requires JavaScript rendering.

    Usage:
        detector = JSDetector()
        result = detector.needs_js_rendering(html, url)
        if result.needs_js:
            # Use Playwright
        else:
            # Use Colly/HTTP response directly
    """

    # SPA framework indicators (high confidence)
    SPA_INDICATORS = [
        '<div id="root"></div>',           # React
        '<div id="__next"></div>',          # Next.js
        '<div id="app"></div>',             # Vue
        '<div id="__nuxt"></div>',          # Nuxt.js
        '<app-root></app-root>',            # Angular
        '<my-app></my-app>',                # Angular (alternative)
        '__NEXT_DATA__',                    # Next.js SSR data
        '__NUXT__',                         # Nuxt.js
        'window.__INITIAL_STATE__',         # Redux/Vuex SSR
        'window.__PRELOADED_STATE__',       # Redux SSR
        'window.__APOLLO_STATE__',          # Apollo GraphQL
        'data-reactroot',                   # React root marker
        'ng-version=',                      # Angular version marker
    ]

    # Framework script patterns (medium confidence)
    FRAMEWORK_PATTERNS = [
        re.compile(r'<script[^>]*src=["\'][^"\']*react[^"\']*\.js', re.I),
        re.compile(r'<script[^>]*src=["\'][^"\']*vue[^"\']*\.js', re.I),
        re.compile(r'<script[^>]*src=["\'][^"\']*angular[^"\']*\.js', re.I),
        re.compile(r'<script[^>]*src=["\'][^"\']*ember[^"\']*\.js', re.I),
        re.compile(r'<script[^>]*src=["\'][^"\']*svelte[^"\']*\.js', re.I),
        re.compile(r'<script[^>]*src=["\'][^"\']*next[^"\']*\.js', re.I),
        re.compile(r'<script[^>]*src=["\'][^"\']*nuxt[^"\']*\.js', re.I),
    ]

    # Noscript warning patterns
    NOSCRIPT_WARNINGS = [
        re.compile(r'<noscript[^>]*>.*?javascript.*?</noscript>', re.I | re.S),
        re.compile(r'<noscript[^>]*>.*?enable.*?</noscript>', re.I | re.S),
        re.compile(r'<noscript[^>]*>.*?browser.*?supported.*?</noscript>', re.I | re.S),
        re.compile(r'<noscript[^>]*>.*?requires.*?</noscript>', re.I | re.S),
    ]

    # Thresholds
    EMPTY_BODY_THRESHOLD = 500  # chars
    SCRIPT_HEAVY_THRESHOLD = 0.3  # script:content ratio

    def __init__(
        self,
        empty_body_threshold: int = 500,
        conservative: bool = True,
    ):
        """
        Initialize JS detector.

        Args:
            empty_body_threshold: Min chars to consider body non-empty
            conservative: If True, more likely to flag as needing JS
        """
        self.empty_body_threshold = empty_body_threshold
        self.conservative = conservative

    def needs_js_rendering(self, html: str, url: str = "") -> JSDetectionResult:
        """
        Check if a page needs JavaScript rendering.

        Args:
            html: Raw HTML content
            url: Optional URL for domain-specific rules

        Returns:
            JSDetectionResult with needs_js flag and reason
        """
        # Check SPA indicators (high confidence)
        for indicator in self.SPA_INDICATORS:
            if indicator in html:
                return JSDetectionResult(
                    needs_js=True,
                    reason=f"SPA indicator: {indicator[:30]}...",
                    confidence=0.95
                )

        # Check framework script patterns
        for pattern in self.FRAMEWORK_PATTERNS:
            if pattern.search(html):
                # Additional check - is there actual content?
                text_content = self._extract_text(html)
                if len(text_content) < self.empty_body_threshold:
                    return JSDetectionResult(
                        needs_js=True,
                        reason=f"Framework script with minimal content",
                        confidence=0.85
                    )

        # Check for empty body
        body_text = self._extract_body_text(html)
        if len(body_text) < self.empty_body_threshold:
            return JSDetectionResult(
                needs_js=True,
                reason=f"Body text too short ({len(body_text)} chars)",
                confidence=0.80
            )

        # Check noscript warnings
        for pattern in self.NOSCRIPT_WARNINGS:
            if pattern.search(html):
                return JSDetectionResult(
                    needs_js=True,
                    reason="Noscript warning present",
                    confidence=0.75
                )

        # Check script-heavy pages (lots of JS, little content)
        script_ratio = self._calculate_script_ratio(html)
        if script_ratio > self.SCRIPT_HEAVY_THRESHOLD and self.conservative:
            text_content = self._extract_text(html)
            if len(text_content) < self.empty_body_threshold * 2:
                return JSDetectionResult(
                    needs_js=True,
                    reason=f"Script-heavy page ({script_ratio:.1%} scripts)",
                    confidence=0.70
                )

        # No JS rendering needed
        return JSDetectionResult(
            needs_js=False,
            reason="Static HTML",
            confidence=0.90
        )

    def _extract_text(self, html: str) -> str:
        """Extract visible text from HTML."""
        # Remove script and style tags
        text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.I | re.S)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.I | re.S)
        text = re.sub(r'<!--.*?-->', '', text, flags=re.S)

        # Remove all HTML tags
        text = re.sub(r'<[^>]+>', ' ', text)

        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text)

        return text.strip()

    def _extract_body_text(self, html: str) -> str:
        """Extract text from body tag only."""
        body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.I | re.S)
        if body_match:
            return self._extract_text(body_match.group(1))
        return self._extract_text(html)

    def _calculate_script_ratio(self, html: str) -> float:
        """Calculate ratio of script content to total content."""
        # Find all scripts
        scripts = re.findall(r'<script[^>]*>.*?</script>', html, re.I | re.S)
        script_size = sum(len(s) for s in scripts)

        total_size = len(html)
        if total_size == 0:
            return 0.0

        return script_size / total_size


class DomainJSRules:
    """
    Domain-specific JS rendering rules.

    Some domains are KNOWN to require JS (or not require it).
    This avoids detection overhead for known patterns.
    """

    # Domains that ALWAYS need JS
    ALWAYS_JS: Set[str] = {
        "facebook.com",
        "instagram.com",
        "twitter.com",
        "x.com",
        "linkedin.com",
        "reddit.com",
        "tiktok.com",
        "pinterest.com",
        "airbnb.com",
        "notion.so",
        "figma.com",
        "canva.com",
        "miro.com",
        "trello.com",
        "asana.com",
    }

    # Domains that NEVER need JS (static sites)
    NEVER_JS: Set[str] = {
        "wikipedia.org",
        "archive.org",
        "github.com",
        "gitlab.com",
        "gov.uk",
        "bbc.com",
        "bbc.co.uk",
        "cnn.com",
        "reuters.com",
        "apnews.com",
    }

    @classmethod
    def get_domain_rule(cls, url: str) -> Optional[bool]:
        """
        Get domain-specific JS rule.

        Returns:
            True if domain always needs JS
            False if domain never needs JS
            None if no rule (use detection)
        """
        from urllib.parse import urlparse

        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()

            # Strip www.
            if domain.startswith("www."):
                domain = domain[4:]

            # Check always-JS domains
            for js_domain in cls.ALWAYS_JS:
                if domain == js_domain or domain.endswith("." + js_domain):
                    return True

            # Check never-JS domains
            for static_domain in cls.NEVER_JS:
                if domain == static_domain or domain.endswith("." + static_domain):
                    return False

            return None

        except Exception:
            return None


def detect_js_requirement(html: str, url: str = "") -> bool:
    """
    Convenience function to detect if JS rendering is needed.

    Args:
        html: Raw HTML content
        url: Optional URL for domain-specific rules

    Returns:
        True if JS rendering is needed
    """
    # Check domain rules first
    domain_rule = DomainJSRules.get_domain_rule(url)
    if domain_rule is not None:
        return domain_rule

    # Fall back to content detection
    detector = JSDetector()
    result = detector.needs_js_rendering(html, url)
    return result.needs_js


# Convenience function for use in DRILL
def needs_playwright(html: str, url: str = "") -> bool:
    """Alias for detect_js_requirement."""
    return detect_js_requirement(html, url)


# CLI test
if __name__ == "__main__":
    import sys

    print("DRILL JS Detector")
    print("=" * 50)

    # Test cases
    test_cases = [
        ("<html><body><h1>Hello World</h1><p>This is a static page with lots of content.</p></body></html>", "Static HTML"),
        ('<html><body><div id="root"></div><script src="react.js"></script></body></html>', "React SPA"),
        ('<html><body><div id="app"></div><script src="vue.js"></script></body></html>', "Vue SPA"),
        ('<html><body><app-root></app-root></body></html>', "Angular SPA"),
        ('<html><body><noscript>Please enable JavaScript to continue.</noscript></body></html>', "Noscript warning"),
    ]

    detector = JSDetector()

    for html, description in test_cases:
        result = detector.needs_js_rendering(html)
        status = "NEEDS JS" if result.needs_js else "STATIC"
        print(f"\n{description}:")
        print(f"  Status: {status}")
        print(f"  Reason: {result.reason}")
        print(f"  Confidence: {result.confidence:.0%}")
