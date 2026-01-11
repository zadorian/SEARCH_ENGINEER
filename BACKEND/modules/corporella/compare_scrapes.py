import json
import difflib
import argparse
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def load_scrape_data(filepath: Path) -> dict | None:
    """Loads scrape data from a JSON file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if "pages" not in data:
                logger.error(f"File {filepath} does not contain a 'pages' key.")
                return None
            # Create a dictionary mapping URL to page content for easier access
            pages_by_url = {page['url']: page for page in data.get('pages', []) if 'url' in page}
            return pages_by_url
    except FileNotFoundError:
        logger.error(f"File not found: {filepath}")
        return None
    except json.JSONDecodeError:
        logger.error(f"Error decoding JSON from file: {filepath}")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred loading {filepath}: {e}")
        return None

def compare_content(url: str, page1: dict, page2: dict):
    """Compares the content of two pages with the same URL and returns a diff."""
    content1 = page1.get('content', '')
    content2 = page2.get('content', '')

    if content1 == content2:
        return None # No changes

    # Use difflib for a textual diff
    # Split content into lines for better diff readability
    content1_lines = content1.splitlines()
    content2_lines = content2.splitlines()

    # Generate diff
    differ = difflib.unified_diff(
        content1_lines,
        content2_lines,
        fromfile=f"Old: {url} ({page1.get('timestamp', 'N/A')})",
        tofile=f"New: {url} ({page2.get('timestamp', 'N/A')})",
        lineterm='', # Avoid extra newlines in diff output
        n=3 # Number of context lines
    )

    diff_output = list(differ)

    if not diff_output:
        # Should not happen if content1 != content2, but good practice
        return None

    # *** AI Enhancement Point ***
    # Here, you could potentially send content1 and content2 to an AI
    # to get a summary of the *semantic* changes.
    # For now, we just return the textual diff.
    # ai_summary = get_ai_change_summary(content1, content2)
    # return "\\n".join(diff_output), ai_summary # Fixed newline escape
    # ***************************

    return "\\n".join(diff_output) # Fixed newline escape


def compare_scrapes(name1: str, data1: dict, name2: str, data2: dict): # Modified signature
    """Compares two sets of scrape data and logs the differences.""" # Modified docstring
    logger.info(f"\\n{'='*20} Comparing {name1} vs {name2} {'='*20}") # Use names, add separator


    if data1 is None or data2 is None: # Should not happen if called correctly, but safe check
        logger.error(f"Cannot compare {name1} and {name2} due to missing data.")
        return False # Indicate comparison failed

    urls1 = set(data1.keys())
    urls2 = set(data2.keys())

    added_urls = urls2 - urls1
    removed_urls = urls1 - urls2
    common_urls = urls1 & urls2

    changes_found = False

    if added_urls:
        changes_found = True
        logger.info(f"
--- Pages Added in {name2} ---")
        for url in sorted(added_urls):
            logger.info(f"+ {url} (Timestamp: {data2[url].get('timestamp', 'N/A')})")

    if removed_urls:
        changes_found = True
        logger.info(f"
--- Pages Removed in {name2} (Present in {name1}) ---")
        for url in sorted(removed_urls):
            logger.info(f"- {url} (Timestamp: {data1[url].get('timestamp', 'N/A')})")

    logger.info(f"
--- Comparing Content for {len(common_urls)} Common Pages ---")
    content_changes = []
    for url in sorted(common_urls):
        diff = compare_content(url, data1[url], data2[url])
        if diff:
            changes_found = True
            content_changes.append(diff)
            # Optional: Add AI summary here if implemented
            # logger.info(f"AI Summary for {url}: {ai_summary}")


    if content_changes:
        logger.info(f"
--- Content Differences Found ({len(content_changes)} pages) ---")
        for i, diff_text in enumerate(content_changes):
             print(f"
--- Diff {i+1}/{len(content_changes)} ---")
             print(diff_text)
             print("-" * (len(f"--- Diff {i+1}/{len(content_changes)} ---"))) # Separator line

    if not changes_found:
        logger.info(f"No differences found between {name1} and {name2}.")
    else:
         logger.info(f"Comparison finished. Found differences between {name1} and {name2}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compare multiple website scrape JSON files sequentially.")
    parser.add_argument(
        "files",
        nargs='+',
        help="Paths to the scrape JSON files, in order (oldest to newest)."
    )
    parser.add_argument(
        "--cache-dir",
        default="cache",
        help="Directory containing the cache files (default: cache)"
    )

    args = parser.parse_args()

    if len(args.files) < 2:
        logger.error("Please provide at least two files to compare.")
        exit(1)

    cache_path = Path(args.cache_dir)
    loaded_data = []

    # Load all files first
    logger.info("Loading scrape files...")
    all_files_valid = True
    for filename in args.files:
        filepath = cache_path / filename
        if not filepath.is_file():
            logger.error(f"Input file not found: {filepath}")
            all_files_valid = False
            continue # Skip this file, but report error

        data = load_scrape_data(filepath)
        if data is None:
            logger.warning(f"Skipping comparison involving {filename} due to loading errors.")
            all_files_valid = False # Mark as problematic but continue loading others
            loaded_data.append((filename, None)) # Add placeholder to maintain sequence
        else:
            logger.info(f"Successfully loaded {filename}")
            loaded_data.append((filename, data))

    if not all_files_valid:
        logger.warning("Some files could not be loaded. Comparisons involving them will be skipped.")

    if len(loaded_data) < 2:
         logger.error("Need at least two successfully loaded files to perform a comparison.")
         exit(1)

    # Perform sequential comparisons
    logger.info("\nStarting sequential comparisons...")
    for i in range(len(loaded_data) - 1):
        name1, data1 = loaded_data[i]
        name2, data2 = loaded_data[i+1]

        # Skip comparison if either file failed to load
        if data1 is None or data2 is None:
             logger.warning(f"Skipping comparison between {name1} and {name2} due to loading errors in one or both files.")
             continue

        compare_scrapes(name1, data1, name2, data2)

    logger.info("\nAll comparisons finished.") 