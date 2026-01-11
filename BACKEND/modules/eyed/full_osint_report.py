#!/usr/bin/env python3
"""
EYE-D Full OSINT Report Generator

FULL STACK:
- Recursive search (VERIFIED queue until exhausted)
- BRUTE variations for all entity types
- Haiku/PACMAN AI entity extraction
- Cymonides graph persistence
- EDITH template report output

Usage:
    python3 full_osint_report.py --input entities.txt --output reports/
    python3 full_osint_report.py --emails "a@b.com" --phones "+123" --names "John Doe"
"""

import asyncio
import argparse
import json
import os
import re
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional, Set, Tuple
from collections import deque

# Add paths
EYED_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(EYED_ROOT))
sys.path.insert(0, str(EYED_ROOT.parent / "NEXUS"))
sys.path.insert(0, str(EYED_ROOT.parent / "PACMAN"))
sys.path.insert(0, str(EYED_ROOT.parent / "BRUTE"))

# Core imports
from unified_osint import UnifiedSearcher

# C1Bridge for Cymonides persistence
try:
    from c1_bridge import C1Bridge
    C1_AVAILABLE = True
except ImportError:
    C1_AVAILABLE = False
    C1Bridge = None

# EDITH writeup
try:
    from edith_writeup import render_report
    EDITH_AVAILABLE = True
except ImportError:
    EDITH_AVAILABLE = False
    render_report = None

# NEXUS variations
try:
    from variations import generate_variations, VariationGenerator
    VARIATIONS_AVAILABLE = True
except ImportError:
    try:
        from NEXUS.variations import generate_variations, VariationGenerator
        VARIATIONS_AVAILABLE = True
    except ImportError:
        VARIATIONS_AVAILABLE = False
        generate_variations = None

# PACMAN entity extraction
PACMAN_AVAILABLE = False
pacman_haiku = None
pacman_extract_fast = None
try:
    from ai_backends.haiku import HaikuBackend
    from entity_extractors import extract_fast
    pacman_haiku = HaikuBackend()
    pacman_extract_fast = extract_fast
    PACMAN_AVAILABLE = True
except ImportError:
    pass


