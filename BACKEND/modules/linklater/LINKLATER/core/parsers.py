"""
WARC Parser - Extract content from Common Crawl WARC records (HTML and binary files).

WARC format:
    WARC/1.0
    WARC-Type: response
    WARC-Target-URI: https://example.com
    ...headers...

    HTTP/1.1 200 OK
    Content-Type: text/html|application/pdf|etc
    ...http headers...

    <html>...actual content...</html>  OR  (binary data)

This is the canonical implementation - replaces:
- scraping/warc_parser.py
- scraping/historical/warc_parser.py
"""

import gzip
import re
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class WARCParser:
    """Parse WARC records and extract content (HTML or binary files)."""

    @staticmethod
    def extract_html(warc_data: bytes) -> Optional[str]:
        """
        Extract HTML body from a WARC record.

        Args:
            warc_data: Raw (possibly gzipped) WARC record bytes

        Returns:
            HTML content as string, or None if extraction fails
        """
        try:
            # Decompress if gzipped
            if warc_data[:2] == b'\x1f\x8b':
                warc_data = gzip.decompress(warc_data)

            # Decode to string
            text = warc_data.decode('utf-8', errors='replace')

            # Find the HTTP response body (after double CRLF in HTTP headers)
            # WARC structure: WARC headers \r\n\r\n HTTP response
            # HTTP response: HTTP status + headers \r\n\r\n body

            # Skip WARC headers
            warc_body_start = text.find('\r\n\r\n')
            if warc_body_start == -1:
                warc_body_start = text.find('\n\n')
                if warc_body_start == -1:
                    return None

            http_response = text[warc_body_start + 4:]

            # Skip HTTP headers to get body
            http_body_start = http_response.find('\r\n\r\n')
            if http_body_start == -1:
                http_body_start = http_response.find('\n\n')
                if http_body_start == -1:
                    return None

            html_body = http_response[http_body_start + 4:]

            # Clean up - remove trailing WARC record boundaries
            if '\r\n\r\n' in html_body:
                # Sometimes there's trailing WARC metadata
                parts = html_body.split('\r\n\r\nWARC/')
                html_body = parts[0]

            return html_body.strip()

        except Exception as e:
            logger.warning(f"Error extracting HTML: {e}")
            return None

    @staticmethod
    def extract_metadata(warc_data: bytes) -> dict:
        """
        Extract metadata from WARC headers.

        Returns:
            Dict with keys: url, timestamp, status, content_type
        """
        metadata = {
            'url': None,
            'timestamp': None,
            'status': None,
            'content_type': None
        }

        try:
            if warc_data[:2] == b'\x1f\x8b':
                warc_data = gzip.decompress(warc_data)

            # Parse first section (WARC headers)
            text = warc_data.decode('utf-8', errors='replace')
            header_end = text.find('\r\n\r\n')
            if header_end == -1:
                header_end = text.find('\n\n')

            if header_end != -1:
                headers = text[:header_end]

                # Extract WARC-Target-URI
                uri_match = re.search(r'WARC-Target-URI:\s*(.+)', headers)
                if uri_match:
                    metadata['url'] = uri_match.group(1).strip()

                # Extract WARC-Date
                date_match = re.search(r'WARC-Date:\s*(.+)', headers)
                if date_match:
                    metadata['timestamp'] = date_match.group(1).strip()

            # Parse HTTP headers for status and content-type
            http_start = header_end + 4 if header_end != -1 else 0
            http_section = text[http_start:]
            http_header_end = http_section.find('\r\n\r\n')
            if http_header_end == -1:
                http_header_end = http_section.find('\n\n')

            if http_header_end != -1:
                http_headers = http_section[:http_header_end]

                # HTTP status
                status_match = re.search(r'HTTP/\d\.\d\s+(\d+)', http_headers)
                if status_match:
                    metadata['status'] = int(status_match.group(1))

                # Content-Type
                ct_match = re.search(r'Content-Type:\s*([^\r\n;]+)', http_headers, re.I)
                if ct_match:
                    metadata['content_type'] = ct_match.group(1).strip()

        except Exception as e:
            logger.warning(f"Error extracting metadata: {e}")

        return metadata

    @staticmethod
    def extract_binary(warc_data: bytes) -> Tuple[Optional[bytes], Optional[str]]:
        """
        Extract binary content and content-type from a WARC record.

        Args:
            warc_data: Raw (possibly gzipped) WARC record bytes

        Returns:
            Tuple of (binary_content, content_type) or (None, None) if extraction fails
        """
        try:
            # Decompress if gzipped
            if warc_data[:2] == b'\x1f\x8b':
                warc_data = gzip.decompress(warc_data)

            # Find the boundary between HTTP headers and body
            # We need to work with bytes, not strings, for binary data

            # Find end of WARC headers (first \r\n\r\n or \n\n)
            warc_header_end = warc_data.find(b'\r\n\r\n')
            if warc_header_end == -1:
                warc_header_end = warc_data.find(b'\n\n')
                if warc_header_end == -1:
                    return None, None
                http_start = warc_header_end + 2
            else:
                http_start = warc_header_end + 4

            # Find end of HTTP headers (second \r\n\r\n or \n\n)
            http_response = warc_data[http_start:]
            http_header_end = http_response.find(b'\r\n\r\n')
            if http_header_end == -1:
                http_header_end = http_response.find(b'\n\n')
                if http_header_end == -1:
                    return None, None
                body_start = http_header_end + 2
            else:
                body_start = http_header_end + 4

            # Extract HTTP headers to get Content-Type
            http_headers = http_response[:http_header_end].decode('utf-8', errors='replace')
            content_type = None
            ct_match = re.search(r'Content-Type:\s*([^\r\n;]+)', http_headers, re.I)
            if ct_match:
                content_type = ct_match.group(1).strip()

            # Extract binary body
            binary_content = http_response[body_start:]

            # Clean up trailing WARC metadata if present
            # Look for WARC/ marker at the end
            warc_trailer = binary_content.find(b'\r\n\r\nWARC/')
            if warc_trailer != -1:
                binary_content = binary_content[:warc_trailer]

            return binary_content, content_type

        except Exception as e:
            logger.warning(f"Error extracting binary: {e}")
            return None, None


