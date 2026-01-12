"""
Memento TimeMap submodule for BACKDRILL.

Provides access to 40+ web archives via Memento protocol:
- Internet Archive (archive.org)
- Archive.today / Archive.is
- Perma.cc
- UK Web Archive (webarchive.org.uk)
- Portuguese Web Archive (arquivo.pt)
- Croatian Web Archive
- Australian Web Archive (webarchive.nla.gov.au)
- Library of Congress (webarchive.loc.gov)
- Stanford Web Archive
- And many more...

SOURCE FILES:
- memento.py ← DATA/archives/archive_browser 21.58.44.py
"""

from .memento import Memento

__all__ = ["Memento"]
