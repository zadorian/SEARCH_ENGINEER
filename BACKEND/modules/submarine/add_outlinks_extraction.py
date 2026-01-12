#!/usr/bin/env python3
"""Add outlinks extraction to _extract_full method."""

with open("/data/SUBMARINE/distributed_scraper.py", "r") as f:
    content = f.read()

# Find the return statement that ends _extract_full (before scrape_batch)
old_code = """            except Exception as e:
                logger.debug(f"PACMAN extraction failed: {e}")

        return result

    async def scrape_batch("""

new_code = """            except Exception as e:
                logger.debug(f"PACMAN extraction failed: {e}")

        # 4. Outlinks extraction (extract all links from HTML)
        if html and url:
            try:
                import sys
                if "/data/SUBMARINE" not in sys.path:
                    sys.path.insert(0, "/data/SUBMARINE")
                from outlink_extractor import extract_outlinks
                all_links = extract_outlinks(html, url, max_links=100)
                result["outlinks"] = all_links
                result["outlinks_external"] = [l for l in all_links if l.get("is_external")]
            except Exception as e:
                logger.debug(f"Outlinks extraction failed: {e}")

        return result

    async def scrape_batch("""

if old_code in content:
    content = content.replace(old_code, new_code)
    with open("/data/SUBMARINE/distributed_scraper.py", "w") as f:
        f.write(content)
    print("SUCCESS: Added outlinks extraction code")
else:
    print("ERROR: Could not find target code block")
    # Debug - show what we have
    import re
    m = re.search(r"PACMAN extraction failed.*?return result", content, re.DOTALL)
    if m:
        print(f"Found similar: {repr(m.group()[:100])}")