class FullOSINTReporter:
    """
    Full recursive OSINT search with all integrations.

    Features:
    - VERIFIED priority queue (searches verified entities first)
    - Automatic entity extraction from all results
    - BRUTE variations for names/phones/emails
    - Cymonides graph persistence
    - EDITH template reports
    """

    def __init__(self, output_dir: str = "reports", project_id: str = None):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.project_id = project_id or f"osint_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.searcher = UnifiedSearcher()

        # Cymonides bridge
        self.c1 = C1Bridge() if C1_AVAILABLE else None

        # Priority queues
        self.verified_queue = deque()  # High priority - search immediately
        self.unverified_queue = deque()  # Lower priority - search after verified exhausted

        # Tracking
        self.searched = set()  # Already searched entities
        self.all_results = []  # All search results
        self.all_entities = []  # All extracted entities
        self.entity_graph = {}  # Entity relationships

        # Stats
        self.stats = {
            'total_searches': 0,
            'verified_searches': 0,
            'unverified_searches': 0,
            'promoted_to_verified': 0,  # UNVERIFIED entities promoted after Haiku check
            'entities_extracted': 0,
            'variations_generated': 0,
            'cymonides_nodes': 0
        }

        # Store raw data from VERIFIED searches for Haiku verification pass
        self.verified_raw_data = []

    def detect_entity_type(self, value: str) -> str:
        """Auto-detect entity type."""
        value = value.strip()
        if '@' in value and '.' in value:
            return 'email'
        if re.match(r'^[\+\d\s\-\(\)]{7,}$', value):
            return 'phone'
        if re.match(r'^https?://', value):
            return 'url'
        if 'linkedin.com' in value:
            return 'linkedin'
        if re.match(r'^[\d\.]+$', value) or re.match(r'^[a-fA-F0-9:]+$', value):
            return 'ip'
        if '.' in value and ' ' not in value and len(value) < 50:
            return 'domain'
        return 'name'

    def generate_variations(self, value: str, entity_type: str) -> List[str]:
        """Generate all variations for an entity using NEXUS."""
        variations = [value]

        if not VARIATIONS_AVAILABLE:
            return variations

        try:
            var_set = generate_variations(value, entity_type=entity_type)
            variations.extend(var_set.variations[:10])  # Limit to 10
            self.stats['variations_generated'] += len(var_set.variations[:10])
        except Exception as e:
            print(f"⚠️ Variation generation error: {e}")

        return list(set(variations))

    async def haiku_verify_unverified(self) -> int:
        """
        HAIKU VERIFICATION PASS:
        Check if any UNVERIFIED entities (names/usernames) appear in VERIFIED raw data.
        If found, PROMOTE them to VERIFIED queue (evidence exists linking them).

        Returns:
            Number of entities promoted to VERIFIED
        """
        if not PACMAN_AVAILABLE or not pacman_haiku:
            print("⚠️ Haiku not available for verification pass")
            return 0

        if not self.verified_raw_data:
            print("⚠️ No verified raw data to check against")
            return 0

        if not self.unverified_queue:
            print("✓ No unverified entities to check")
            return 0

        promoted_count = 0

        # Collect all UNVERIFIED entity values
        unverified_entities = []
        temp_queue = deque()
        while self.unverified_queue:
            item = self.unverified_queue.popleft()
            value, entity_type, entity = item
            unverified_entities.append({
                'value': value,
                'type': entity_type,
                'entity': entity,
                'item': item
            })
            temp_queue.append(item)

        # Restore unverified queue (will remove promoted ones later)
        self.unverified_queue = temp_queue

        if not unverified_entities:
            return 0

        print(f"\n🔍 HAIKU VERIFICATION PASS")
        print(f"   Checking {len(unverified_entities)} UNVERIFIED entities against VERIFIED raw data...")

        # Combine all verified raw data for context
        verified_context = "\n---\n".join([
            f"Source: {rd.get('source', 'unknown')}\nQuery: {rd.get('entity_value', '')}\nData: {json.dumps(rd.get('data', {}), default=str)[:2000]}"
            for rd in self.verified_raw_data[:20]  # Limit context size
        ])

        # Build prompt for Haiku
        entity_list = "\n".join([f"- {e['value']} ({e['type']})" for e in unverified_entities[:50]])

        prompt = f"""You are a verification analyst. Your task is to check if any of the UNVERIFIED entities below appear in the VERIFIED raw data.

UNVERIFIED ENTITIES TO CHECK:
{entity_list}

VERIFIED RAW DATA (from searches on emails, phones, domains, IPs):
{verified_context[:8000]}

TASK:
For each UNVERIFIED entity (name/username), determine if it appears in the VERIFIED raw data.
If an entity appears in the verified data, it should be PROMOTED to verified status because we have evidence linking it to a verified identifier.

Return a JSON array of entities that should be PROMOTED to VERIFIED:
[{{"value": "entity_value", "reason": "brief explanation of where it was found"}}]

If no entities should be promoted, return: []

ONLY return the JSON array, nothing else."""

        try:
            # Call Anthropic directly for custom prompt (HaikuBackend.extract is for entity extraction)
            import anthropic
            client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))

            message = client.messages.create(
                model='claude-haiku-4-5-20251001',
                max_tokens=4096,
                messages=[{'role': 'user', 'content': prompt}]
            )
            response = message.content[0].text

            if response and isinstance(response, str):
                # Parse JSON response
                import re as regex
                json_match = regex.search(r'\[.*\]', response, regex.DOTALL)
                if json_match:
                    promoted_list = json.loads(json_match.group())

                    # Process promoted entities
                    promoted_values = set()
                    for item in promoted_list:
                        if isinstance(item, dict) and 'value' in item:
                            promoted_values.add(item['value'].lower().strip())
                            print(f"   ✅ PROMOTING: {item['value']} - {item.get('reason', 'found in verified data')}")

                    # Move promoted entities from UNVERIFIED to VERIFIED queue
                    new_unverified = deque()
                    while self.unverified_queue:
                        item = self.unverified_queue.popleft()
                        value, entity_type, entity = item
                        if value.lower().strip() in promoted_values:
                            # PROMOTE to VERIFIED queue
                            self.verified_queue.append(item)
                            promoted_count += 1
                            self.stats['promoted_to_verified'] += 1
                        else:
                            new_unverified.append(item)

                    self.unverified_queue = new_unverified
                    print(f"   📊 Promoted {promoted_count} entities to VERIFIED queue")

        except Exception as e:
            print(f"   ⚠️ Haiku verification error: {e}")

        return promoted_count

    async def extract_entities_pacman(self, text: str) -> List[Dict]:
        """Extract entities using PACMAN (Haiku + regex)."""
        entities = []

        if not PACMAN_AVAILABLE:
            return entities

        try:
            # Fast regex extraction
            if pacman_extract_fast:
                fast = pacman_extract_fast(text)
                for etype, values in fast.items():
                    for val in values:
                        entities.append({
                            'type': etype,
                            'value': val,
                            'source': 'pacman_regex',
                            'verified': False
                        })

            # Haiku AI extraction
            if pacman_haiku and pacman_haiku.is_available():
                ai_entities = await pacman_haiku.extract(text)
                for ent in ai_entities:
                    etype = str(ent.entity_type.name).upper() if hasattr(ent.entity_type, 'name') else str(ent.entity_type)
                    entities.append({
                        'type': etype,
                        'value': ent.value,
                        'source': 'pacman_haiku',
                        'verified': False,
                        'confidence': getattr(ent, 'confidence', 0.8)
                    })

            self.stats['entities_extracted'] += len(entities)
        except Exception as e:
            print(f"⚠️ PACMAN extraction error: {e}")

        return entities

    def add_to_queue(self, entity: Dict, verified: bool = False):
        """Add entity to appropriate queue."""
        value = entity.get('value', '').strip()
        if not value or value in self.searched:
            return

        entity_type = entity.get('type', self.detect_entity_type(value))
        queue_item = (value, entity_type, entity)

        if verified:
            if value not in [q[0] for q in self.verified_queue]:
                self.verified_queue.append(queue_item)
                print(f"  ✓ VERIFIED queue: {value[:40]}...")
        else:
            if value not in [q[0] for q in self.unverified_queue]:
                self.unverified_queue.append(queue_item)

    async def search_entity(self, value: str, entity_type: str) -> Dict:
        """Search single entity through EYE-D."""
        print(f"\n{'='*60}")
        print(f"🔍 [{entity_type.upper()}] {value}")
        print(f"{'='*60}")

        self.searched.add(value)
        self.stats['total_searches'] += 1

        try:
            if entity_type == 'email':
                result = await self.searcher.search_email(value)
            elif entity_type == 'phone':
                result = await self.searcher.search_phone(value)
            elif entity_type == 'name':
                result = await self.searcher.search_people(value)
            elif entity_type == 'domain':
                result = await self.searcher.search_whois(value)
            elif entity_type == 'ip':
                result = await self.searcher.search_ip(value)
            elif entity_type in ['linkedin', 'url']:
                result = await self.searcher.search_linkedin(value)
            else:
                result = await self.searcher.search_people(value)

            result['_search_type'] = entity_type
            result['_search_value'] = value
            result['_timestamp'] = datetime.now().isoformat()

            return result

        except Exception as e:
            print(f"❌ Search error: {e}")
            return {
                'error': str(e),
                '_search_type': entity_type,
                '_search_value': value
            }

    def process_result(self, result: Dict) -> List[Dict]:
        """Process search result, extract entities, add to queues."""
        extracted = []

        # Get entities from result
        entities = result.get('entities', [])

        # Also extract from raw data using PACMAN
        for res in result.get('results', []):
            data = res.get('data', {})
            if isinstance(data, str):
                text = data
            elif isinstance(data, dict):
                text = json.dumps(data, default=str)
            elif isinstance(data, list):
                text = json.dumps(data, default=str)
            else:
                # Handle custom objects (OSINTResult, etc.)
                try:
                    if hasattr(data, '__dict__'):
                        text = json.dumps(data.__dict__, default=str)
                    else:
                        text = str(data)
                except:
                    text = str(data)

            # Run PACMAN extraction (sync wrapper)
            try:
                loop = asyncio.get_event_loop()
                pacman_entities = loop.run_until_complete(self.extract_entities_pacman(text[:10000]))
                entities.extend(pacman_entities)
            except:
                pass

        # Process all entities
        for entity in entities:
            # Skip non-dict entities
            if not isinstance(entity, dict):
                continue

            value = entity.get('value', '')
            if not value or not isinstance(value, str):
                continue
            value = value.strip()
            if len(value) < 3 or value in self.searched:
                continue

            etype = str(entity.get('type', '')).upper()

            # Map entity types
            if etype in ['EMAIL', 'MAIL']:
                entity_type = 'email'
            elif etype in ['PHONE', 'TELEPHONE', 'MOBILE']:
                entity_type = 'phone'
            elif etype in ['PERSON', 'NAME', 'FULL_NAME', 'NAME_VARIATION']:
                entity_type = 'name'
            elif etype in ['DOMAIN', 'WEBSITE']:
                entity_type = 'domain'
            elif etype in ['IP', 'IP_ADDRESS']:
                entity_type = 'ip'
            elif etype in ['URL', 'LINKEDIN', 'LINKEDIN_URL', 'SOCIAL_URL']:
                entity_type = 'url'
            elif etype in ['COMPANY', 'ORGANIZATION']:
                entity_type = 'name'  # Search as name
            elif etype in ['USERNAME', 'ACCOUNT']:
                entity_type = 'username'
            else:
                continue  # Skip unknown types

            # VERIFICATION RULE (ALL rounds):
            # Queue placement is based on what TYPE you will SEARCH ON:
            # - Searching ON name/username → UNVERIFIED results (ambiguous)
            # - Searching ON email/phone/domain/IP → VERIFIED results (unique)
            #
            # Even if a name was extracted from a VERIFIED email search,
            # when we SEARCH ON that name, the results are UNVERIFIED.
            # The queue determines what tag the search RESULTS get.
            if entity_type in ['name', 'username']:
                verified = False  # Searching ON names/usernames → UNVERIFIED results
            else:
                verified = True   # Searching ON emails/phones/domains/IPs → VERIFIED results

            # Add to appropriate queue
            self.add_to_queue({
                'value': value,
                'type': entity_type,
                'original_type': etype,
                'verified': verified,
                'source': entity.get('source', entity.get('context', 'unknown'))
            }, verified=verified)

            extracted.append(entity)

        return extracted

    def persist_to_cymonides(self, result: Dict, verified: bool = False, entities: List[Dict] = None):
        """
        Persist result to Cymonides graph with NARRATIVE tag edge.

        Args:
            result: Search result dict
            verified: True for VERIFIED tag, False for UNVERIFIED tag
            entities: List of extracted entities (for creating NEXUS relationships)
        """
        if not self.c1:
            return

        try:
            result_copy = dict(result)
            result_copy['project_id'] = self.project_id
            result_copy['verified'] = verified  # Pass verification status

            # Include extracted entities for NEXUS relationship creation
            if entities:
                existing_entities = result_copy.get('entities', [])
                result_copy['entities'] = existing_entities + entities

            node_id = self.c1.index_eyed_results(result_copy, verified=verified)
            self.stats['cymonides_nodes'] += 1
            tag_label = "VERIFIED" if verified else "UNVERIFIED"
            entity_count = len(result_copy.get('entities', []))
            print(f"  📊 Cymonides: {node_id} [{tag_label}] ({entity_count} entities)")
        except Exception as e:
            # Silently skip if ES unavailable
            pass

    async def run_recursive_search(
        self,
        emails: List[str] = None,
        phones: List[str] = None,
        names: List[str] = None,
        domains: List[str] = None,
        ips: List[str] = None,
        usernames: List[str] = None,
        max_depth: int = 3,
        max_total: int = 100
    ):
        """
        Run full recursive search with VERIFIED priority queue.

        1. Generate variations for all input entities
        2. Search VERIFIED entities first (high confidence)
        3. When VERIFIED exhausted, run Haiku verification pass
        4. Search PROMOTED entities (now verified)
        5. Search remaining UNVERIFIED
        6. Repeat until queues empty or limits reached
        """
        emails = emails or []
        phones = phones or []
        names = names or []
        domains = domains or []
        ips = ips or []
        usernames = usernames or []

        total_inputs = len(emails) + len(phones) + len(names) + len(domains) + len(ips) + len(usernames)

        print(f"\n{'#'*60}")
        print(f"# EYE-D FULL RECURSIVE OSINT SEARCH")
        print(f"# Project: {self.project_id}")
        print(f"#")
        print(f"# Input ({total_inputs} entities):")
        print(f"#   VERIFIED: {len(emails)} emails, {len(phones)} phones, {len(domains)} domains, {len(ips)} IPs")
        print(f"#   UNVERIFIED: {len(names)} names, {len(usernames)} usernames")
        print(f"# Max depth: {max_depth} | Max total: {max_total}")
        print(f"#")
        print(f"# Features:")
        print(f"#   - NEXUS Variations: {'✓' if VARIATIONS_AVAILABLE else '✗'}")
        print(f"#   - PACMAN Extraction: {'✓' if PACMAN_AVAILABLE else '✗'}")
        print(f"#   - Cymonides Graph: {'✓' if C1_AVAILABLE else '✗'}")
        print(f"#   - EDITH Reports: {'✓' if EDITH_AVAILABLE else '✗'}")
        print(f"{'#'*60}\n")

        # STEP 1: Generate variations and seed queues
        print("📋 STEP 1: Generating variations and seeding queues...")

        # VERIFICATION RULE: Queue placement based on what TYPE you search ON
        # - Searching ON email/phone/domain/IP → VERIFIED results
        # - Searching ON name/username → UNVERIFIED results
        # This applies to ALL rounds including Round 1

        # === VERIFIED QUEUE (unique identifiers) ===
        for email in emails:
            email = email.strip()
            variations = self.generate_variations(email, 'email')
            for var in variations:
                self.add_to_queue({'value': var, 'type': 'email'}, verified=True)

        for phone in phones:
            phone = phone.strip()
            variations = self.generate_variations(phone, 'phone')
            for var in variations:
                self.add_to_queue({'value': var, 'type': 'phone'}, verified=True)

        for domain in domains:
            domain = domain.strip()
            # No variations for domains - search as-is
            self.add_to_queue({'value': domain, 'type': 'domain'}, verified=True)

        for ip in ips:
            ip = ip.strip()
            # No variations for IPs - search as-is
            self.add_to_queue({'value': ip, 'type': 'ip'}, verified=True)

        # === UNVERIFIED QUEUE (ambiguous identifiers) ===
        for name in names:
            name = name.strip()
            variations = self.generate_variations(name, 'person')
            for var in variations:
                self.add_to_queue({'value': var, 'type': 'name'}, verified=False)

        for username in usernames:
            username = username.strip()
            # No variations for usernames - search as-is
            self.add_to_queue({'value': username, 'type': 'username'}, verified=False)

        print(f"\n✓ Seeded: {len(self.verified_queue)} VERIFIED, {len(self.unverified_queue)} UNVERIFIED entities")
        print(f"  (Variations: {self.stats['variations_generated']})")

        # STEP 2: Process VERIFIED queue first (exhaustively)
        print(f"\n📋 STEP 2: Processing VERIFIED queue (unique identifiers)...")

        # Phase 2A: Exhaust VERIFIED queue first
        while self.verified_queue and self.stats['total_searches'] < max_total:
            value, entity_type, entity = self.verified_queue.popleft()

            if value in self.searched:
                continue

            self.stats['verified_searches'] += 1
            print(f"\n[{self.stats['total_searches']+1}/{max_total}] (VERIFIED)")

            # Search
            result = await self.search_entity(value, entity_type)
            self.all_results.append(result)

            # Store raw data for Haiku verification pass
            self.verified_raw_data.append(result)

            # Extract entities and add to queues
            extracted = self.process_result(result)
            self.all_entities.extend(extracted)

            # Persist to Cymonides with VERIFIED tag (include extracted entities for NEXUS)
            self.persist_to_cymonides(result, verified=True, entities=extracted)

            # Progress
            print(f"  → Extracted: {len(extracted)} entities")
            print(f"  → Queues: {len(self.verified_queue)} VERIFIED, {len(self.unverified_queue)} UNVERIFIED")

        # Phase 2B: HAIKU VERIFICATION PASS
        # Check if any UNVERIFIED entities appear in VERIFIED raw data
        # If found, PROMOTE them to VERIFIED (we have evidence!)
        print(f"\n📋 STEP 3: Haiku Verification Pass...")
        promoted = await self.haiku_verify_unverified()

        if promoted > 0:
            print(f"\n✓ {promoted} entities promoted to VERIFIED based on evidence in raw data")
            print(f"  → New VERIFIED queue size: {len(self.verified_queue)}")

        # Phase 2C: Process newly VERIFIED entities (promoted ones)
        if self.verified_queue:
            print(f"\n📋 STEP 4: Processing PROMOTED entities (now VERIFIED)...")
            while self.verified_queue and self.stats['total_searches'] < max_total:
                value, entity_type, entity = self.verified_queue.popleft()

                if value in self.searched:
                    continue

                self.stats['verified_searches'] += 1
                print(f"\n[{self.stats['total_searches']+1}/{max_total}] (PROMOTED→VERIFIED)")

                # Search
                result = await self.search_entity(value, entity_type)
                self.all_results.append(result)

                # Store for potential future verification passes
                self.verified_raw_data.append(result)

                # Extract entities and add to queues
                extracted = self.process_result(result)
                self.all_entities.extend(extracted)

                # Persist with VERIFIED tag (promoted entities are now verified!)
                self.persist_to_cymonides(result, verified=True, entities=extracted)

                print(f"  → Extracted: {len(extracted)} entities")
                print(f"  → Queues: {len(self.verified_queue)} VERIFIED, {len(self.unverified_queue)} UNVERIFIED")

        # Phase 2D: Process remaining UNVERIFIED queue
        depth = 0
        if self.unverified_queue:
            print(f"\n📋 STEP 5: Processing UNVERIFIED queue (ambiguous identifiers)...")
            while self.unverified_queue and self.stats['total_searches'] < max_total and depth < max_depth:
                value, entity_type, entity = self.unverified_queue.popleft()

                if value in self.searched:
                    continue

                self.stats['unverified_searches'] += 1
                depth += 1
                print(f"\n[{self.stats['total_searches']+1}/{max_total}] (UNVERIFIED)")

                # Search
                result = await self.search_entity(value, entity_type)
                self.all_results.append(result)

                # Extract entities and add to queues
                extracted = self.process_result(result)
                self.all_entities.extend(extracted)

                # Persist with UNVERIFIED tag (include extracted entities for NEXUS)
                self.persist_to_cymonides(result, verified=False, entities=extracted)

                print(f"  → Extracted: {len(extracted)} entities")
                print(f"  → Queues: {len(self.verified_queue)} VERIFIED, {len(self.unverified_queue)} UNVERIFIED")

        # STEP 6: Summary
        print(f"\n{'='*60}")
        print(f"✅ RECURSIVE SEARCH COMPLETE")
        print(f"{'='*60}")
        print(f"Total searches: {self.stats['total_searches']}")
        print(f"  - VERIFIED: {self.stats['verified_searches']}")
        print(f"  - UNVERIFIED: {self.stats['unverified_searches']}")
        print(f"  - Promoted to VERIFIED: {self.stats['promoted_to_verified']}")
        print(f"Entities extracted: {self.stats['entities_extracted']}")
        print(f"Variations generated: {self.stats['variations_generated']}")
        print(f"Cymonides nodes: {self.stats['cymonides_nodes']}")

    def generate_edith_report(self) -> str:
        """Generate EDITH-style markdown report."""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        md = []
        md.append(f"# OSINT INTELLIGENCE REPORT")
        md.append(f"## Project: {self.project_id}")
        md.append(f"**Generated:** {timestamp}")
        md.append("")

        # Executive Summary
        md.append("---")
        md.append("## EXECUTIVE SUMMARY")
        md.append("")
        md.append(f"This report presents findings from a comprehensive OSINT investigation using the EYE-D platform.")
        md.append("")
        md.append("### Statistics")
        md.append(f"| Metric | Value |")
        md.append(f"|--------|-------|")
        md.append(f"| Total Searches | {self.stats['total_searches']} |")
        md.append(f"| Verified Searches | {self.stats['verified_searches']} |")
        md.append(f"| Unverified Searches | {self.stats['unverified_searches']} |")
        md.append(f"| Promoted to Verified | {self.stats['promoted_to_verified']} |")
        md.append(f"| Entities Extracted | {self.stats['entities_extracted']} |")
        md.append(f"| Name Variations | {self.stats['variations_generated']} |")
        md.append(f"| Graph Nodes Created | {self.stats['cymonides_nodes']} |")
        md.append("")

        # Entity Summary
        md.append("---")
        md.append("## ENTITIES DISCOVERED")
        md.append("")

        # Group entities by type
        by_type = {}
        for ent in self.all_entities:
            etype = ent.get('type', ent.get('original_type', 'OTHER'))
            if etype not in by_type:
                by_type[etype] = []
            val = ent.get('value', '')
            if val and val not in [e['value'] for e in by_type[etype]]:
                by_type[etype].append(ent)

        for etype, entities in sorted(by_type.items()):
            md.append(f"### {etype} ({len(entities)})")
            md.append("")
            for ent in entities[:50]:
                val = ent.get('value', '')
                src = ent.get('source', '')
                verified = "✓" if ent.get('verified') else ""
                md.append(f"- {val} {verified} *({src})*" if src else f"- {val} {verified}")
            if len(entities) > 50:
                md.append(f"- *... and {len(entities) - 50} more*")
            md.append("")

        # Detailed Results
        md.append("---")
        md.append("## DETAILED FINDINGS")
        md.append("")

        for i, result in enumerate(self.all_results, 1):
            stype = result.get('_search_type', 'unknown')
            sval = result.get('_search_value', 'unknown')

            md.append(f"### {i}. {stype.upper()}: {sval}")
            md.append("")

            if result.get('error'):
                md.append(f"**Error:** {result['error']}")
                md.append("")
                continue

            # Results by source
            for res in result.get('results', [])[:10]:
                source = res.get('source', 'unknown')
                md.append(f"#### Source: {source}")
                md.append("")

                data = res.get('data', {})

                if isinstance(data, list):
                    md.append(f"Records: {len(data)}")
                    md.append("")
                    for j, item in enumerate(data[:5], 1):
                        if isinstance(item, dict):
                            md.append(f"**Record {j}:**")
                            for k, v in list(item.items())[:10]:
                                if v:
                                    md.append(f"- {k}: {v}")
                        else:
                            md.append(f"- {item}")
                    if len(data) > 5:
                        md.append(f"*... {len(data) - 5} more records*")
                    md.append("")
                elif isinstance(data, dict):
                    for k, v in list(data.items())[:15]:
                        if v and not isinstance(v, (dict, list)):
                            md.append(f"- **{k}:** {v}")
                    md.append("")
                else:
                    md.append(f"{str(data)[:500]}")
                    md.append("")

            md.append("---")
            md.append("")

        # Appendix
        md.append("## APPENDIX: Search Queue Summary")
        md.append("")
        md.append("### Searched Entities")
        md.append("")
        for val in sorted(self.searched):
            md.append(f"- {val}")
        md.append("")

        return '\n'.join(md)

    def save_reports(self):
        """Save all reports."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        # EDITH Markdown Report
        report_path = self.output_dir / f"{self.project_id}_{timestamp}_REPORT.md"
        with open(report_path, 'w') as f:
            f.write(self.generate_edith_report())
        print(f"\n📄 Report: {report_path}")

        # Raw JSON
        json_path = self.output_dir / f"{self.project_id}_{timestamp}_RAW.json"
        with open(json_path, 'w') as f:
            json.dump({
                'project_id': self.project_id,
                'timestamp': timestamp,
                'stats': self.stats,
                'results': self.all_results,
                'entities': self.all_entities,
                'searched': list(self.searched)
            }, f, indent=2, default=str)
        print(f"📊 JSON: {json_path}")

        # Entity list
        entities_path = self.output_dir / f"{self.project_id}_{timestamp}_ENTITIES.txt"
        with open(entities_path, 'w') as f:
            for ent in self.all_entities:
                f.write(f"{ent.get('type', 'UNKNOWN')}\t{ent.get('value', '')}\t{ent.get('source', '')}\n")
        print(f"📋 Entities: {entities_path}")

        return report_path


def parse_input_file(filepath: str) -> Dict[str, List[str]]:
    """
    Parse input file (auto-detect types).

    Supports explicit type prefixes:
        email:john@example.com
        phone:+1-555-1234
        name:John Smith
        domain:example.com
        ip:192.168.1.1
        username:jsmith

    Or auto-detection based on patterns.
    """
    result = {
        'emails': [],
        'phones': [],
        'names': [],
        'domains': [],
        'ips': [],
        'usernames': []
    }

    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            # Check for explicit type prefix
            if ':' in line and line.split(':')[0].lower() in ['email', 'phone', 'name', 'domain', 'ip', 'username']:
                prefix, value = line.split(':', 1)
                prefix = prefix.lower().strip()
                value = value.strip()
                if prefix == 'email':
                    result['emails'].append(value)
                elif prefix == 'phone':
                    result['phones'].append(value)
                elif prefix == 'name':
                    result['names'].append(value)
                elif prefix == 'domain':
                    result['domains'].append(value)
                elif prefix == 'ip':
                    result['ips'].append(value)
                elif prefix == 'username':
                    result['usernames'].append(value)
            else:
                # Auto-detect type
                if '@' in line and '.' in line:
                    result['emails'].append(line)
                elif re.match(r'^[\+\d\s\-\(\)]{7,}$', line):
                    result['phones'].append(line)
                elif re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', line):
                    result['ips'].append(line)
                elif re.match(r'^[a-fA-F0-9:]{10,}$', line):  # IPv6
                    result['ips'].append(line)
                elif '.' in line and ' ' not in line and len(line) < 50 and not '@' in line:
                    result['domains'].append(line)
                elif line.startswith('@') or (len(line) < 30 and ' ' not in line and not '.' in line):
                    # Likely a username (starts with @ or short no-space string)
                    result['usernames'].append(line.lstrip('@'))
                else:
                    # Default to name
                    result['names'].append(line)

    return result


async def main():
    parser = argparse.ArgumentParser(description='EYE-D Full Recursive OSINT Report')
    parser.add_argument('--input', '-i', help='Input file (one entity per line, auto-detected)')
    parser.add_argument('--output', '-o', default='reports', help='Output directory')
    parser.add_argument('--emails', '-e', help='Comma-separated emails')
    parser.add_argument('--phones', '-p', help='Comma-separated phones')
    parser.add_argument('--names', '-n', help='Comma-separated names')
    parser.add_argument('--domains', '-d', help='Comma-separated domains')
    parser.add_argument('--ips', help='Comma-separated IP addresses')
    parser.add_argument('--usernames', '-u', help='Comma-separated usernames')
    parser.add_argument('--max-depth', type=int, default=3, help='Max recursion depth')
    parser.add_argument('--max-total', type=int, default=100, help='Max total searches')
    parser.add_argument('--project', help='Project ID')

    args = parser.parse_args()

    emails, phones, names, domains, ips, usernames = [], [], [], [], [], []

    if args.input:
        parsed = parse_input_file(args.input)
        emails.extend(parsed.get('emails', []))
        phones.extend(parsed.get('phones', []))
        names.extend(parsed.get('names', []))
        domains.extend(parsed.get('domains', []))
        ips.extend(parsed.get('ips', []))
        usernames.extend(parsed.get('usernames', []))

    if args.emails:
        emails.extend([e.strip() for e in args.emails.split(',')])
    if args.phones:
        phones.extend([p.strip() for p in args.phones.split(',')])
    if args.names:
        names.extend([n.strip() for n in args.names.split(',')])
    if args.domains:
        domains.extend([d.strip() for d in args.domains.split(',')])
    if args.ips:
        ips.extend([i.strip() for i in args.ips.split(',')])
    if args.usernames:
        usernames.extend([u.strip() for u in args.usernames.split(',')])

    if not any([emails, phones, names, domains, ips, usernames]):
        print("No entities provided. Use --input FILE or --emails/--phones/--names/--domains/--ips/--usernames")
        parser.print_help()
        return

    reporter = FullOSINTReporter(output_dir=args.output, project_id=args.project)

    await reporter.run_recursive_search(
        emails=emails,
        phones=phones,
        names=names,
        domains=domains,
        ips=ips,
        usernames=usernames,
        max_depth=args.max_depth,
        max_total=args.max_total
    )

    reporter.save_reports()

    print(f"\n{'='*60}")
    print(f"✅ COMPLETE - Reports saved to {args.output}/")
    print(f"{'='*60}")


if __name__ == '__main__':
    asyncio.run(main())
