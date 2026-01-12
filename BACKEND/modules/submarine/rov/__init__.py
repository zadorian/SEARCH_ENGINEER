"""
ROV (Remotely Operated Vehicle) - SUBMARINE Authentication Plugin

Enables deep-sea scraping of authenticated content by injecting
browser session cookies into requests.
"""

from .session_injector import SessionInjector, export_cookies_from_browser_instructions

__all__ = ['SessionInjector', 'export_cookies_from_browser_instructions']