def html_to_markdown(html: str) -> str:
    """
    Convert HTML to clean markdown text.
    Basic implementation - strips tags and normalizes whitespace.
    For better results, use a dedicated library like markdownify.
    """
    # Remove script and style elements
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.I)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.I)

    # Convert common elements
    html = re.sub(r'<h1[^>]*>(.*?)</h1>', r'\n# \1\n', html, flags=re.DOTALL | re.I)
    html = re.sub(r'<h2[^>]*>(.*?)</h2>', r'\n## \1\n', html, flags=re.DOTALL | re.I)
    html = re.sub(r'<h3[^>]*>(.*?)</h3>', r'\n### \1\n', html, flags=re.DOTALL | re.I)
    html = re.sub(r'<p[^>]*>(.*?)</p>', r'\n\1\n', html, flags=re.DOTALL | re.I)
    html = re.sub(r'<br\s*/?>', '\n', html, flags=re.I)
    html = re.sub(r'<li[^>]*>(.*?)</li>', r'- \1\n', html, flags=re.DOTALL | re.I)

    # Extract link text
    html = re.sub(r'<a[^>]*>(.*?)</a>', r'\1', html, flags=re.DOTALL | re.I)

    # Remove remaining tags
    html = re.sub(r'<[^>]+>', '', html)

    # Decode entities
    html = html.replace('&nbsp;', ' ')
    html = html.replace('&amp;', '&')
    html = html.replace('&lt;', '<')
    html = html.replace('&gt;', '>')
    html = html.replace('&quot;', '"')

    # Normalize whitespace
    html = re.sub(r'\n\s*\n', '\n\n', html)
    html = re.sub(r'[ \t]+', ' ', html)

    return html.strip()
