#!/usr/bin/env python3
"""Apply all patches to distributed_scraper.py cleanly."""

with open("/data/SUBMARINE/distributed_scraper.py", "r") as f:
    content = f.read()

print("Applying patches...")

# 1. Add sys.path at module level (after 'import logging')
old_import = "import logging"
new_import = """import logging
import sys

# Setup paths for SUBJECT and PACMAN imports
if "/data" not in sys.path:
    sys.path.insert(0, "/data")
if "/data/CLASSES" not in sys.path:
    sys.path.insert(0, "/data/CLASSES")
if "/data/SUBMARINE" not in sys.path:
    sys.path.insert(0, "/data/SUBMARINE")"""

content = content.replace(old_import, new_import, 1)
print("  1. Added sys.path setup")

# 2. Add outlinks to ES mapping (after industries)
old_mapping = """"industries": {"type": "nested", "properties": {
                                    "name": {"type": "keyword"},
                                    "confidence": {"type": "float"},
                                    "language": {"type": "keyword"},
                                    "matched_term": {"type": "text"},
                                }},
                            }"""

new_mapping = """"industries": {"type": "nested", "properties": {
                                    "name": {"type": "keyword"},
                                    "confidence": {"type": "float"},
                                    "language": {"type": "keyword"},
                                    "matched_term": {"type": "text"},
                                }},
                                "outlinks": {"type": "nested", "properties": {
                                    "url": {"type": "keyword"},
                                    "text": {"type": "text"},
                                    "domain": {"type": "keyword"},
                                    "is_external": {"type": "boolean"},
                                }},
                                "outlinks_external": {"type": "nested", "properties": {
                                    "url": {"type": "keyword"},
                                    "text": {"type": "text"},
                                    "domain": {"type": "keyword"},
                                    "is_external": {"type": "boolean"},
                                }},
                            }"""

content = content.replace(old_mapping, new_mapping)
print("  2. Added outlinks to ES mapping")

# 3. Change _extract_full signature to include url
old_sig = "async def _extract_full(self, html: str, text: str) -> Dict[str, Any]:"
new_sig = "async def _extract_full(self, html: str, text: str, url: str = \"\") -> Dict[str, Any]:"
content = content.replace(old_sig, new_sig)
print("  3. Updated _extract_full signature")

# 4. Add outlinks to result dict
old_result = """"industries": [],   # NEW: from SUBJECT (more granular)
        }"""
new_result = """"industries": [],   # NEW: from SUBJECT (more granular)
            "outlinks": [],
            "outlinks_external": [],
        }"""
content = content.replace(old_result, new_result)
print("  4. Added outlinks to result dict")

# 5. Update call to _extract_full to include page.url
old_call = "extraction = await self._extract_full(page.html, page.text)"
new_call = "extraction = await self._extract_full(page.html, page.text, page.url)"
content = content.replace(old_call, new_call)
print("  5. Updated _extract_full call")

# 6. Add outlinks to doc structure (after professions)
old_doc = """"professions": extraction.get("professions", []),
                    "titles": extraction.get("titles", []),
                    "industries": extraction.get("industries", []),
                }"""
new_doc = """"professions": extraction.get("professions", []),
                    "titles": extraction.get("titles", []),
                    "industries": extraction.get("industries", []),
                    "outlinks": extraction.get("outlinks", []),
                    "outlinks_external": extraction.get("outlinks_external", []),
                }"""
content = content.replace(old_doc, new_doc)
print("  6. Added outlinks to doc structure")

# 7. Add outlinks extraction code (before return result at end of _extract_full)
# Find the LAST "return result" that's inside _extract_full
# We need to add outlinks extraction before this

old_return = """        # 3. Person/Company extraction (first-names library + company designations)
        try:
            import sys
            if '/data/SUBMARINE' not in sys.path:
                sys.path.insert(0, '/data/SUBMARINE')

            from simple_extractor import extract_persons, extract_companies

            # Extract persons (uses first-names library)
            persons = extract_persons(content[:100000], max_results=50)
            for p in persons:
                if p['name'] not in [x.get('name') for x in result['persons']]:
                    result['persons'].append({
                        'name': p['name'],
                        'confidence': p['confidence'],
                        'source': p.get('source', 'regex'),
                        'snippet': p.get('snippet', ''),
                    })

            # Extract companies (uses company designations: Ltd, Inc, GmbH, etc.)
            companies = extract_companies(content[:100000], max_results=50)
            for c in companies:
                if c['name'] not in [x.get('name') for x in result['companies']]:
                    result['companies'].append({
                        'name': c['name'],
                        'confidence': c['confidence'],
                        'suffix': c.get('suffix'),
                        'source': c.get('source', 'regex'),
                        'snippet': c.get('snippet', ''),
                    })

        except Exception as e:
            logger.debug(f"Person/company extraction failed: {e}")

        return result"""

new_return = """        # 3. Person/Company extraction (first-names library + company designations)
        try:
            import sys
            if '/data/SUBMARINE' not in sys.path:
                sys.path.insert(0, '/data/SUBMARINE')

            from simple_extractor import extract_persons, extract_companies

            # Extract persons (uses first-names library)
            persons = extract_persons(content[:100000], max_results=50)
            for p in persons:
                if p['name'] not in [x.get('name') for x in result['persons']]:
                    result['persons'].append({
                        'name': p['name'],
                        'confidence': p['confidence'],
                        'source': p.get('source', 'regex'),
                        'snippet': p.get('snippet', ''),
                    })

            # Extract companies (uses company designations: Ltd, Inc, GmbH, etc.)
            companies = extract_companies(content[:100000], max_results=50)
            for c in companies:
                if c['name'] not in [x.get('name') for x in result['companies']]:
                    result['companies'].append({
                        'name': c['name'],
                        'confidence': c['confidence'],
                        'suffix': c.get('suffix'),
                        'source': c.get('source', 'regex'),
                        'snippet': c.get('snippet', ''),
                    })

        except Exception as e:
            logger.debug(f"Person/company extraction failed: {e}")

        # 4. Outlinks extraction
        if html and url:
            try:
                from outlink_extractor import extract_outlinks
                all_links = extract_outlinks(html, url, max_links=100)
                result["outlinks"] = all_links
                result["outlinks_external"] = [l for l in all_links if l.get("is_external")]
            except Exception as e:
                logger.debug(f"Outlinks extraction failed: {e}")

        return result"""

content = content.replace(old_return, new_return)
print("  7. Added outlinks extraction code")

# Write the patched file
with open("/data/SUBMARINE/distributed_scraper.py", "w") as f:
    f.write(content)

print("\nAll patches applied successfully!")
