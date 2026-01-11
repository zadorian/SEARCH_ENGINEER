import sys
import requests
import bisect
import gzip
import json
import os
from io import BytesIO
import asyncio
import aiohttp

# Configuration
CC_DATA_URL = "https://data.commoncrawl.org"
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

class CCIndexOfflineLookup:
    def __init__(self, archive="CC-MAIN-2024-10"):
        self.archive = archive
        self.index_base = f"{CC_DATA_URL}/cc-index/collections/{archive}/indexes"
        self.cluster_idx_url = f"{self.index_base}/cluster.idx"
        self.cluster_idx_path = os.path.join(DATA_DIR, f"cluster_{archive}.idx")
        self.cluster_idx = [] # Cache for the index keys
        self._cluster_keys = []

    def fetch_cluster_index(self):
        """
        Downloads the cluster.idx file if not present locally.
        Loads it into memory.
        """
        if not os.path.exists(self.cluster_idx_path):
            print(f"[*] Downloading cluster index for {self.archive}...", file=sys.stderr)
            resp = requests.get(self.cluster_idx_url)
            if resp.status_code != 200:
                raise Exception(f"Failed to download cluster.idx: {resp.status_code}")
            
            with open(self.cluster_idx_path, 'wb') as f:
                f.write(resp.content)
            print(f"[*] Saved cluster index to {self.cluster_idx_path}", file=sys.stderr)
        else:
            print(f"[*] Loading cached cluster index from {self.cluster_idx_path}...", file=sys.stderr)
        
        # Load into memory
        with open(self.cluster_idx_path, 'r') as f:
            lines = f.readlines()
            
        # Format: key timestamp filename offset length shard
        self.cluster_idx = []
        for line in lines:
            # Use default split to handle mixed tabs/spaces
            parts = line.split()
            if len(parts) >= 5:
                try:
                    # key = parts[0]
                    # timestamp = parts[1]
                    # filename = parts[2]
                    # offset = int(parts[3])
                    # length = int(parts[4])
                    
                    self.cluster_idx.append((parts[0], parts[2], int(parts[3]), int(parts[4])))
                except ValueError:
                    continue
        
        print(f"[*] Loaded {len(self.cluster_idx)} index blocks.", file=sys.stderr)
        self._cluster_keys = [x[0] for x in self.cluster_idx]

    def _get_blocks_for_domain(self, domain, max_blocks=20, ensure_loaded=True):
        if ensure_loaded and not self.cluster_idx:
            self.fetch_cluster_index()

        # Reverse domain for SURT key: com,soax
        parts = domain.split('.')
        reversed_domain = ",".join(parts[::-1])

        # Binary search to find the block
        keys = self._cluster_keys or [x[0] for x in self.cluster_idx]
        idx = bisect.bisect_right(keys, reversed_domain) - 1

        if idx < 0:
            return [], reversed_domain

        blocks = []
        for i in range(idx, min(len(self.cluster_idx), idx + max_blocks)):
            block_key, filename, offset, length = self.cluster_idx[i]
            if i > idx and block_key > reversed_domain and not block_key.startswith(reversed_domain):
                break
            blocks.append((block_key, filename, offset, length))

        return blocks, reversed_domain

    async def _ensure_index_ready(self):
        if self.cluster_idx:
            return
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.fetch_cluster_index)

    def _extract_records(self, lines, reversed_domain, include_wat=True):
        results = []
        unique_wats = set()

        for line in lines:
            try:
                parts = line.split(None, 2)
                if len(parts) < 3:
                    continue

                key = parts[0]
                if not key.startswith(reversed_domain):
                    continue

                suffix = key[len(reversed_domain):]
                if suffix and suffix[0] not in [')', ',']:
                    continue

                meta = json.loads(parts[2])
                warc_file = meta.get('filename', '')
                if 'robotstxt' in warc_file or 'crawldiagnostics' in warc_file:
                    continue

                if include_wat:
                    wat_file = warc_file.replace('/warc/', '/wat/').replace('.warc.gz', '.warc.wat.gz')
                    if wat_file in unique_wats:
                        continue
                    unique_wats.add(wat_file)
                    results.append({
                        'url': meta.get('url'),
                        'wat_filename': wat_file,
                        'timestamp': meta.get('timestamp'),
                    })
                else:
                    results.append({
                        'url': meta.get('url'),
                        'timestamp': meta.get('timestamp'),
                        'warc_filename': warc_file,
                    })
            except Exception:
                continue

        return results

    async def lookup_domain_async(self, domain, limit=100, max_blocks=20, max_concurrent=8):
        """
        Async lookup for domain records with parallel range requests.
        """
        await self._ensure_index_ready()
        blocks, reversed_domain = self._get_blocks_for_domain(domain, max_blocks=max_blocks, ensure_loaded=False)
        if not blocks:
            return []

        async def fetch_block(session, block):
            block_key, filename, offset, length = block
            shard_url = f"{self.index_base}/{filename}"
            headers = {"Range": f"bytes={offset}-{offset + length - 1}"}
            try:
                async with session.get(shard_url, headers=headers) as resp:
                    if resp.status not in [200, 206]:
                        return []
                    content = gzip.decompress(await resp.read())
                    lines = content.decode('utf-8', errors='ignore').splitlines()
                    return self._extract_records(lines, reversed_domain, include_wat=True)
            except Exception:
                return []

        results = []
        async with aiohttp.ClientSession() as session:
            sem = asyncio.Semaphore(max(1, int(max_concurrent)))

            async def guarded_fetch(block):
                async with sem:
                    return await fetch_block(session, block)

            tasks = [guarded_fetch(block) for block in blocks]
            block_results = await asyncio.gather(*tasks, return_exceptions=True)

        for block_result in block_results:
            if not block_result or isinstance(block_result, Exception):
                continue
            for item in block_result:
                results.append(item)
                if len(results) >= limit:
                    return results[:limit]

        return results[:limit]

    async def scan_index_only(self, domain, limit=1000, max_blocks=20, max_concurrent=8):
        """
        Index-only scan: returns URL list without fetching WAT content.
        """
        await self._ensure_index_ready()
        blocks, reversed_domain = self._get_blocks_for_domain(domain, max_blocks=max_blocks, ensure_loaded=False)
        if not blocks:
            return []

        async def fetch_block(session, block):
            block_key, filename, offset, length = block
            shard_url = f"{self.index_base}/{filename}"
            headers = {"Range": f"bytes={offset}-{offset + length - 1}"}
            try:
                async with session.get(shard_url, headers=headers) as resp:
                    if resp.status not in [200, 206]:
                        return []
                    content = gzip.decompress(await resp.read())
                    lines = content.decode('utf-8', errors='ignore').splitlines()
                    return self._extract_records(lines, reversed_domain, include_wat=False)
            except Exception:
                return []

        results = []
        seen_urls = set()
        async with aiohttp.ClientSession() as session:
            sem = asyncio.Semaphore(max(1, int(max_concurrent)))

            async def guarded_fetch(block):
                async with sem:
                    return await fetch_block(session, block)

            tasks = [guarded_fetch(block) for block in blocks]
            block_results = await asyncio.gather(*tasks, return_exceptions=True)

        for block_result in block_results:
            if not block_result or isinstance(block_result, Exception):
                continue
            for item in block_result:
                url = item.get("url")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                results.append(item)
                if len(results) >= limit:
                    return results[:limit]

        return results[:limit]

    def lookup_domain(self, domain, limit=100):
        """
        Finds and downloads the CDX records for a specific domain.
        """
        if not self.cluster_idx:
            self.fetch_cluster_index()

        # Reverse domain for SURT key: com,soax
        parts = domain.split('.')
        reversed_domain = ",".join(parts[::-1])
        
        print(f"[*] Looking up key prefix: {reversed_domain}", file=sys.stderr)

        # Binary search to find the block
        keys = self._cluster_keys or [x[0] for x in self.cluster_idx]
        idx = bisect.bisect_right(keys, reversed_domain) - 1
        
        if idx < 0:
            return []

        # Check current block and subsequent blocks
        results = []
        unique_wats = set()
        
        # Limit the number of blocks to check
        MAX_BLOCKS_TO_CHECK = 20
        
        for i in range(idx, min(len(self.cluster_idx), idx + MAX_BLOCKS_TO_CHECK)):
            if len(unique_wats) >= limit:
                print(f"[*] Reached limit of {limit} WAT files.", file=sys.stderr)
                break
                
            block_key, filename, offset, length = self.cluster_idx[i]
            
            # Optimization: If block key is strictly greater than prefix and doesn't match prefix
            if i > idx and block_key > reversed_domain and not block_key.startswith(reversed_domain):
                break
            
            print(f"[*] Checking block {i}: {block_key} in {filename} (Offset: {offset}, Length: {length})", file=sys.stderr)

            shard_url = f"{self.index_base}/{filename}"
            headers = {"Range": f"bytes={offset}-{offset + length - 1}"}
            
            try:
                resp = requests.get(shard_url, headers=headers)
                if resp.status_code not in [200, 206]:
                    print(f"[!] Failed to fetch block: {resp.status_code}", file=sys.stderr)
                    continue

                content = gzip.decompress(resp.content)
                lines = content.decode('utf-8').splitlines()
                
                found_in_block = False
                for line in lines:
                    try:
                        parts = line.split(None, 2)
                        if len(parts) < 3: continue
                        
                        # Check matches
                        key = parts[0]
                        if key.startswith(reversed_domain):
                            # Check boundary to avoid partial domain matches (e.g. bbc vs bbc-worship)
                            # Allowed separators after domain: ) (root) or , (subdomain)
                            suffix = key[len(reversed_domain):]
                            if suffix and suffix[0] in [')', ',']:
                                found_in_block = True
                                meta = json.loads(parts[2])
                                warc_file = meta.get('filename', '')
                                
                                # Skip robots.txt files (they often don't have WATs or aren't useful)
                                if 'robotstxt' in warc_file or 'crawldiagnostics' in warc_file:
                                    continue
                                
                                # Convert to WAT
                                wat_file = warc_file.replace('/warc/', '/wat/').replace('.warc.gz', '.warc.wat.gz')
                                
                                if wat_file not in unique_wats:
                                    unique_wats.add(wat_file)
                                    results.append({
                                        'url': meta.get('url'),
                                        'wat_filename': wat_file,
                                        'timestamp': meta.get('timestamp')
                                    })
                    except Exception as e:
                        continue
                
                # If we passed the domain alphabetically in this block, we can stop
                if i > idx and not found_in_block:
                     # Double check if we really passed it
                     # If the last key in this block is > reversed_domain and no matches found, we are done
                     # Simplified: just rely on the optimization check at loop start
                     pass

            except Exception as e:
                print(f"[!] Error processing block: {e}", file=sys.stderr)
                continue
                
        return results

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python cc_offline_sniper.py <domain> <archive> [--print-wats]")
        sys.exit(1)

    domain = sys.argv[1]
    archive = sys.argv[2]
    
    client = CCIndexOfflineLookup(archive)
    results = client.lookup_domain(domain)
    
    # Output JSON for consumption
    # We output the full results so the Go binary knows which URLs to look for in which file
    print(json.dumps(results))
